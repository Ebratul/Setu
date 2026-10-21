import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.config import AGENT_DIR
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.db

PREVIOUS = "e7a3c1d9b5f4"


def test_migration_upgrades_and_downgrades_cleanly(seeded_db: str) -> None:  # noqa: F811
    cfg = Config(str(AGENT_DIR / "alembic.ini"))
    engine = create_engine(seeded_db)

    def tables() -> set[str]:
        return set(inspect(engine).get_table_names())

    assert {"party_members", "onboarding_reviews"} <= tables()
    command.downgrade(cfg, PREVIOUS)
    assert not {"party_members", "onboarding_reviews"} & tables()
    cols = {c["name"] for c in inspect(engine).get_columns("parties")}
    assert not {"tax_id", "onboarded_at"} & cols
    command.upgrade(cfg, "head")
    assert {"party_members", "onboarding_reviews"} <= tables()
    cols = {c["name"] for c in inspect(engine).get_columns("parties")}
    assert {"tax_id", "onboarded_at"} <= cols
    engine.dispose()


HEAD_PREVIOUS = "b7d3e9a1c4f6"


def test_p30_migration_maps_statuses_both_ways(seeded_db: str) -> None:  # noqa: F811
    """Upgrade renames PENDING -> PENDING_VERIFICATION; downgrade folds the new values back."""
    from sqlalchemy import text

    cfg = Config(str(AGENT_DIR / "alembic.ini"))
    engine = create_engine(seeded_db)
    insert = (
        "INSERT INTO users (id, email, display_name, role, language, is_demo, status, mfa_enabled)"
        " VALUES (gen_random_uuid(), :e, 'T', 'BUYER', 'en', false, :s, false)"
    )
    command.downgrade(cfg, HEAD_PREVIOUS)  # P24 shape: PENDING exists, REJECTED does not
    with engine.begin() as c:
        c.execute(text(insert), {"e": "p24-pending@example.com", "s": "PENDING"})
        c.execute(text(insert), {"e": "p24-active@example.com", "s": "ACTIVE"})
        c.execute(  # the old email step-up set this flag; there is no TOTP secret column yet
            text(insert.replace("false, :s, false)", "false, :s, true)")),
            {"e": "p24-legacymfa@example.com", "s": "ACTIVE"},
        )
    with pytest.raises(Exception, match="ck_users_user_status"), engine.begin() as c:
        c.execute(text(insert), {"e": "p24-bad@example.com", "s": "REJECTED"})
    command.upgrade(cfg, "head")
    with engine.begin() as c:
        got = dict(
            c.execute(text("SELECT email, status FROM users WHERE email LIKE 'p24-%'")).all()
        )
        assert got == {
            "p24-pending@example.com": "PENDING_VERIFICATION",
            "p24-active@example.com": "ACTIVE",
            "p24-legacymfa@example.com": "ACTIVE",
        }
        flag = c.execute(
            text("SELECT mfa_enabled FROM users WHERE email = 'p24-legacymfa@example.com'")
        ).scalar_one()
        assert flag is False  # a flag without a secret is not two-factor
        for s in ("PENDING_PROFILE", "REJECTED"):
            c.execute(text(insert), {"e": f"p30-{s.lower()}@example.com", "s": s})
        cols = {c_["name"] for c_ in inspect(c).get_columns("users")}
        assert {"email_verified_at", "mfa_secret_encrypted", "terms_version", "deleted_at"} <= cols
        idx = {i["name"]: i for i in inspect(c).get_indexes("parties")}
        assert idx["uq_parties_kind_dedupe_key"]["unique"] is True
        assert {"onboarding_profiles", "verification_documents", "phone_verifications"} <= set(
            inspect(c).get_table_names()
        )
    command.downgrade(cfg, HEAD_PREVIOUS)
    with engine.begin() as c:
        got = dict(
            c.execute(
                text("SELECT email, status FROM users WHERE email LIKE 'p%@example.com'")
            ).all()
        )
        assert got["p24-pending@example.com"] == "PENDING"  # PENDING_VERIFICATION folds back
        assert got["p30-pending_profile@example.com"] == "PENDING"
        assert got["p30-rejected@example.com"] == "SUSPENDED"
        c.execute(text("DELETE FROM users WHERE email LIKE 'p%@example.com'"))
    command.upgrade(cfg, "head")
    engine.dispose()


def test_dedupe_key_is_unique_per_kind_only_when_set(seeded_db: str) -> None:  # noqa: F811
    import uuid

    from sqlalchemy.exc import IntegrityError

    from app.db.models import Party
    from app.db.session import batch_session

    key = "a" * 64

    def party(kind: str, dedupe: str | None) -> Party:
        return Party(
            id=uuid.uuid4(),
            code=f"P-{uuid.uuid4().hex[:10]}",
            kind=kind,
            legal_name="X",
            city="Dhaka",
            country="BD",
            first_seen_on=__import__("datetime").date.today(),
            dedupe_key=dedupe,
        )

    with batch_session() as s:  # many parties without a key are fine; one key per kind
        s.add_all(
            [
                party("BUYER", None),
                party("BUYER", None),
                party("BUYER", key),
                party("SUPPLIER", key),
            ]
        )
    with pytest.raises(IntegrityError), batch_session() as s:
        s.add(party("BUYER", key))
    with batch_session() as s:
        s.execute(text_delete())


def text_delete():
    from sqlalchemy import text

    return text("DELETE FROM parties WHERE dedupe_key = :k").bindparams(k="a" * 64)
