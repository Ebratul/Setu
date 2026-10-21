"""Party members: who may act for a business and with which party-level role. Owners manage their
own party; admins manage any. A user with a party and no `party_members` row counts as OWNER."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.deps import CurrentUser, ensure_verified
from app.db.enums import KybStatus, Language, MemberRole, PartyKind, Role, UserStatus
from app.db.models import Party, PartyMember, User
from app.errors import Conflict, DomainError, Forbidden, NotFound
from app.schemas.onboarding import InviteIn, MemberList, MemberOut


def _manager(db: Session, actor: CurrentUser, party_id: uuid.UUID, *, lock: bool = False) -> Party:
    stmt = select(Party).where(Party.id == party_id)
    party = db.scalar(stmt.with_for_update() if lock else stmt)
    allowed = actor.role == Role.ADMIN or (
        actor.party_id == party_id and actor.member_role == MemberRole.OWNER
    )
    if not allowed:
        raise Forbidden("only the owner of this business or an administrator can manage members")
    if party is None:
        raise NotFound("party not found")
    return party


def _roles(db: Session, party_id: uuid.UUID) -> list[tuple[User, MemberRole]]:
    users = db.scalars(
        select(User).where(User.party_id == party_id).order_by(User.created_at, User.email)
    ).all()
    rows = {
        m.user_id: m.member_role
        for m in db.scalars(select(PartyMember).where(PartyMember.party_id == party_id))
    }
    return [(u, rows.get(u.id, MemberRole.OWNER)) for u in users]


def _out(user: User, role: MemberRole) -> MemberOut:
    return MemberOut(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        member_role=role.value,  # type: ignore[arg-type]
        status=user.status.value,  # type: ignore[arg-type]
        signed_in_once=user.auth_subject is not None or user.is_demo,
        created_at=user.created_at,
    )


def list_members(db: Session, actor: CurrentUser, party_id: uuid.UUID) -> MemberList:
    _manager(db, actor, party_id)
    return MemberList(party_id=party_id, items=[_out(u, r) for u, r in _roles(db, party_id)])


def invite(db: Session, actor: CurrentUser, party_id: uuid.UUID, body: InviteIn) -> MemberOut:
    ensure_verified(actor)
    party = _manager(db, actor, party_id)
    if party.kind == PartyKind.LENDER:
        raise DomainError("members cannot be added to a lender", "MEMBER_PARTY_KIND")
    if party.kyb_status in (KybStatus.PENDING, KybStatus.FAILED):
        raise Conflict("the business has not been verified yet", code="PARTY_NOT_VERIFIED")
    email = body.email.lower()
    existing = db.scalar(select(User.id).where(User.email.ilike(email)))
    if existing is not None:
        raise Conflict("this email address already has an account", code="EMAIL_IN_USE")
    user = User(
        id=uuid.uuid4(),
        email=email,
        display_name=body.display_name,
        role=Role(party.kind.value),
        language=Language.EN,
        party_id=party.id,
        is_demo=False,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    db.add(
        PartyMember(
            id=uuid.uuid4(),
            party_id=party.id,
            user_id=user.id,
            member_role=MemberRole(body.member_role),
        )
    )
    write_audit(
        db,
        actor="user",
        action="member.invited",
        tier=2,
        params={
            "party_id": str(party.id),
            "user_id": str(user.id),
            "member_role": body.member_role,
        },
        result="ok",
        actor_id=str(actor.id),
    )
    db.commit()
    return _out(user, MemberRole(body.member_role))


def remove(db: Session, actor: CurrentUser, party_id: uuid.UUID, user_id: uuid.UUID) -> None:
    ensure_verified(actor)
    party = _manager(db, actor, party_id, lock=True)
    members = _roles(db, party.id)
    target = next(((u, r) for u, r in members if u.id == user_id), None)
    if target is None:
        raise NotFound("member not found")
    user, role = target
    owners = [u for u, r in members if r == MemberRole.OWNER and u.status != UserStatus.SUSPENDED]
    if role == MemberRole.OWNER and len(owners) <= 1:
        raise Conflict("a business needs at least one owner", code="LAST_OWNER")
    row = db.scalar(
        select(PartyMember).where(PartyMember.party_id == party.id, PartyMember.user_id == user.id)
    )
    if row is not None:
        db.delete(row)
    user.party_id = None  # without a party, the missing-row-means-OWNER default cannot apply
    user.status = UserStatus.SUSPENDED
    write_audit(
        db,
        actor="user",
        action="member.removed",
        tier=2,
        params={"party_id": str(party.id), "user_id": str(user.id), "member_role": role.value},
        result="ok",
        actor_id=str(actor.id),
    )
    db.commit()
