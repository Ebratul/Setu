"""The signed-in user's own account: profile, data export (masked) and a soft-delete request."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.ratelimit import check_limit
from app.auth.deps import has_mfa
from app.db.enums import Language, UserStatus
from app.db.models import AuditLog, Party, User
from app.errors import Conflict
from app.schemas.onboarding import AccountOut, AccountPatch, DeleteRequested
from app.services import onboarding


def account_out(db: Session, user: User) -> AccountOut:
    profile = onboarding.profile_of(db, user)
    party = db.get(Party, user.party_id) if user.party_id else None
    contact = ((profile.data if profile else None) or {}).get("contact") or {}
    return AccountOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,  # type: ignore[arg-type]
        language=user.language.value,  # type: ignore[arg-type]
        account_status=user.status.value,  # type: ignore[arg-type]
        auth_provider=user.auth_provider,
        mfa_enabled=has_mfa(user),
        terms_version=user.terms_version,
        terms_accepted_at=user.terms_accepted_at,
        party_name=party.legal_name if party else None,
        mobile_masked=contact.get("mobile_masked"),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def patch(db: Session, user: User, body: AccountPatch) -> AccountOut:
    if body.language is not None:
        user.language = Language(body.language)
    if body.full_name is not None:
        user.display_name = body.full_name
        profile = onboarding.profile_of(db, user)
        if profile is not None and (profile.data or {}).get("contact"):
            contact = {**profile.data["contact"], "full_name": body.full_name}
            profile.data = {**profile.data, "contact": contact}
    onboarding.audit(db, user, "onboarding.profile_saved", {"section": "account"})
    db.commit()
    return account_out(db, user)


def export(db: Session, user: User) -> dict[str, Any]:
    """Everything we hold about the caller, masked. Full sensitive values are never exported."""
    check_limit("account-export", str(user.id), 5, 3600)
    state = onboarding.state_for(db, user)
    seqs = db.scalars(
        select(AuditLog.action).where(AuditLog.actor_id == str(user.id)).order_by(AuditLog.seq)
    ).all()
    onboarding.audit(db, user, "account.export", {})
    db.commit()
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": account_out(db, user).model_dump(mode="json"),
        "onboarding": state.model_dump(mode="json"),
        "activity": {"audit_actions": list(seqs)},
        "note": "Sensitive numbers are masked in this export.",
    }


def delete_request(db: Session, user: User) -> DeleteRequested:
    if user.deleted_at is not None:
        raise Conflict("deletion was already requested", code="DELETE_ALREADY_REQUESTED")
    now = datetime.now(UTC)
    user.deleted_at = now
    user.status = UserStatus.SUSPENDED
    onboarding.audit(db, user, "account.delete_requested", {}, tier=2)
    db.commit()
    return DeleteRequested(deleted_at=now)
