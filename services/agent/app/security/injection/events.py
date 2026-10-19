"""Layer 3 - capability control (always on) and the event log.

The agent can only PROPOSE money actions. A detection in content linked to a deal sets
`flags_deal`: the deal's next money action is then Tier 3 (`deal_flagged` feeds the risk engine's
`instruction_from_document`), a FRAUD alert is raised and a signed audit row is written. Nothing
here consults the defences switch: detection may be off for an evaluation, this never is.
Only rule codes and a masked, truncated snippet are stored, never the document.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Deal, Document, InjectionEvent
from app.security.audit import record_event, write_audit
from app.security.injection.detector import Detection
from app.security.tiers import Tier

log = structlog.get_logger("setu.injection")

ACTION_FLAGGED = "FLAGGED_DEAL_TIER3"
ACTION_IGNORED = "IGNORED"
ACTION_BLOCKED_TOOL = "TOOL_DROPPED"


def deal_flagged(db: Session, deal_id: uuid.UUID) -> bool:
    """True while any unresolved detection flags the deal (instruction_from_document)."""
    return (
        db.scalar(
            select(InjectionEvent.id)
            .where(
                InjectionEvent.deal_id == deal_id,
                InjectionEvent.flags_deal.is_(True),
                InjectionEvent.resolved_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def record(
    db: Session | None,
    *,
    kind: str,
    source: str,
    rules: list[str],
    score: int = 0,
    snippet: str = "",
    action_taken: str,
    layer: int | None = None,
    deal_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    tool: str | None = None,
    attack_style: str | None = None,
    origin: str = "live",
    defences_on: bool = True,
    flags_deal: bool = False,
    alert: bool = True,
    durable: bool = False,
) -> InjectionEvent | None:
    """Audit row + event row (+ FRAUD alert when flagging a deal). The caller commits.
    Without a database (the evaluation harness) only the in-memory audit trail is written."""
    if durable and db is not None:
        # Own session, committed at once: the flag must survive a later rollback of the chat
        # turn (client disconnect, model error), or an attacker could abort their way past it.
        from app.db.session import get_engine

        with Session(get_engine(), expire_on_commit=False) as own:
            row = record(
                own, kind=kind, source=source, rules=rules, score=score, snippet=snippet,
                action_taken=action_taken, layer=layer, deal_id=deal_id, document_id=document_id,
                user_id=user_id, tool=tool, attack_style=attack_style, origin=origin,
                defences_on=defences_on, flags_deal=flags_deal, alert=alert,
            )  # fmt: skip
            own.commit()
            return row
    action = "INJECTION_DETECTED" if kind == "DETECTED" else "INJECTION_BLOCKED_TOOL"
    params: dict[str, Any] = {
        "source": source,
        "rules": rules,
        "tool": tool,
        "deal_id": str(deal_id) if deal_id else None,
        "document_id": str(document_id) if document_id else None,
    }
    refs = {"user_id": str(user_id) if user_id else "", "origin": origin}
    record_event(
        actor="system",
        action=action,
        tier=int(Tier.T3),
        params=params,
        result=action_taken,
        refs=refs,
    )
    if db is None:
        return None
    seq = write_audit(
        db,
        actor="system",
        action=action,
        tier=int(Tier.T3),
        params=params,
        result=action_taken,
        deal_id=deal_id,
    )
    row = InjectionEvent(
        id=uuid.uuid4(),
        ts=datetime.now(UTC),
        kind=kind,
        source=source,
        origin=origin,
        rules=rules[:12],
        score=score,
        snippet=snippet[:200],
        attack_style=attack_style,
        tool=tool,
        action_taken=action_taken,
        layer=layer,
        defences_on=defences_on,
        flags_deal=flags_deal and deal_id is not None,
        deal_id=deal_id,
        document_id=document_id,
        user_id=user_id,
        audit_seq=seq,
    )
    db.add(row)
    db.flush()
    if row.flags_deal and alert and deal_id is not None:
        deal = db.get(Deal, deal_id)
        if deal is not None:
            from app.services import alerts

            alerts.raise_injection_alert(db, deal, source=source, rules=rules)
    return row


def record_detection(
    db: Session | None,
    detection: Detection,
    *,
    deal_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    origin: str = "live",
    attack_style: str | None = None,
    alert: bool = True,
    defences_on: bool = True,
) -> InjectionEvent | None:
    return record(
        db,
        kind="DETECTED",
        source=detection.source,
        rules=list(detection.matched_rules),
        score=detection.score,
        snippet=detection.snippet,
        action_taken=ACTION_FLAGGED if deal_id else ACTION_IGNORED,
        layer=3 if deal_id else 2,
        deal_id=deal_id,
        document_id=document_id,
        user_id=user_id,
        attack_style=attack_style,
        origin=origin,
        flags_deal=deal_id is not None,
        alert=alert,
        defences_on=defences_on,
    )


def record_document(
    db: Session, doc: Document, detections: list[Detection], *, alert: bool = False
) -> None:
    """Pipeline hook: one event per placement, once per document and placement. The document's own
    FRAUD alert usually exists already (`alert=False`)."""
    for d in detections:
        seen = db.scalar(
            select(InjectionEvent.id)
            .where(
                InjectionEvent.document_id == doc.id,
                InjectionEvent.source == d.source,
                InjectionEvent.kind == "DETECTED",
                InjectionEvent.resolved_at.is_(None),
            )
            .limit(1)
        )
        if seen is None:
            record_detection(db, d, deal_id=doc.deal_id, document_id=doc.id, alert=alert)
