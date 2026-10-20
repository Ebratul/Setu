"""FR-8: the signed credit record of a completed deal, and a check that it is genuine."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.audit.keys import load_signing_key, public_pem
from app.auth.deps import CurrentUser, current_user
from app.db.session import get_db
from app.services import credit_record

router = APIRouter(prefix="/credit-records", tags=["credit-records"])
Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]


class CreditRecordOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulated: Literal[True] = True
    id: uuid.UUID
    deal_ref: str
    issued_at: datetime
    key_id: str
    payload: dict[str, Any]
    payload_hash: str
    signature: str
    hash_ok: bool
    signature_ok: bool
    verified: bool
    public_key_pem: str


@router.get("/{deal}", response_model=CreditRecordOut)
def get_record(deal: str, db: Db, user: User) -> CreditRecordOut:
    """The signed record of a completed deal (reference or id), with its verification result."""
    row = credit_record.for_deal(db, user, deal)
    hash_ok, sig_ok = credit_record.verify(row)
    return CreditRecordOut(
        id=row.id,
        deal_ref=str(row.payload.get("deal_ref", deal)),
        issued_at=row.issued_at,
        key_id=row.key_id,
        payload=row.payload,
        payload_hash=row.payload_hash,
        signature=row.signature,
        hash_ok=hash_ok,
        signature_ok=sig_ok,
        verified=hash_ok and sig_ok,
        public_key_pem=public_pem(load_signing_key().public_key()),
    )


class VerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]
    signature: str


class VerifyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulated: Literal[True] = True
    payload_hash: str
    verified: bool


@router.post("/verify", response_model=VerifyOut)
def verify(body: VerifyIn, user: User) -> VerifyOut:
    """Lender-style check of a record you hold: recompute the hash and verify the signature."""
    from app.audit.keys import verify_signature
    from app.security.audit import canonical_json, sha256_hex

    digest = sha256_hex(canonical_json(body.payload))
    ok = verify_signature(load_signing_key().public_key(), digest, body.signature)
    return VerifyOut(payload_hash=digest, verified=ok)
