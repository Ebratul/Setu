import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.agent import persistence, runner
from app.auth.deps import CurrentUser, current_user
from app.db.session import get_db
from app.errors import Forbidden
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    MessageList,
    MessageOut,
    ThreadList,
    ThreadOut,
)

router = APIRouter(prefix="/chat", tags=["chat"])

Db = Annotated[Session, Depends(get_db)]
User = Annotated[CurrentUser, Depends(current_user)]

# No proxy buffering, no transforms: tokens must reach the browser as they are produced
# (Next.js rewrite, Vercel, nginx).
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, db: Db, user: User) -> ChatResponse:
    """One chat turn with the Setu agent (read-only tools; nothing moves money). Simulated data."""
    return runner.chat(db, user, body)


@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def chat_stream(body: ChatRequest, db: Db, user: User) -> StreamingResponse:
    """Server-Sent Events: `meta`, `tool_start`, `tool_end`, `token`, `final`, `error`."""
    runner.validate(db, user, body)
    return StreamingResponse(
        runner.stream(user, body), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.get("/threads", response_model=ThreadList)
def threads(db: Db, user: User, user_id: uuid.UUID | None = None) -> ThreadList:
    """The caller's own chat threads, newest first."""
    if user_id is not None and user_id != user.id:
        raise Forbidden("you can only list your own chat threads")
    return ThreadList(
        threads=[
            ThreadOut(
                id=t.id,
                title=t.title,
                language=t.language,
                deal_id=t.deal_id,
                tokens_used=t.tokens_used,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in persistence.list_threads(db, user)
        ]
    )


@router.get("/threads/{thread_id}/messages", response_model=MessageList)
def messages(thread_id: uuid.UUID, db: Db, user: User) -> MessageList:
    """Messages of one of the caller's threads (tool results are stored masked)."""
    thread = persistence.get_thread(db, user, thread_id)
    return MessageList(
        thread_id=thread.id,
        messages=[
            MessageOut(
                seq=m.seq, role=m.role, content=m.content, created_at=m.created_at, meta=m.meta
            )
            for m in persistence.list_messages(db, thread)
        ],
    )
