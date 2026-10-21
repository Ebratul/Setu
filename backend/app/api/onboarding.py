"""Self-service onboarding (P30). The caller has a verified Neon sign-in but may not have a Setu
account yet, so these routes use the Neon identity, not `current_user` (except the document
download routes, which also serve admins). The server picks role and status; a client-sent user id
is never read. Field errors come back as 422 `VALIDATION_FAILED` with `errors[{field, code}]`."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.friendly import FriendlyRoute
from app.api.ratelimit import ip_of
from app.auth import neon
from app.auth.deps import CurrentUser, lenient_user, local_user, verified_identity
from app.config import get_settings
from app.db.enums import VerificationDocType
from app.db.models import User
from app.db.session import get_db
from app.errors import Forbidden, NotFound, PayloadTooLarge
from app.schemas.onboarding import (
    BusinessIn,
    ConsentIn,
    ContactIn,
    OnboardingState,
    PhoneSent,
    PhoneVerifyIn,
    RoleIn,
    UrlOut,
    VerificationDocumentOut,
)
from app.services import onboarding, onboarding_docs, onboarding_phone

router = APIRouter(prefix="/onboarding", tags=["onboarding"], route_class=FriendlyRoute)

Db = Annotated[Session, Depends(get_db)]


def _identity(request: Request) -> neon.NeonIdentity:
    if get_settings().auth_mode != "neon":
        raise NotFound("not available in demo mode")
    return verified_identity(request)


Identity = Annotated[neon.NeonIdentity, Depends(_identity)]


def _applicant(db: Db, identity: Identity) -> User:
    return onboarding.account_user(db, identity)


Applicant = Annotated[User, Depends(_applicant)]


@router.get("/me", response_model=OnboardingState)
def me(db: Db, identity: Identity) -> OnboardingState:
    """Where the caller stands. 200 with `account_status: null` before a role is chosen."""
    user = local_user(db, identity)
    if user is not None and user.deleted_at is not None:
        raise Forbidden("this account is suspended", code="ACCOUNT_SUSPENDED")
    return onboarding.state_for(db, user)


@router.post("/role", response_model=OnboardingState)
def choose_role(body: RoleIn, request: Request, db: Db, identity: Identity) -> OnboardingState:
    """Create the account in PENDING_PROFILE. ADMIN needs an allowlisted email, JUDGE an invite
    code (403 ROLE_NOT_ALLOWED / INVALID_INVITE_CODE); changing it after step 1 is a 409."""
    return onboarding.choose_role(db, identity, body, ip_of(request))


@router.put("/contact", response_model=OnboardingState)
def contact(body: ContactIn, db: Db, user: Applicant) -> OnboardingState:
    return onboarding.save_contact(db, user, body)


@router.post("/phone/send", response_model=PhoneSent)
def phone_send(db: Db, user: Applicant) -> PhoneSent:
    """Send a 6-digit code to the saved mobile. `demo_code` is in the response only when
    DEMO_MODE=true. 429 OTP_RATE_LIMIT after 3 sends in 10 minutes."""
    return onboarding_phone.send(db, user)


@router.post("/phone/verify", response_model=OnboardingState)
def phone_verify(body: PhoneVerifyIn, db: Db, user: Applicant) -> OnboardingState:
    """410 OTP_EXPIRED, 423 OTP_LOCKED after 5 wrong codes, 400 OTP_INVALID otherwise."""
    return onboarding_phone.verify(db, user, body.code)


@router.put("/business", response_model=OnboardingState)
def business(body: BusinessIn, db: Db, user: Applicant) -> OnboardingState:
    """Buyer or supplier business details (the body shape follows the account type)."""
    return onboarding.save_business(db, user, body)


@router.post("/documents", response_model=VerificationDocumentOut, status_code=201)
def upload_document(
    db: Db,
    user: Applicant,
    type: Annotated[VerificationDocType, Form(description="Document type")],
    file: Annotated[UploadFile, File(description="PDF, PNG or JPG, at most 4 MB")],
) -> VerificationDocumentOut:
    limit = get_settings().document_max_bytes
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge(f"file is larger than {limit // (1024 * 1024)} MB", "FILE_TOO_LARGE")
    return onboarding_docs.add(db, user, type, file.filename, data)


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, db: Db, user: Applicant) -> Response:
    onboarding_docs.remove(db, user, document_id)
    return Response(status_code=204)


@router.get("/documents/{document_id}/url", response_model=UrlOut)
def document_url(
    document_id: uuid.UUID, db: Db, user: Annotated[CurrentUser, Depends(lenient_user)]
) -> UrlOut:
    """Short-lived signed link, for the owner or an administrator."""
    url, expires = onboarding_docs.signed_url(db, user, document_id)
    return UrlOut(url=url, expires_at=expires)


@router.get("/documents/{document_id}/file")
def document_file(
    document_id: uuid.UUID,
    token: str,
    db: Db,
    user: Annotated[CurrentUser, Depends(lenient_user)],
) -> Response:
    doc, data = onboarding_docs.fetch(db, user, document_id, token)
    safe = doc.original_name.encode("ascii", "replace").decode().replace('"', "")
    return Response(
        content=data,
        media_type=doc.mime,
        headers={
            "Content-Disposition": f'attachment; filename="{safe}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'",
            "Referrer-Policy": "no-referrer",
            "Cache-Control": "private, no-store",
        },
    )


@router.put("/consent", response_model=OnboardingState)
def consent(body: ConsentIn, db: Db, user: Applicant) -> OnboardingState:
    return onboarding.save_consent(db, user, body)


@router.post("/submit", response_model=OnboardingState)
def submit(db: Db, user: Applicant) -> OnboardingState:
    """Needs every earlier step; runs the automated checks and moves the account to
    PENDING_VERIFICATION (admins: ACTIVE once TOTP and consent are done)."""
    return onboarding.submit(db, user)
