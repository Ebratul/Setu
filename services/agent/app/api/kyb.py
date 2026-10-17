"""FR-4 supplier KYB endpoints. Deterministic checks; every verify run is audited."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, require_analysis_reader, require_writer
from app.db.session import get_db
from app.schemas.kyb import KybResult, KybStatusOut
from app.services import kyb

router = APIRouter(prefix="/kyb", tags=["kyb"])

Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require_analysis_reader)]
Writer = Annotated[CurrentUser, Depends(require_writer)]


@router.post("/verify/{supplier_id}", response_model=KybResult)
def verify_supplier(
    supplier_id: uuid.UUID,
    db: Db,
    user: Writer,
    deal_id: Annotated[
        str | None,
        Query(
            min_length=1, max_length=64, pattern=r"^[A-Za-z0-9-]+$", description="Reference or id"
        ),
    ] = None,
) -> KybResult:
    """Run the KYB checks now and save the result, history, audit entry and alerts."""
    return kyb.verify(db, user, supplier_id, deal_id)


@router.get("/{supplier_id}", response_model=KybStatusOut)
def supplier_kyb(supplier_id: uuid.UUID, db: Db, user: Reader) -> KybStatusOut:
    """Latest KYB result and run history (read-only; judges allowed)."""
    return kyb.status_of(db, user, supplier_id)
