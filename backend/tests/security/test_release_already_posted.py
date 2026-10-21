from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.errors import Conflict
from app.services import approvals


def test_a_ledger_collision_becomes_a_409_not_a_500(monkeypatch: pytest.MonkeyPatch) -> None:
    def collide(*_args: object) -> None:
        raise IntegrityError("insert", {}, Exception("duplicate key pk_ledger_entries"))

    monkeypatch.setattr(approvals, "_run", collide)
    db = MagicMock()
    with pytest.raises(Conflict) as err:
        approvals._execute(db, MagicMock(), MagicMock(), MagicMock(), "OWNER", datetime.now(UTC))
    assert err.value.status == 409
    assert err.value.code == "RELEASE_ALREADY_POSTED"
    db.rollback.assert_called_once()
