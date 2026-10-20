import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.config import AGENT_DIR
from tests.api.conftest import seeded_db  # noqa: F401  (fixture)

pytestmark = pytest.mark.db

PREVIOUS = "a9c4e7b2d5f8"
TABLES = {"sandbox_payments", "sandbox_payment_events"}


def test_sandbox_payment_tables_downgrade_and_upgrade_cleanly(seeded_db: str) -> None:  # noqa: F811
    cfg = Config(str(AGENT_DIR / "alembic.ini"))
    engine = create_engine(seeded_db)
    assert TABLES <= set(inspect(engine).get_table_names())
    command.downgrade(cfg, PREVIOUS)
    assert not TABLES & set(inspect(engine).get_table_names())
    command.upgrade(cfg, "head")
    assert TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_a_sandbox_payment_cannot_be_stored_as_real(seeded_db: str) -> None:  # noqa: F811
    engine = create_engine(seeded_db)
    with engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(text("UPDATE sandbox_payments SET simulated = false"))
        conn.execute(
            text(
                "INSERT INTO sandbox_payments (id, provider, simulated, deal_id, buyer_id,"
                " created_by_user_id, coverage, amount, currency, charge_amount, charge_currency,"
                " status, provider_order_id, request_id) SELECT gen_random_uuid(), 'X', false,"
                " d.id, d.buyer_id, u.id, 'NEXT_TRANCHE', 1, 'USD', 1, 'USD', 'CREATED', 'O', 'r'"
                " FROM deals d, users u LIMIT 1"
            )
        )
    engine.dispose()
