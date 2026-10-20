import pytest

from app.domain import onboarding_kyb as k
from app.domain.kyb import SanctionEntry

LIST = (
    SanctionEntry("S1", ("Zhongtai Meridian Trading Co., Ltd.",)),
    SanctionEntry("S2", ("Zhao Meilin",)),
)


def facts(**over: object) -> k.OnboardingFacts:
    base: dict[str, object] = {
        "legal_name": "Padma Textile Imports Ltd",
        "license_name": None,
        "tax_id": "123456789",
        "country": "BD",
        "holder_name": "Padma Textile Imports Ltd",
        "account_type": "CORPORATE",
        "bank_country": "BD",
    }
    base.update(over)
    return k.OnboardingFacts(**base)  # type: ignore[arg-type]


def run(**over: object) -> k.OnboardingAssessment:
    return k.assess(facts(**over), LIST, ["BD", "CN"])


def status(a: k.OnboardingAssessment, code: str) -> str:
    return next(c.status for c in a.checks if c.code == code)


def test_clean_submission_auto_clears_with_full_score() -> None:
    a = run()
    assert a.recommendation == "AUTO_CLEAR" and a.score == 100
    assert all(c.status == "PASS" for c in a.checks)


def test_sanctions_hit_blocks_and_zeroes_the_score() -> None:
    a = run(legal_name="Zhongtai Meridian Trading Co Ltd", holder_name="Zhongtai Meridian Trading")
    assert a.recommendation == "BLOCK" and a.score == 0
    assert status(a, "SANCTIONS_SCREEN") == "FAIL"


def test_holder_name_alone_on_the_list_blocks() -> None:
    assert run(holder_name="Zhao Meilin").recommendation == "BLOCK"


def test_chinese_company_words_normalise() -> None:
    a = run(
        legal_name="Shaoxing Huaxin Textile Co Ltd", holder_name="Shaoxing Huaxin Textile 有限公司"
    )
    assert status(a, "HOLDER_NAME_MATCH") == "PASS"


def test_holder_mismatch_needs_review() -> None:
    a = run(holder_name="Completely Different Traders")
    assert status(a, "HOLDER_NAME_MATCH") == "FAIL" and a.recommendation == "NEEDS_REVIEW"
    assert a.score == 70


def test_personal_account_warns_and_skips_holder_match() -> None:
    a = run(account_type="PERSONAL", holder_name="Some Person")
    assert status(a, "ACCOUNT_TYPE") == "WARN" and a.recommendation == "NEEDS_REVIEW"
    assert all(c.code != "HOLDER_NAME_MATCH" for c in a.checks)


def test_licence_name_is_checked_only_when_given() -> None:
    assert all(c.code != "LICENSE_NAME_MATCH" for c in run().checks)
    assert status(run(license_name="Padma Textile Imports Limited"), "LICENSE_NAME_MATCH") == "PASS"
    assert status(run(license_name="Other Co"), "LICENSE_NAME_MATCH") == "FAIL"


@pytest.mark.parametrize(
    ("tin", "expected"),
    [("123456789", "PASS"), ("1234567890123", "PASS"), ("12345678", "FAIL"), ("12345A789", "FAIL")],
)
def test_bd_tax_id_format(tin: str, expected: str) -> None:
    assert status(run(tax_id=tin), "TAX_ID_FORMAT") == expected


def test_country_allow_list() -> None:
    a = run(country="US")
    assert status(a, "COUNTRY_ALLOWED") == "FAIL"
    assert status(run(bank_country="HK"), "BANK_COUNTRY") == "WARN"


def test_score_is_deterministic_and_clamped() -> None:
    a = run(holder_name="Nope", country="US", tax_id="1", bank_country="HK")
    assert 0 <= a.score <= 100 and a == run(
        holder_name="Nope", country="US", tax_id="1", bank_country="HK"
    )
