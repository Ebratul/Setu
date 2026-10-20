"""Signed, hash-chained audit history (scheme setu-audit-v2) and Ed25519-signed credit records.

Signing key: the configured AUDIT_SIGNING_KEY if set, otherwise a dev key generated on first seed
run and kept in the git-ignored `keys/audit_dev_ed25519.key`. Ed25519 signatures are
deterministic, so re-seeding with the same key reproduces identical rows.
"""

from dataclasses import dataclass
from datetime import datetime

from app.audit.keys import key_id, load_signing_key, sign_hash
from app.audit.mask import clean_payload
from app.audit.writer import PendingEntry, build_chain
from app.db.enums import Actor, DealStatus
from app.db.models import AuditLog, CreditRecord
from app.security.audit import canonical_json, sha256_hex
from seed.alerts_approvals import APPROVAL_T2, APPROVAL_T3, approvals
from seed.common import Ctx, Row, Rows, sid
from seed.deals import DEALS, MAIN_DEAL, DealSpec, deal_id
from seed.parties import HUAMENG, PARTY_NAMES


@dataclass(frozen=True, slots=True)
class Event:
    ts: datetime
    actor: Actor
    action: str
    tier: int
    params: Row
    result: str
    bound_hash: str | None = None  # approval rows: the approval's binding hash


def _deal_events(ctx: Ctx, spec: DealSpec) -> list[Event]:
    ref = spec.ref
    events = [
        Event(
            ctx.at(spec.opened, 10, 0),
            Actor.USER,
            "DEAL_CREATED",
            0,
            {"deal_ref": ref, "goods_value": str(spec.goods_value.amount)},
            "OK",
        )
    ]
    first_release_done = False
    for seq, (plan, amount) in enumerate(
        zip(spec.milestones, spec.milestone_amounts(), strict=True), start=1
    ):
        p = {"deal_ref": ref, "milestone_seq": seq, "amount": str(amount.amount), "currency": "USD"}
        if plan.funded is not None:
            events.append(
                Event(ctx.at(plan.funded, 11, 0), Actor.USER, "ESCROW_FUNDED", 1, p, "SIMULATED_OK")
            )
        if plan.released is not None:
            ts = ctx.at(plan.released, 11, 0)
            if not first_release_done and spec.ref == "SETU-2025-0011":
                # first ever release to this supplier: one-tap Tier 2 approval
                events.append(
                    Event(
                        ctx.at(plan.released, 10, 30),
                        Actor.SYSTEM,
                        "APPROVAL_REQUESTED",
                        2,
                        p,
                        "PENDING",
                    )
                )
                events.append(
                    Event(
                        ctx.at(plan.released, 10, 42),
                        Actor.USER,
                        "APPROVAL_GRANTED",
                        2,
                        p,
                        "APPROVED",
                    )
                )
                events.append(Event(ts, Actor.SYSTEM, "MILESTONE_RELEASED", 2, p, "SIMULATED_OK"))
            else:
                events.append(Event(ts, Actor.SYSTEM, "MILESTONE_RELEASED", 1, p, "SIMULATED_OK"))
            first_release_done = True
    if spec.status == DealStatus.COMPLETED and spec.completed_on is not None:
        done = {"deal_ref": ref, "on_time": spec.on_time, "disputes": spec.disputes}
        events.append(
            Event(ctx.at(spec.completed_on, 12, 0), Actor.SYSTEM, "DEAL_COMPLETED", 0, done, "OK")
        )
        events.append(
            Event(
                ctx.at(spec.completed_on, 12, 1),
                Actor.SYSTEM,
                "CREDIT_RECORD_ISSUED",
                0,
                done,
                "SIGNED",
            )
        )
    if spec.status == DealStatus.DISPUTED:
        p = {"deal_ref": ref, "milestone_seq": 3}
        events.append(
            Event(
                ctx.at(spec.milestones[2].due + 2, 9, 15), Actor.USER, "DISPUTE_OPENED", 0, p, "OK"
            )
        )
        events.append(
            Event(
                ctx.at(spec.milestones[2].due + 2, 9, 16),
                Actor.SYSTEM,
                "ESCROW_FROZEN",
                0,
                p,
                "FROZEN",
            )
        )
    return events


