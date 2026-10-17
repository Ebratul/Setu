"""FR-6.2 / SR-6 hash registry. Admin (and judge) listing and stats; the simulated lender-facing
check (JSON for a hash, a document or identity fields; multipart for a file)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user
from app.config import get_settings
from app.db.enums import RegistryPurpose, RegistryStatus, Role
from app.db.session import get_db
from app.errors import Forbidden, PayloadTooLarge
from app.schemas.registry import (
    DocumentRegistryOut,
    LenderCheckIn,
    LenderCheckOut,
    RegistryList,
    RegistryStatsOut,
)
from app.services import registry

router = APIRouter(tags=["registry"])

Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]


def _admin_reader(user: CurrentUser) -> None:
    if user.role not in (Role.ADMIN, Role.JUDGE):
        raise Forbidden("the registry listing is for admins and judges")


@router.get("/registry", response_model=RegistryList)
def list_registry(
    db: Db,
    user: User,
    status: RegistryStatus | None = None,
    result: Literal["EXACT_DUPLICATE", "NEAR_DUPLICATE"] | None = None,
    purpose: RegistryPurpose | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RegistryList:
    """Registered documents: hash prefixes and minimal metadata. `result` keeps entries that
    blocked at least one exact or near duplicate."""
    _admin_reader(user)
    return registry.list_entries(db, status, result, purpose, limit, offset)


@router.get("/registry/stats", response_model=RegistryStatsOut)
def registry_stats(db: Db, user: User) -> RegistryStatsOut:
    _admin_reader(user)
    return registry.stats(db)


@router.post("/registry/lender-check", response_model=LenderCheckOut)
def lender_check(body: LenderCheckIn, db: Db, user: User) -> LenderCheckOut:
    """A simulated institution asks whether a document is already registered elsewhere. Returns
    the result, what it is registered for and when; never a buyer, price or deal."""
    return registry.lender_check(db, user, body)


@router.post("/registry/lender-check/file", response_model=LenderCheckOut)
def lender_check_file(
    db: Db,
    user: User,
    lender_id: Annotated[str, Form(max_length=64)],
    file: Annotated[UploadFile, File(description="The document to look up (PDF, at most 10 MB)")],
) -> LenderCheckOut:
    limit = get_settings().document_max_bytes
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge(f"file is larger than {limit // (1024 * 1024)} MB", "FILE_TOO_LARGE")
    return registry.lender_check(db, user, LenderCheckIn(lender_id=lender_id), file=data)


@router.get("/documents/{document_id}/registry", response_model=DocumentRegistryOut)
def document_registry(document_id: uuid.UUID, db: Db, user: User) -> DocumentRegistryOut:
    """Is this document registered, and does it clash with another context? Not for suppliers."""
    return registry.document_registry(db, user, document_id)
