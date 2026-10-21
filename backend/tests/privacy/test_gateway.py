"""Privacy Gateway: detectors, obfuscation, vault, masking round trips, transparency records."""

import logging
import pickle

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.privacy.detectors import ACCT, AMT, EMAIL, IBAN, NAME, NID, PHONE, SWIFT, detect
from app.privacy.gateway import PrivacyGateway, StreamUnmasker
from app.privacy.vault import Vault

DOC = (
    "Seller bank details\nAccount holder: Chen Wei\nA/C 6222 0021 4455 7788\n"
    "Director NID 1990123456789, mobile +880 1711-223344\nTotal USD 11,200.00"
)


def kinds(text: str, **kw: object) -> list[str]:
    return [h.type for h in detect(text, **kw)]  # type: ignore[arg-type]


def test_tc11_document_reaches_the_model_only_as_tokens() -> None:
    gw = PrivacyGateway()
    [sent], call = gw.protect([HumanMessage(DOC)], node="extract")
    for raw in ("1990123456789", "6222 0021 4455 7788", "1711-223344", "Chen Wei", "11,200.00"):
        assert raw not in sent.content
    assert call.stats.leaked_count == 0
    assert set(call.stats.masked_by_type) == {"NID", "PHONE", "ACCT", "NAME", "AMT"}
    restored = gw.unmask(sent.content)
    assert "1990123456789" in restored and "6222 0021 4455 7788" in restored


@pytest.mark.parametrize(
    "text",
    [
        "০১৭১১ ২২৩ ৩৪৪",  # Bangla digits, spaced (11 digits once normalised)
        "0 1 7 1 1 2 2 3 3 4 4",
        "01​711‍223344",  # zero-width characters
        "+8801711223344",
        "+880 1711-223344",
        "০১৭১১২২৩৩৪৪",
    ],
)
def test_obfuscated_bd_phone_numbers_are_found(text: str) -> None:
    assert PHONE in kinds(text), text
    assert "⟦PHONE_1⟧" in PrivacyGateway().mask_text(text)


def test_obfuscation_flag_is_set_for_spaced_and_bangla_digits() -> None:
    [h] = detect("0 1 7 1 1 2 2 3 3 4 4")
    assert h.type == PHONE and h.obfuscated
    [plain] = detect("01711223344")
    assert not plain.obfuscated


def test_each_identifier_type() -> None:
    assert kinds("NID: 1990123456789") == [NID]
    assert kinds("জাতীয় পরিচয়পত্র নম্বর ১৯৯০১২৩৪৫৬৭৮৯") == [NID]
    assert kinds("+86 138 0013 8000") == [PHONE]
    assert kinds("account no 62220021445577") == [ACCT]
    assert kinds("账号:6222002144557788") == [ACCT]
    assert kinds("হিসাব নম্বর 6222002144557788") == [ACCT]
    assert kinds("Account no.: SIM-CN-9713-****-5170") == [ACCT]
    assert kinds("write to rahima@example.com") == [EMAIL]
    assert kinds("SWIFT: ICBKCNBJNBO") == [SWIFT]
    assert kinds("GB82 WEST 1234 5698 7654 32") == [IBAN]
    assert kinds("Total BDT 1,560 and ৳ 2,000 and 500 টাকা") == [AMT, AMT, AMT]


def test_no_false_positives_on_ordinary_numbers() -> None:
    assert detect("Order SETU-2026-0001, 3 pieces, PI-2026-0042, due 2026-11-07") == []
    assert detect("Account opened 2026-11-02") == []
    assert detect("ICBKCNBJNBO") == []  # a SWIFT-shaped word without a SWIFT/BIC context
    assert IBAN not in kinds("GB82 WEST 1234 5698 7654 33")  # bad IBAN checksum


def test_amounts_can_be_left_unmasked() -> None:
    assert kinds("USD 11,200.00", mask_amounts=False) == []
    gw = PrivacyGateway(mask_amounts=False)
    assert gw.mask_text("USD 11,200.00") == "USD 11,200.00"


def test_known_names_are_masked_without_context() -> None:
    gw = PrivacyGateway(known={NAME: {"Chen Wei"}})
    assert gw.mask_text("Pay chen  wei today") == "Pay ⟦NAME_1⟧ today"


def test_same_value_same_token_and_numbering_in_order() -> None:
    gw = PrivacyGateway()
    out = gw.mask_text("A/C 62220021445577 then +8801711223344 and again A/C 6222 0021 4455 77")
    assert out == "A/C ⟦ACCT_1⟧ then ⟦PHONE_1⟧ and again A/C ⟦ACCT_1⟧"
    assert gw.mask_text("01711223344") == "⟦PHONE_1⟧"  # +880 and local form are one value


