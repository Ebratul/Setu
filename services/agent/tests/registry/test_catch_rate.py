"""Catch rate of the registry on the synthetic DUPLICATE_INVOICE packs (dev split only)."""

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.forensics import eval_registry
from app.forensics.pack_loader import GENERATED

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not (GENERATED / "manifest.jsonl").exists(), reason="no data/generated"),
]


def test_every_dev_duplicate_invoice_pack_is_caught(seeded_db: str, capsys) -> None:  # type: ignore[no-untyped-def]
    with Session(get_engine()) as db:
        result = eval_registry.run(db)
    stats = result["stats"]
    with capsys.disabled():
        print("\n" + eval_registry.render(result))
    assert stats["any"], "the dev split has DUPLICATE_INVOICE packs"
    assert result["missed"] == []
    assert all(stats["exact"]) and all(stats["near"])
