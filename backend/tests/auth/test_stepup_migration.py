import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from app.config import AGENT_DIR
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.db

PREVIOUS = "f1b8d2c4a6e3"


def test_stepup_migration_downgrades_and_upgrades_cleanly(seeded_db: str) -> None:  # noqa: F811
    cfg = Config(str(AGENT_DIR / "alembic.ini"))
    engine = create_engine(seeded_db)

    def cols() -> set[str]:
        return {c["name"] for c in inspect(engine).get_columns("approval_requests")}

    assert "requested_by_user_id" in cols()
    assert "stepup_challenges" in inspect(engine).get_table_names()
    command.downgrade(cfg, PREVIOUS)
    assert "requested_by_user_id" not in cols()
    assert "stepup_challenges" not in inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "requested_by_user_id" in cols()
    assert "stepup_challenges" in inspect(engine).get_table_names()
    engine.dispose()