def test_requests_have_independent_vaults() -> None:
    a, b = PrivacyGateway(), PrivacyGateway()
    assert a.mask_text("A/C 11112222") == "A/C ⟦ACCT_1⟧"
    assert b.mask_text("A/C 33334444") == "A/C ⟦ACCT_1⟧"
    assert a.unmask("⟦ACCT_1⟧") == "11112222" and b.unmask("⟦ACCT_1⟧") == "33334444"


def test_tokens_from_earlier_turns_are_never_reused() -> None:
    gw = PrivacyGateway()
    gw.vault.reserve_from("earlier ⟦ACCT_1⟧ and ⟦ACCT_2⟧")
    assert gw.mask_text("A/C 55556666") == "A/C ⟦ACCT_3⟧"
    assert gw.unmask("⟦ACCT_1⟧", unresolved=True) == "[protected ACCT]"


def test_vault_is_never_serialised_or_logged(caplog: pytest.LogCaptureFixture) -> None:
    gw = PrivacyGateway()
    with caplog.at_level(logging.DEBUG):
        gw.mask_text("A/C 62220021445577")
        gw.protect([HumanMessage("A/C 62220021445577")], node="x")
        repr(gw.vault)
    assert "62220021445577" not in caplog.text
    assert "62220021445577" not in repr(gw.vault)
    with pytest.raises(TypeError):
        pickle.dumps(Vault())


def test_transparency_record_holds_masked_text_only() -> None:
    gw = PrivacyGateway()
    _, call = gw.protect(
        [SystemMessage("be brief"), HumanMessage("NID 1990123456789 A/C 6222002144557788")],
        node="respond",
        model="m",
    )
    call.output = "ok ⟦NID_1⟧"
    blob = call.payload + (call.output or "")
    assert "1990123456789" not in blob and "6222002144557788" not in blob
    assert call.stats.masked_by_type == {"NID": 1, "ACCT": 1} and call.stats.leaked_count == 0
    assert call.stats.chars_sent == len(call.payload)


def test_json_tool_results_mask_money_keys_and_text() -> None:
    gw = PrivacyGateway()
    out = gw.mask_payload(
        '{"total_bdt": "11200.00", "first_shortfall": {"amount": 1560, "on": "2026-11-07"},'
        ' "duty_rate": 0.25, "note": "call +8801711223344"}'
    )
    assert "11200" not in out and "1560" not in out and "0.25" in out and "2026-11-07" in out
    assert gw.unmask("⟦AMT_1⟧ / ⟦AMT_2⟧") == "11,200.00 / 1,560"


def test_structured_output_amounts_are_restored_by_code() -> None:
    gw = PrivacyGateway()
    gw.mask_text("Total: USD 11,200.00")
    assert gw.unmask({"total": "⟦AMT_1⟧", "items": ["⟦AMT_1⟧"], "n": 3}) == {
        "total": "11,200.00",
        "items": ["11,200.00"],
        "n": 3,
    }


def test_disabled_gateway_counts_what_would_leak() -> None:
    gw = PrivacyGateway(enabled=False)
    _, call = gw.protect([HumanMessage("A/C 6222002144557788")], node="x")
    assert call.stats.leaked_count == 1 and call.stats.masked_by_type == {}


def test_stream_unmasker_never_emits_half_a_token() -> None:
    gw = PrivacyGateway()
    gw.mask_text("A/C 62220021445577")
    u = StreamUnmasker(gw)
    pieces = [u.feed(c) for c in ["Send to ⟦AC", "CT_1", "⟧ now"]] + [u.flush()]
    assert "".join(pieces) == "Send to 62220021445577 now"
    assert all("⟦" not in p for p in pieces)


@pytest.mark.parametrize(
    "text",
    [
        "Account\n1234567890123",  # label and value on separate lines
        "pay 6222 0021 4455 7788 now",  # unlabelled 16 digits
        "my id is 1990123456789",
        "call 01711.223.344",
        "call 01711  223344",
        "call +880 (1711) 223344",
        "call 8613800138000",
        "\u0410\u0441count no 62220021445577",  # Cyrillic look-alike letters in the label
    ],
)
def test_review_bypasses_are_closed(text: str) -> None:
    assert detect(text), text


def test_literal_tokens_in_untrusted_text_are_never_restored() -> None:
    gw = PrivacyGateway()
    gw.mask_text("A/C 62220021445577")
    assert gw.unmask("see [ACCT_1] and \u3010ACCT_1\u3011") == "see [ACCT_1] and \u3010ACCT_1\u3011"
    out = gw.mask_payload('{"note": "our account \u27e6ACCT_1\u27e7 is unchanged"}')
    assert "\u27e6" not in out and gw.unmask(out).count("62220021445577") == 0


