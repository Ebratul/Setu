"""FR-4 KYB engine: name matching, each check, aggregation and the demo scenarios. Pure, no DB."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.config import get_settings
from app.domain import kyb
from app.domain.kyb import (
    AccountFacts,
    Check,
    HistoryFacts,
    PartyFacts,
    SanctionEntry,
    Thresholds,
    aggregate,
    assess,
    band_for,
    match_names,
    normalise_name,
)

TODAY = date(2026, 10, 20)
HUAXIN = PartyFacts("Shaoxing Huaxin Textile Co., Ltd.", "Shaoxing Huaxin Textile Co., Ltd.", "CN")
HUAMENG = PartyFacts(
    "Guangzhou Huameng Trading Co., Ltd.", "Guangzhou Huameng Trading Co., Ltd.", "CN"
)
HISTORY = HistoryFacts(total_deals=2, completed_deals=2)


def acct(
    holder: str,
    *,
    kind: str = "CORPORATE",
    seen: int = 400,
    country: str = "CN",
    currency: str = "CNY",
    pending: bool = False,
) -> AccountFacts:
    return AccountFacts(
        holder, kind, TODAY - timedelta(days=seen), country, currency, pending=pending
    )


def run(
    party: PartyFacts, account: AccountFacts | None, invoice: str | None = None, **kw
) -> kyb.Assessment:
    return assess(
        party=party,
        invoice_name=invoice or party.legal_name,
        account=account,
        history=kw.pop("history", HISTORY),
        sanctions=kw.pop("sanctions", ()),
        today=TODAY,
        **kw,
    )


def by_code(a: kyb.Assessment) -> dict[str, str]:
    return {c.code: c.status for c in a.checks}


# --- names ---------------------------------------------------------------------------------


def test_normalise_collapses_case_punctuation_and_suffixes() -> None:
    assert (
        normalise_name("  Shaoxing  HUAXIN Textile Co., Ltd. ") == "shaoxing huaxin textile co ltd"
    )
    assert normalise_name("Huaxin Textile Company Limited") == "huaxin textile co ltd"
    assert normalise_name("A&B Corp.") == "a and b co"
    assert normalise_name("Café Résumé Trade") == "cafe resume trading"
    assert normalise_name("Huaxin Textile (HK) Trading Ltd") == "huaxin textile hk trading ltd"


def test_normalise_cjk_company_words() -> None:
    assert normalise_name("绍兴 Huaxin 纺织有限公司") == "shaoxing huaxin textile ltd"
    assert normalise_name("") == "" and normalise_name("...") == ""


def test_name_variants_reach_the_match_threshold() -> None:
    m = match_names("SHAOXING HUAXIN TEXTILE CO LTD", "Shaoxing Huaxin Textile Co., Ltd.")
    assert m.score == Decimal("100.00") and m.band == "match"
    m2 = match_names("Shaoxing Huaxin Textile Company Limited", HUAXIN.legal_name)
    assert m2.band == "match"


def test_loose_variants_are_partial_or_mismatch_never_match() -> None:
    assert match_names("Huaxin Textiles Trading", HUAXIN.legal_name).band in ("partial", "mismatch")
    # a subset name must not score 100 just because token_set_ratio does
    assert match_names("Huaxin Textile", HUAXIN.legal_name).band == "partial"
    hk = match_names("Huaxin Textile (HK) Trading Ltd", HUAXIN.legal_name)
    assert hk.band == "mismatch" and hk.score < 80
    assert match_names("Chen Wei", HUAMENG.legal_name).band == "mismatch"
    assert match_names("", "x").score == Decimal("0.00")


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (100, "match"),
        (92.0, "match"),
        (91.99, "partial"),
        (80.0, "partial"),
        (79.99, "mismatch"),
        (0, "mismatch"),
    ],
)
def test_threshold_boundaries(score: float, band: str) -> None:
    assert band_for(score, 92.0, 80.0) == band


def test_thresholds_are_configurable_and_scores_are_floored() -> None:
    s = get_settings()
    assert (s.kyb_match_threshold, s.kyb_partial_threshold) == (92.0, 80.0)
    m = match_names("Huaxin Textile", HUAXIN.legal_name, match=70, partial=50)
    assert m.band == "match"  # same score, looser thresholds
    assert m.score == m.score.quantize(Decimal("0.01"))


# --- checks --------------------------------------------------------------------------------


def test_huaxin_active_corporate_account_is_verified() -> None:
    a = run(HUAXIN, acct(HUAXIN.legal_name, seen=400))
    assert a.status == "VERIFIED" and a.score == 100 and a.reason_codes == ()
    assert set(by_code(a)) == {
        "LICENSE_VS_INVOICE_NAME",
        "LICENSE_VS_ACCOUNT_HOLDER",
        "ACCOUNT_TYPE",
        "ACCOUNT_AGE",
        "ACCOUNT_COUNTRY",
        "REGISTRY_HISTORY",
        "SANCTIONS_SCREEN",
    }
    assert all(c.detail_en and c.detail_bn for c in a.checks)
    assert "Verified" in a.explanation_en and a.explanation_bn


def test_huameng_personal_new_account_tc01() -> None:
    a = run(HUAMENG, acct("Chen Wei", kind="PERSONAL", seen=3))
    codes = by_code(a)
    assert a.status == "WARNING"
    assert codes["LICENSE_VS_ACCOUNT_HOLDER"] == "FAIL"
    assert codes["ACCOUNT_TYPE"] == "FAIL"
    assert codes["ACCOUNT_AGE"] == "FAIL"
    assert codes["LICENSE_VS_INVOICE_NAME"] == "PASS" and codes["SANCTIONS_SCREEN"] == "PASS"
    assert a.score == 40  # 100 - 25 - 20 - 15
    assert a.reason_codes == ("LICENSE_VS_ACCOUNT_HOLDER", "ACCOUNT_TYPE", "ACCOUNT_AGE")
    assert "Chen Wei" in a.explanation_en and "Chen Wei" in a.explanation_bn


def test_pending_hk_account_is_warned_not_trusted() -> None:
    hk = acct("Huaxin Textile (HK) Trading Ltd", seen=1, country="HK", currency="USD", pending=True)
    a = run(HUAXIN, hk)
    codes = by_code(a)
    assert a.status == "WARNING"
    assert codes["PENDING_BENEFICIARY_CHANGE"] == "WARN"
    assert codes["ACCOUNT_COUNTRY"] == "WARN"
    assert codes["LICENSE_VS_ACCOUNT_HOLDER"] == "FAIL" and codes["ACCOUNT_AGE"] == "FAIL"


@pytest.mark.parametrize(
    ("days", "status"), [(0, "FAIL"), (6, "FAIL"), (7, "WARN"), (29, "WARN"), (30, "PASS")]
)
def test_account_age_boundaries(days: int, status: str) -> None:
    a = run(HUAXIN, acct(HUAXIN.legal_name, seen=days))
    assert by_code(a)["ACCOUNT_AGE"] == status


def test_country_and_currency_consistency() -> None:
    assert (
        by_code(run(HUAXIN, acct(HUAXIN.legal_name, currency="USD")))["ACCOUNT_COUNTRY"] == "PASS"
    )
    assert by_code(run(HUAXIN, acct(HUAXIN.legal_name, country="HK")))["ACCOUNT_COUNTRY"] == "WARN"
    bdt = acct(HUAXIN.legal_name, currency="BDT")
    assert by_code(run(HUAXIN, bdt))["ACCOUNT_COUNTRY"] == "WARN"


def test_invoice_name_mismatch_is_flagged() -> None:
    a = run(HUAXIN, acct(HUAXIN.legal_name), invoice="Huaxin Textiles Trading")
    assert by_code(a)["LICENSE_VS_INVOICE_NAME"] in ("WARN", "FAIL")
    assert a.status == "WARNING"


def test_licence_name_falls_back_to_legal_name() -> None:
    party = PartyFacts(HUAXIN.legal_name, None, "CN")
    assert run(party, acct(HUAXIN.legal_name)).status == "VERIFIED"


def test_registry_history_rules() -> None:
    def hist(total: int, disputed: int) -> HistoryFacts:
        return HistoryFacts(total_deals=total, completed_deals=0, disputed_deals=disputed)

    ok = acct(HUAXIN.legal_name)
    assert by_code(run(HUAXIN, ok, history=hist(0, 0)))["REGISTRY_HISTORY"] == "PASS"
    assert by_code(run(HUAXIN, ok, history=hist(2, 1)))["REGISTRY_HISTORY"] == "PASS"  # 50%
    assert by_code(run(HUAXIN, ok, history=hist(5, 2)))["REGISTRY_HISTORY"] == "WARN"
    assert by_code(run(HUAXIN, ok, history=hist(3, 2)))["REGISTRY_HISTORY"] == "WARN"
    prev = HistoryFacts(1, 1, 0, (("2026-10-19T09:00:00+00:00", "WARNING"),))
    c = next(c for c in run(HUAXIN, ok, history=prev).checks if c.code == "REGISTRY_HISTORY")
    assert c.evidence["previous_checks"] == [
        {"checked_at": "2026-10-19T09:00:00+00:00", "status": "WARNING"}
    ]


def test_no_active_account_warns() -> None:
    a = run(HUAXIN, None)
    assert by_code(a)["RECEIVING_ACCOUNT"] == "WARN" and a.status == "WARNING"


# --- sanctions -----------------------------------------------------------------------------

LISTED = (SanctionEntry("T-1", ("Zhongtai Meridian Trading Co., Ltd.",), "fictional"),)


def test_sanctioned_supplier_name_is_blocked_with_score_zero() -> None:
    party = PartyFacts("ZHONGTAI MERIDIAN TRADING CO LTD", None, "CN")
    a = run(party, acct(party.legal_name), sanctions=LISTED)
    assert a.status == "BLOCKED" and a.score == 0
    assert a.reason_codes[0] == "SANCTIONS_SCREEN"
    hit = next(c for c in a.checks if c.code == "SANCTIONS_SCREEN")
    assert hit.status == "FAIL" and hit.evidence["hits"][0]["entry_id"] == "T-1"
    assert "No payment should be sent" in a.explanation_en


def test_sanctioned_account_holder_and_invoice_name_are_screened() -> None:
    holder = run(HUAXIN, acct("Zhongtai Meridian Trading Co Ltd"), sanctions=LISTED)
    assert holder.status == "BLOCKED"
    invoice = run(
        HUAXIN, acct(HUAXIN.legal_name), invoice="Zhongtai Meridian Trading", sanctions=LISTED
    )
    # the invoice seller name is screened too, but alone it is only a hold, never a block
    assert invoice.status == "WARNING" and invoice.score <= kyb.HOLD_SCORE_CAP
    hit = next(c for c in invoice.checks if c.code == "SANCTIONS_SCREEN")
    assert hit.status == "FAIL" and hit.evidence["blocking"] is False
    assert hit.evidence["hits"][0]["role"] == "invoice_name"
    assert "not blocked" in hit.detail_en
    assert (
        by_code(run(HUAXIN, acct(HUAXIN.legal_name), sanctions=LISTED))["SANCTIONS_SCREEN"]
        == "PASS"
    )


def test_demo_cast_does_not_hit_the_mock_sanctions_list() -> None:
    data = json.loads(get_settings().kyb_sanctions_file.read_text(encoding="utf-8"))
    entries = tuple(SanctionEntry(e["id"], tuple(e["names"])) for e in data["entries"])
    assert len(entries) >= 3 and "fictional" in data["note"].lower()
    names = [HUAXIN.legal_name, HUAMENG.legal_name, "Ningbo Brightline Accessories Co., Ltd.",
             "Chen Wei", "Huaxin Textile (HK) Trading Ltd"]  # fmt: skip
    assert kyb.screen_sanctions(names, entries, Thresholds()) == []
    assert kyb.screen_sanctions(["Zhao Meilin"], entries, Thresholds())


# --- aggregation ---------------------------------------------------------------------------


def chk(code: str, status: str) -> Check:
    return Check(code, status, "en", "bn")  # type: ignore[arg-type]


def test_score_formula_weights_and_warn_is_half() -> None:
    extras = {"RECEIVING_ACCOUNT", "DOC_INSTRUCTION"}
    assert sum(w for c, w in kyb.WEIGHTS.items() if c not in extras) == 100
    assert kyb.score_of([chk("ACCOUNT_TYPE", "FAIL")]) == 80
    assert kyb.score_of([chk("ACCOUNT_TYPE", "WARN")]) == 90
    assert kyb.score_of([chk("PENDING_BENEFICIARY_CHANGE", "WARN")]) == 98  # 2.5 -> half up 97.5
    assert kyb.score_of([chk(c, "FAIL") for c in kyb.WEIGHTS]) == 0
    assert kyb.score_of([chk("SANCTIONS_SCREEN", "FAIL")]) == 0


def test_status_rules() -> None:
    assert aggregate([chk("ACCOUNT_AGE", "PASS")]).status == "VERIFIED"
    assert aggregate([chk("ACCOUNT_AGE", "WARN")]).status == "WARNING"
    assert aggregate([chk("ACCOUNT_AGE", "FAIL")]).status == "WARNING"  # not critical
    assert (
        aggregate([chk("ACCOUNT_AGE", "FAIL"), chk("SANCTIONS_SCREEN", "FAIL")]).status == "BLOCKED"
    )


def test_reason_codes_put_fails_first() -> None:
    a = aggregate([chk("ACCOUNT_COUNTRY", "WARN"), chk("ACCOUNT_TYPE", "FAIL")])
    assert a.reason_codes == ("ACCOUNT_TYPE", "ACCOUNT_COUNTRY")


def test_explanations_are_deterministic_and_bangla_uses_bangla_digits() -> None:
    a = run(HUAMENG, acct("Chen Wei", kind="PERSONAL", seen=3))
    assert a == run(HUAMENG, acct("Chen Wei", kind="PERSONAL", seen=3))
    assert "\u09ea\u09e6" in a.explanation_bn and "40" not in a.explanation_bn  # Bangla 40


def test_generated_text_never_looks_like_an_instruction_to_the_detector() -> None:
    from app.security.injection import detect_instructions

    party = PartyFacts("ZHONGTAI MERIDIAN TRADING CO LTD", None, "CN")
    scenarios = [
        run(HUAXIN, acct(HUAXIN.legal_name)),
        run(HUAMENG, acct("Chen Wei", kind="PERSONAL", seen=3)),
        run(party, acct(party.legal_name), sanctions=LISTED),
        run(HUAXIN, acct("Huaxin Textile (HK) Trading Ltd", seen=1, country="HK", pending=True)),
        run(HUAXIN, None),
    ]
    for a in scenarios:
        texts = [a.explanation_en, a.explanation_bn]
        texts += [c.detail_en for c in a.checks] + [c.detail_bn for c in a.checks]
        assert [f for t in texts for f in detect_instructions(t)] == []


def test_party_only_assessment_has_no_invoice_check_or_screening() -> None:
    a = assess(
        party=HUAXIN,
        invoice_name=None,
        account=acct(HUAXIN.legal_name),
        history=HISTORY,
        sanctions=LISTED,
        today=TODAY,
    )
    assert "LICENSE_VS_INVOICE_NAME" not in by_code(a) and a.status == "VERIFIED"
    sanc = next(c for c in a.checks if c.code == "SANCTIONS_SCREEN")
    assert "invoice_name" not in {h["role"] for h in sanc.evidence["hits"]}
    listed_invoice = assess(
        party=HUAXIN,
        invoice_name="Zhongtai Meridian Trading Co., Ltd.",
        account=acct(HUAXIN.legal_name),
        history=HISTORY,
        sanctions=LISTED,
        today=TODAY,
    )
    assert listed_invoice.status == "WARNING"


def test_instruction_like_invoice_text_adds_a_doc_instruction_reason() -> None:
    a = run(HUAXIN, acct(HUAXIN.legal_name), invoice_flags=["SYSTEM_ROLE"])
    assert a.status == "WARNING" and "DOC_INSTRUCTION" in a.reason_codes
    check = next(c for c in a.checks if c.code == "DOC_INSTRUCTION")
    assert check.evidence == {"finding_codes": ["SYSTEM_ROLE"]}


def test_homoglyphs_and_zero_width_characters_cannot_dodge_the_sanctions_screen() -> None:
    cyrillic = "Zh\u043eng\u0442ai M\u0435ridi\u0430n Trading Co., Ltd."  # cyrillic o t e a
    zero_width = "Zhong\u200btai Meridian\u200d Trading Co., Ltd."
    greek = "Zh\u03bfngtai Meridian Trading Co., Ltd."  # omicron
    assert normalise_name(cyrillic) == normalise_name("Zhongtai Meridian Trading Co., Ltd.")
    for name in (cyrillic, zero_width, greek):
        party = PartyFacts(name, None, "CN")
        a = run(party, acct(party.legal_name), sanctions=LISTED)
        assert a.status == "BLOCKED", name


@pytest.mark.parametrize(
    "content",
    [
        '{"version": "x", "entries": []}',
        '{"entries": [{"id": "1", "names": ["A"]}]}',
        '{"version": "x", "entries": [{"id": "1", "names": []}]}',
        '{"version": "x"}',
        "[]",
        "not json",
    ],
)
def test_unusable_sanctions_file_fails_closed(tmp_path, content: str) -> None:  # type: ignore[no-untyped-def]
    from app.errors import ServiceUnavailable
    from app.services.kyb import load_sanctions

    f = tmp_path / "s.json"
    f.write_text(content)
    with pytest.raises(ServiceUnavailable):
        load_sanctions(f)
    with pytest.raises(ServiceUnavailable):
        load_sanctions(tmp_path / "missing.json")


def test_valid_sanctions_file_loads(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.services.kyb import load_sanctions

    f = tmp_path / "s.json"
    f.write_text('{"version": "t", "entries": [{"id": "1", "names": ["Fiction Co"]}]}')
    assert [e.id for e in load_sanctions(f)] == ["1"]
