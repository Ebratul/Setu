"""Supplier directory and profile (KYB badge, scorecard). Buyers see their own suppliers only."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, require_analysis_reader
from app.db.session import get_db
from app.schemas.kyb import SupplierList, SupplierProfile
from app.services import suppliers

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[CurrentUser, Depends(require_analysis_reader)]


@router.get("", response_model=SupplierList)
def list_suppliers(db: Db, user: Reader, buyer_id: uuid.UUID | None = None) -> SupplierList:
    """Suppliers with KYB badge, score, completed deals and on-time rate."""
    return suppliers.list_suppliers(db, user, buyer_id)


@router.get("/{supplier_id}", response_model=SupplierProfile)
def supplier_profile(
    supplier_id: uuid.UUID, db: Db, user: Reader, buyer_id: uuid.UUID | None = None
) -> SupplierProfile:
    """Company details, bank accounts, deal history, scorecard trend and the latest KYB result."""
    return suppliers.profile(db, user, supplier_id, buyer_id)
