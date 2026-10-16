import pytest

from tests.conftest import unsafe_test_db_reason

MAIN = "postgresql://setu:setu@localhost:5435/setu"


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("postgresql://u:p@ep-x.neon.tech/setu_test", "not local"),
        ("postgresql://setu:setu@localhost:5435/setu", "does not end in '_test'"),
        ("postgresql://setu:setu@localhost:5435/setu_test", None),
    ],
)
def test_test_database_guard(url: str, reason: str | None) -> None:
    got = unsafe_test_db_reason(url, MAIN)
    assert (got is None) if reason is None else (reason in (got or ""))


def test_same_database_as_main_is_refused() -> None:
    main = "postgresql://setu:setu@localhost:5435/setu_test"
    assert unsafe_test_db_reason(main, main) == "test database is the same as DATABASE_URL"
