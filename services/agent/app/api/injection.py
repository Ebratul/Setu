"""Prompt-injection defence: live attack console, scoreboard and the admin event list (P19).

Admins and judges only. The console runs the real defence layers on a sandbox (no deal, no money,
no model call); "Defences: OFF" disables layers 2, 4 and 5 only, never the risk engine.
"""

import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user
from app.db.models import Deal, InjectionEvent
from app.db.session import get_db
from app.errors import Conflict, Forbidden, NotFound
from app.schemas.injection import (
    ConsoleRunIn,
    ConsoleRunOut,
    DetectionStats,
    GalleryList,
    GalleryOut,
    InjectionEventList,
    InjectionEventOut,
    ModeStats,
    ScoreboardOut,
)
from app.security.audit import write_audit
from app.security.injection import console, suite
from app.security.injection.gallery import GALLERY

RERUN_LOCK = threading.Lock()
router = APIRouter(prefix="/security/injection", tags=["security"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]


def _require_reader(user: CurrentUser) -> None:
    if not user.reads_all:
        raise Forbidden("only admins and judges can use the security console")


@router.get("/gallery", response_model=GalleryList)
def gallery(user: User) -> GalleryList:
    _require_reader(user)
    return GalleryList(items=[GalleryOut(**asdict(g)) for g in GALLERY])


@router.post("/run", response_model=ConsoleRunOut)
async def run(body: ConsoleRunIn, db: Db, user: User) -> ConsoleRunOut:
    """Run one attack through the layers. The only side effects are a console-tagged event and
    its signed audit row."""
    _require_reader(user)
    if body.attack_id is None and not (body.text and body.text.strip()):
        raise NotFound("choose an attack or type some text")
    return await run_in_threadpool(console.run, db, user, body)


def _scoreboard(data: dict[str, Any] | None, split: str) -> ScoreboardOut:
    if data is None:
        return ScoreboardOut(available=False, split=split)
    return ScoreboardOut(
        available=True,
        split=data["split"],
        generated_at=datetime.fromisoformat(data["generated_at"]),
        attacks=data["attacks"],
        modes={k: ModeStats(**v) for k, v in data["modes"].items()},
        detection=DetectionStats(**{k: data["detection"][k] for k in DetectionStats.model_fields}),
        layer_attribution=data.get("layer_attribution", {}),
        notes=data.get("notes", ""),
    )


@router.get("/scoreboard", response_model=ScoreboardOut)
def scoreboard(user: User) -> ScoreboardOut:
    """The saved dev-split numbers (attack success OFF vs ON, detection recall, false positives).
    The test split is never served from here: P24 reports it."""
    _require_reader(user)
    return _scoreboard(suite.load_saved("dev"), "dev")


@router.post("/scoreboard/rerun", response_model=ScoreboardOut)
async def rerun(user: User) -> ScoreboardOut:
    """Re-run the dev-split suite now (about ten seconds) and save the result."""
    _require_reader(user)
    if not RERUN_LOCK.acquire(blocking=False):
        raise Conflict("the suite is already running")
    try:
        data = await run_in_threadpool(suite.run_attack_suite, "dev")
    finally:
        RERUN_LOCK.release()
    return _scoreboard(data, "dev")


def _out(e: InjectionEvent, ref: str | None) -> InjectionEventOut:
    return InjectionEventOut(
        id=e.id,
        ts=e.ts,
        kind=e.kind,  # type: ignore[arg-type]
        source=e.source,
        origin=e.origin,
        rules=list(e.rules or []),
        score=e.score,
        snippet=e.snippet,
        attack_style=e.attack_style,
        tool=e.tool,
        action_taken=e.action_taken,
        layer=e.layer,
        defences_on=e.defences_on,
        flags_deal=e.flags_deal,
        resolved=e.resolved_at is not None,
        deal_id=e.deal_id,
        deal_reference=ref,
        document_id=e.document_id,
        audit_seq=e.audit_seq,
    )


@router.get("/events", response_model=InjectionEventList)
def events(
    db: Db,
    user: User,
    style: str | None = Query(None, max_length=32),
    source: str | None = Query(None, max_length=16),
    origin: str | None = Query(None, max_length=16),
    limit: int = Query(100, ge=1, le=500),
) -> InjectionEventList:
    """Injection events, newest first; each links to its signed audit entry (`audit_seq`)."""
    _require_reader(user)
    where: list[Any] = []
    if style:
        where.append(InjectionEvent.attack_style == style)
    if source:
        where.append(InjectionEvent.source == source)
    if origin:
        where.append(InjectionEvent.origin == origin)
    rows = db.execute(
        select(InjectionEvent, Deal.reference)
        .join(Deal, Deal.id == InjectionEvent.deal_id, isouter=True)
        .where(*where)
        .order_by(InjectionEvent.ts.desc())
        .limit(limit)
    ).all()
    total = db.scalar(select(func.count()).select_from(InjectionEvent).where(*where)) or 0

    def tally(col: Any) -> dict[str, int]:
        return {
            str(k or "none"): int(n)
            for k, n in db.execute(select(col, func.count()).where(*where).group_by(col)).all()
        }

    return InjectionEventList(
        items=[_out(e, ref) for e, ref in rows],
        total=int(total),
        by_style=tally(InjectionEvent.attack_style),
        by_source=tally(InjectionEvent.source),
    )


@router.post("/events/{event_id}/resolve", response_model=InjectionEventOut)
def resolve(event_id: uuid.UUID, db: Db, user: User) -> InjectionEventOut:
    """An admin has reviewed the event: the deal's layer 3 flag from it is released."""
    if user.role.value != "ADMIN":
        raise Forbidden("only an admin can resolve an injection event")
    row = db.get(InjectionEvent, event_id)
    if row is None:
        raise NotFound("event not found")
    if row.resolved_at is None:
        write_audit(
            db,
            actor="user",
            action="INJECTION_RESOLVED",
            tier=3,
            params={"event_id": str(row.id), "deal_id": str(row.deal_id) if row.deal_id else None,
                    "by": str(user.id)},
            result="FLAG_RELEASED",
            deal_id=row.deal_id,
        )  # fmt: skip
        row.resolved_at = datetime.now(UTC)
        db.commit()
    ref = db.scalar(select(Deal.reference).where(Deal.id == row.deal_id)) if row.deal_id else None
    return _out(row, ref)