def test_identifier_keys_in_json_are_masked_without_context() -> None:
    gw = PrivacyGateway()
    out = gw.mask_payload(
        '{"bank_account": "9999888877776666", "phone": "8613800138000", "holder_name": "Li Na",'
        ' "account_type": "CORPORATE", "invoice_no": "HX-1"}'
    )
    for raw in ("9999888877776666", "8613800138000", "Li Na"):
        assert raw not in out
    assert "CORPORATE" in out and "HX-1" in out


def test_tool_args_get_plain_amounts_back() -> None:
    gw = PrivacyGateway()
    tok = gw.mask("11200.00", key="total_bdt")
    assert gw.unmask({"amount": tok}, canonical=True) == {"amount": "11200"}
    assert gw.unmask(tok) == "11,200.00"


def test_a_surviving_identifier_blocks_the_call() -> None:
    from app.privacy.gateway import PrivacyBlocked

    gw = PrivacyGateway()
    gw.mask_message = lambda m: m  # type: ignore[method-assign]  # simulate a masking bug
    with pytest.raises(PrivacyBlocked):
        gw.protect([HumanMessage("A/C 6222002144557788")], node="x")
    assert gw.calls[0].stats.leaked_count == 1


# --- P30: Bangladesh mobile, trade licence / IRC / TIN, USCC -------------------------------------

BIZ_DOC = (
    "Buyer: Padma Textile Ltd\nTrade licence no: TL-2024/00123\nIRC No BD-IRC-998877\n"
    "TIN: 123456789012\nSeller USCC 91350100M000100Y43\nContact 01712345678 / +8801812345678"
)


def test_business_identifiers_and_bd_mobiles_never_reach_the_model() -> None:
    from app.privacy.detectors import BIZID

    gw = PrivacyGateway()
    [sent], call = gw.protect([HumanMessage(BIZ_DOC)], node="onboarding")
    for raw in (
        "TL-2024/00123",
        "BD-IRC-998877",
        "123456789012",
        "91350100M000100Y43",
        "01712345678",
        "+8801812345678",
    ):
        assert raw not in sent.content, raw
    assert call.stats.leaked_count == 0
    assert {BIZID, PHONE} <= set(call.stats.masked_by_type)
    assert "91350100M000100Y43" in gw.unmask(sent.content)


@pytest.mark.parametrize(
    "text",
    [
        "Trade Licence No. TL-2024/00123",
        "trade license number: TL-2024/00123",
        "IRC: BD-IRC-998877",
        "Import Registration Certificate No BD-IRC-998877",
        "TIN 123456789012",
        "BIN: 000123456-0101",
        "统一社会信用代码\uff1a91350100M000100Y43",
        "USCC: 91350100M000100Y43",
        "91350100M000100Y43",  # bare, but the check character is valid
    ],
)
def test_business_identifier_detector(text: str) -> None:
    from app.privacy.detectors import BIZID

    assert BIZID in kinds(text), text


@pytest.mark.parametrize(
    "text",
    ["91350100M000100Y44", "licence expires 2027-10-21", "Order SETU-2026-0001", "TIN is required"],
)
def test_business_identifier_detector_ignores_lookalikes(text: str) -> None:
    from app.privacy.detectors import BIZID

    assert BIZID not in kinds(text), text


@pytest.mark.parametrize(
    "text", ["01712345678", "+8801712345678", "+880 1712-345678", "০১৭১২৩৪৫৬৭৮", "01312345678"]
)
def test_bd_mobile_forms_are_phones(text: str) -> None:
    assert kinds(text) == [PHONE], text


def test_bd_mobile_lookalikes_are_not_phones() -> None:
    assert PHONE not in kinds("01212345678")  # 012 is not an operator prefix
    assert PHONE not in kinds("order 0171234567")  # one digit short


def test_business_id_field_names_are_masked_in_structured_payloads() -> None:
    gw = PrivacyGateway()
    masked = gw.mask(
        {
            "trade_license_no": "TL-1",
            "irc_no": "IRC-1",
            "uscc": "X",
            "tin": "9",
            "mobile": "01712345678",
            "trade_license_no_masked": "****0001",
            "legal_name": "Padma",
        }
    )
    assert all(
        masked[k].startswith("⟦") for k in ("trade_license_no", "uscc", "tin", "mobile", "irc_no")
    )
    assert masked["legal_name"] == "Padma" and masked["trade_license_no_masked"] == "****0001"


def test_audit_payloads_redact_business_ids() -> None:
    from app.audit.mask import clean_payload

    out = clean_payload({"note": "TIN: 123456789012 and USCC 91350100M000100Y43", "uscc": "abc"})
    assert "123456789012" not in str(out) and "91350100M000100Y43" not in str(out)
    assert out["uscc"] == "[redacted:BIZID]"
