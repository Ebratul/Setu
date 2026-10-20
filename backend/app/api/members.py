"""Party members and invites (owner of the party, or ADMIN)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, current_user
from app.db.session import get_db
from app.schemas.onboarding import InviteIn, MemberList, MemberOut
from app.services import members

router = APIRouter(prefix="/parties", tags=["members"])

Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]


@router.get("/{party_id}/members", response_model=MemberList)
def list_members(party_id: uuid.UUID, db: Db, user: User) -> MemberList:
    return members.list_members(db, user, party_id)


@router.post("/{party_id}/members", response_model=MemberOut, status_code=201)
def invite_member(party_id: uuid.UUID, body: InviteIn, db: Db, user: User) -> MemberOut:
    """Pre-create the account; it is linked to the invitee's Neon sign-in (same verified email)."""
    return members.invite(db, user, party_id, body)


@router.delete("/{party_id}/members/{user_id}", status_code=204)
def remove_member(party_id: uuid.UUID, user_id: uuid.UUID, db: Db, user: User) -> Response:
    members.remove(db, user, party_id, user_id)
    return Response(status_code=204)
