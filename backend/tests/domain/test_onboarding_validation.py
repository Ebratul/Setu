"""Pure onboarding validators and the profile checks. No database."""

from datetime import date

import pytest

from app.domain import onboarding_kyb as engine
from app.domain import onboarding_validation as v
from app.domain.kyb import SanctionEntry, Thresholds

GOOD_USCC = ["91350100M000100Y43", "91330201MA2ABC1233"]


@pytest.mark.parametrize("code", GOOD_USCC)
def test_valid_uscc(code: str) -> None:
    assert v.uscc_valid(code) and v.uscc_valid(code.lower()) and v.uscc_valid(f" {code} ")


@pytest.mark.parametrize(
    "code",
    [
        "91350100M000100Y44",  # wrong check character
        "91350100M000100Y4",  # 17 chars
        "91350100M000100Y433",  # 19 chars
        "I1350100M000100Y43",  # I is not in the alphabet
        "91350100M000100Y4O",
        "",
        "九13501" + "0" * 12,
    ],
)
def test_invalid_uscc(code: str) -> None:
    assert not v.uscc_valid(code)


def test_check_char_follows_gb_32100() -> None:
    assert v.uscc_check_char("91350100M000100Y4") == "3"
    assert v.uscc_check_char("short") is None
    assert v.uscc_check_char("9135010!M000100Y4") is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01712345678", "+8801712345678"),
        ("+8801712345678", "+8801712345678"),
        ("8801712345678", "+8801712345678"),
        ("+880 1712-345678", "+8801712345678"),
        ("(017) 1234 5678", "+8801712345678"),
        ("01212345678", None),
        ("+8801712345", None),
        ("+8613800138000", None),
        ("abc", None),
        ("", None),
    ],
)
def test_bd_mobile(raw: str, expected: str | None) -> None:
    assert v.normalise_bd_mobile(raw) == expected


def test_id_patterns_are_applied_to_the_whole_value() -> None:
    assert v.id_matches(r"^\d{9,13}$", "123 456 789")
    assert not v.id_matches(r"^\d{9,13}$", "12345678")
    assert not v.id_matches(r"^\d{9,13}$", "123456789 x")
    assert not v.id_matches("(unclosed", "123")  # a broken operator regex never passes


def test_expiry_states() -> None:
    today = date(2026, 10, 21)
    assert v.expiry_state(date(2026, 10, 20), today) == "EXPIRED"
    assert v.expiry_state(today, today) == "EXPIRING"
    assert v.expiry_state(date(2026, 11, 20), today) == "EXPIRING"
    assert v.expiry_state(date(2026, 11, 21), today) == "OK"


SANCTIONS = (SanctionEntry("S-1", ("Baihe Orchid Logistics Limited",), "mock"),)


def facts(**over: object) -> engine.ProfileFacts:
    base: dict[str, object] = {
        "role": "BUYER",
        "legal_name": "Padma Textile Imports Ltd",
        "contact_name": "Nusrat Jahan",
        "today": date(2026, 10, 21),
        "duplicate_of_other_company": False,
        "phone_verified": True,
        "doc_types": frozenset({"TRADE_LICENSE", "IRC"}),
        "reused_hash": False,
        "license_expiry": date(2027, 10, 21),
    }
    base.update(over)
    return engine.ProfileFacts(**base)  # type: ignore[arg-type]


def run(f: engine.ProfileFacts) -> dict[str, str]:
    out = engine.assess_profile(f, SANCTIONS, ["BD", "CN"], Thresholds())
    return {c.code: c.status for c in out.checks}


def test_clean_buyer_passes_everything() -> None:
    out = engine.assess_profile(facts(), SANCTIONS, ["BD", "CN"], Thresholds())
    assert {c.status for c in out.checks} == {"PASS"} and out.score == 100
    assert out.recommendation == "AUTO_CLEAR" and engine.risk_summary(out.checks) == "PASS"


def test_each_buyer_problem_is_flagged() -> None:
    assert run(facts(duplicate_of_other_company=True))["DUPLICATE_COMPANY"] == "FAIL"
    assert run(facts(reused_hash=True))["DOC_HASH_REUSE"] == "FAIL"
    assert run(facts(phone_verified=False))["PHONE_VERIFIED"] == "FAIL"
    assert run(facts(doc_types=frozenset({"IRC"})))["DOC_PRESENT"] == "FAIL"
    assert run(facts(license_expiry=date(2026, 10, 20)))["LICENSE_EXPIRY"] == "FAIL"
    assert run(facts(license_expiry=date(2026, 11, 1)))["LICENSE_EXPIRY"] == "WARN"


def test_sanctions_on_company_or_contact_blocks() -> None:
    for over in (
        {"legal_name": "Baihe Orchid Logistics Limited"},
        {"contact_name": "Baihe Orchid Logistics Limited"},
    ):
        out = engine.assess_profile(facts(**over), SANCTIONS, ["BD"], Thresholds())
        assert out.recommendation == "BLOCK" and out.score == 0
        assert engine.risk_summary(out.checks) == "FAIL"


def supplier(**over: object) -> engine.ProfileFacts:
    base: dict[str, object] = {
        "role": "SUPPLIER",
        "legal_name": "Ningbo Brightline Co., Ltd",
        "license_expiry": None,
        "doc_types": frozenset({"BUSINESS_LICENSE", "BANK_PROOF"}),
        "holder_name": "Ningbo Brightline Co., Ltd",
        "swift_country": "CN",
    }
    base.update(over)
    return facts(**base)


def test_supplier_holder_account_type_and_country() -> None:
    assert set(run(supplier()).values()) == {"PASS"}
    assert run(supplier(holder_name="Chen Wei"))["KYB_HOLDER_NAME"] == "WARN"
    assert run(supplier(holder_name="Chen Wei"))["KYB_ACCOUNT_TYPE"] == "WARN"
    assert (
        run(supplier(holder_name="宁波明线有限公司", legal_name="宁波明线有限公司"))[
            "KYB_ACCOUNT_TYPE"
        ]
        == "PASS"
    )
    assert run(supplier(swift_country="US"))["KYB_COUNTRY"] == "WARN"
    assert run(supplier(swift_country="HK"))["KYB_COUNTRY"] == "PASS"
    assert "LICENSE_EXPIRY" not in run(supplier())
