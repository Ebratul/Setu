"""Fixes from the P20 security review."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.registry import ToolContext, default_registry
from app.audit import write_audit
from app.audit.mask import clean_payload
from app.audit.verify import MALFORMED, verify_lines
from app.auth.deps import CurrentUser
from app.db import session as db_session
from app.db.enums import Role
from app.db.models import AuditLog
from tests.audit.test_scheme_verify import KEY, make


def test_control_characters_ints_and_big_numbers_are_made_safe() -> None:
    out = clean_payload({"note": "a\x00b\x07c", "phone": 8801712345678, "big": 2**60, "n": 7})
    assert "\x00" not in out["note"] and out["phone"] == "[redacted:PHONE]"
    assert out["big"] == str(2**60) and out["n"] == 7


def test_a_float_in_a_forged_export_is_malformed_not_a_crash() -> None:
    lines = make(3)
    lines[1]["payload"]["score"] = 0.5
    report = verify_lines(lines, KEY.public_key())
    assert (report.broken_seq, report.reason) == (2, MALFORMED)


def test_a_partial_export_reports_how_many_seqs_are_absent() -> None:
    lines = make(30)
    for i in (25, 12, 5):
        del lines[i]
    report = verify_lines(lines, KEY.public_key(), contiguous=False)
    assert report.ok and report.missing_seqs == 3
    assert verify_lines(lines, KEY.public_key()).ok is False  # the strict default catches it


@pytest.mark.db
def test_tool_audit_survives_a_rollback_and_a_long_hostile_tool_name(migrated_db: str) -> None:
    ctx_user = CurrentUser(
        uuid.uuid4(), "x@demo.setu", "X", Role.BUYER, "en", None
    )  # no DB row needed: the call is refused before any lookup
    engine = db_session.get_engine()
    hostile = "a" * 60
    with Session(engine) as turn:
        ctx = ToolContext(caller="llm", user=ctx_user, db=turn)
        out = default_registry().guard(hostile, {"x": "bad\x00arg"}, ctx)
        assert not out.ok
        turn.rollback()  # the chat turn is aborted
    with Session(engine) as s:
        rows = s.scalars(select(AuditLog).where(AuditLog.actor == "llm")).all()
    assert len(rows) == 1 and rows[0].action.startswith("TOOL:") and len(rows[0].action) <= 64
    assert "\x00" not in str(rows[0].payload)


@pytest.mark.db
def test_ts_is_taken_after_the_lock_so_it_never_runs_backwards(migrated_db: str) -> None:
    with Session(db_session.get_engine()) as s:
        a = write_audit(s, actor="system", action="A", tier=0, params={}, result="OK")
        b = write_audit(s, actor="system", action="B", tier=0, params={}, result="OK")
        s.commit()
        t = {r.seq: r.ts for r in s.scalars(select(AuditLog))}
    assert t[b] >= t[a] and t[a] <= datetime.now(UTC)