def _main_deal_events(ctx: Ctx) -> list[Event]:
    approval_hashes = {r["key"]: r["params_hash"] for r in approvals(ctx)}
    return [
        Event(
            ctx.at(-8, 14, 35),
            Actor.SYSTEM,
            "DOCUMENT_CHECKED",
            0,
            {"deal_ref": MAIN_DEAL, "doc": "proforma_invoice.pdf"},
            "PASSED",
        ),
        Event(
            ctx.at(-1, 14, 35),
            Actor.SYSTEM,
            "DOCUMENT_CHECKED",
            0,
            {"deal_ref": MAIN_DEAL, "doc": "production_photos"},
            "PASSED",
        ),
        Event(
            ctx.at(-3, 16, 0),
            Actor.SYSTEM,
            "KYB_CHECKED",
            0,
            {"supplier": HUAMENG, "deal_ref": "SETU-2026-0005"},
            "WARNING",
        ),
        Event(
            ctx.at(0, 9, 30),
            Actor.SYSTEM,
            "APPROVAL_REQUESTED",
            2,
            {"deal_ref": MAIN_DEAL, "milestone_seq": 1, "reason": "FX_RATE_LOCK"},
            "PENDING",
            approval_hashes[APPROVAL_T2],
        ),
        Event(
            ctx.at(0, 9, 45),
            Actor.SYSTEM,
            "APPROVAL_REQUESTED",
            3,
            {"deal_ref": MAIN_DEAL, "action": "CHANGE_BENEFICIARY"},
            "PENDING",
            approval_hashes[APPROVAL_T3],
        ),
    ]


def events(ctx: Ctx) -> list[Event]:
    evs: list[Event] = []
    for spec in DEALS:
        if spec.status in (DealStatus.COMPLETED, DealStatus.DISPUTED, DealStatus.FUNDED):
            evs += _deal_events(ctx, spec)
    evs += _main_deal_events(ctx)
    return sorted(evs, key=lambda e: (e.ts, e.action, canonical_json(e.params)))


def credit_payload(ctx: Ctx, spec: DealSpec) -> Row:
    return {
        "record_type": "setu.completed_deal.v1",
        "simulated": True,
        "deal_ref": spec.ref,
        "buyer": PARTY_NAMES[spec.buyer],
        "supplier": PARTY_NAMES[spec.supplier],
        "amount": str(spec.goods_value.amount),
        "currency": "USD",
        "milestones": [str(m.amount) for m in spec.milestone_amounts()],
        "opened_on": ctx.day(spec.opened).isoformat(),
        "completed_on": ctx.day(spec.completed_on or 0).isoformat(),
        "on_time": spec.on_time,
        "disputes": spec.disputes,
    }


def build(ctx: Ctx) -> Rows:
    key = load_signing_key(create_dev_key=True)
    kid = key_id(key.public_key())
    chain = build_chain(
        key,
        [
            PendingEntry(
                ts=e.ts,
                actor_type=e.actor.value,
                actor_id="system" if e.actor == Actor.SYSTEM else "demo-user",
                deal_id=deal_id(str(e.params["deal_ref"])) if "deal_ref" in e.params else None,
                action=e.action,
                tier=e.tier,
                decision=e.result,
                payload=clean_payload(
                    {**e.params, **({"binding_hash": e.bound_hash} if e.bound_hash else {})}
                ),
            )
            for e in events(ctx)
        ],
    )
    audit_rows = list(chain)
    credit_rows = []
    for spec in DEALS:
        if spec.status != DealStatus.COMPLETED or spec.completed_on is None:
            continue
        payload = credit_payload(ctx, spec)
        digest = sha256_hex(canonical_json(payload))
        credit_rows.append(
            {
                "id": sid("credit_record", spec.ref),
                "deal_id": deal_id(spec.ref),
                "buyer_id": sid("party", spec.buyer),
                "supplier_id": sid("party", spec.supplier),
                "amount": spec.goods_value.amount,
                "currency": "USD",
                "on_time": bool(spec.on_time),
                "dispute_count": spec.disputes,
                "completed_on": ctx.day(spec.completed_on),
                "payload": payload,
                "payload_hash": digest,
                "signature": sign_hash(key, digest),
                "key_id": kid,
                "issued_at": ctx.at(spec.completed_on, 12, 1),
            }
        )
    return [(CreditRecord, credit_rows), (AuditLog, audit_rows)]
