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
