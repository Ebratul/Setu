"""One chat turn: resolve the thread, run the graph, persist messages, shape the response.

Used by POST /chat (blocking) and POST /chat/stream (SSE). Errors inside a turn never surface a
stack trace: the blocking call raises a DomainError, the stream emits an `error` event.
"""

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, cast

import structlog
from fastapi.sse import format_sse_event
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tracers import LangChainTracer
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session, sessionmaker

from app.agent.graph import build_graph
from app.agent.intents import detect_language
from app.agent.nodes import AgentDeps
from app.agent.persistence import (
    add_tokens,
    append_message,
    create_thread,
    get_checkpointer,
    get_thread,
    resolve_deal,
)
from app.agent.state import AgentState, Lang
from app.auth.deps import CurrentUser
from app.config import get_settings
from app.db.enums import ChatRole
from app.db.models import ChatThread
from app.db.session import get_engine
from app.errors import DomainError, ServiceUnavailable
from app.llm import tracing
from app.schemas.chat import ChatRequest, ChatResponse, ToolCallOut, UsageOut
from app.security.privacy_gateway import mask_for_storage

log = structlog.get_logger("setu.chat")

TRACE_TAGS = ["setu", "phase-P08"]
TRACE_ROLES = frozenset({"ADMIN", "JUDGE"})
RESPOND_NODE = "respond"
STREAM_ERROR = {"code": "agent_error", "message": "Something went wrong. Nothing was changed."}


@dataclass(slots=True)
class Turn:
    thread: ChatThread
    language: Lang
    deal_id: str | None
    run_id: uuid.UUID
    config: RunnableConfig
    graph_input: dict[str, Any]
    callbacks: list[Any]


def _graph() -> CompiledStateGraph:
    return build_graph(checkpointer=get_checkpointer())


def validate(db: Session, user: CurrentUser, req: ChatRequest) -> None:
    """Ownership and deal checks that must fail as HTTP errors before a stream starts."""
    if req.thread_id is not None:
        get_thread(db, user, req.thread_id)
    if req.deal_id is not None:
        resolve_deal(db, user, req.deal_id)


def start_turn(db: Session, user: CurrentUser, req: ChatRequest) -> Turn:
    deal = resolve_deal(db, user, req.deal_id) if req.deal_id else None
    if req.thread_id is not None:
        thread = get_thread(db, user, req.thread_id)
    else:
        lang = req.language or detect_language(req.message) or _user_lang(user)
        thread = create_thread(db, user, req.message, lang, deal.id if deal else None)
    language = cast(
        Lang, req.language or detect_language(req.message) or str(thread.language) or "en"
    )
    append_message(db, thread, ChatRole.USER, req.message, {"language": language})
    db.commit()

    run_id = uuid.uuid4()
    callbacks = tracing.callbacks()
    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(thread.id),
            "deps": AgentDeps(user=user, db=db, thread_id=str(thread.id)),
        },
        "callbacks": callbacks,
        "run_id": run_id,
        "run_name": "setu-chat",
        "tags": list(TRACE_TAGS),
        "metadata": {"user_role": str(user.role), "thread_id": str(thread.id)},
        "recursion_limit": 40,
    }
    graph_input = {
        "messages": [HumanMessage(content=req.message, id=str(uuid.uuid4()))],
        "language": language,
        "deal_id": deal.reference if deal else None,
        "thread_tokens_before": thread.tokens_used or 0,
    }
    return Turn(thread, language, graph_input["deal_id"], run_id, config, graph_input, callbacks)


def _user_lang(user: CurrentUser) -> Lang:
    return cast(Lang, user.language if user.language in ("en", "bn", "zh") else "en")


def finish_turn(db: Session, user: CurrentUser, turn: Turn, values: dict[str, Any]) -> ChatResponse:
    state = AgentState.model_validate(values)
    for rec, res in zip(state.tool_calls_made, state.tool_results, strict=False):
        append_message(
            db,
            turn.thread,
            ChatRole.TOOL,
            mask_for_storage(res["payload"]),
            {
                "tool": rec["name"],
                "ok": rec["ok"],
                "args_summary": rec["args_summary"],
                "error_code": rec["error_code"],
            },
        )
    answer = state.answer or ""
    usage = state.token_usage
    append_message(
        db,
        turn.thread,
        ChatRole.ASSISTANT,
        answer,
        {
            "intent": state.intent,
            "model": state.model_used,
            "route_source": state.route_source,
            "usage": dict(usage),
            "stopped": state.stop_reason,
            "injection_flags": state.injection_flags,
            "run_id": str(turn.run_id),
        },
    )
    add_tokens(db, turn.thread, usage["total_tokens"])
    db.commit()
    log.info(
        "chat_turn",
        thread_id=str(turn.thread.id),
        intent=state.intent,
        model=state.model_used,
        tools=len(state.tool_calls_made),
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        thread_total=turn.thread.tokens_used,
        stopped=state.stop_reason,
    )
    trace_url = _finish_trace(turn, state, user)
    return ChatResponse(
        thread_id=turn.thread.id,
        answer=answer,
        intent=state.intent,
        model_used=state.model_used,
        language=turn.language,
        tool_calls=[
            ToolCallOut(name=r["name"], args_summary=r["args_summary"], ok=r["ok"])
            for r in state.tool_calls_made
        ],
        usage=UsageOut(
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            thread_total=turn.thread.tokens_used,
            thread_budget=get_settings().thread_token_budget,
        ),
        stopped=state.stop_reason,
        trace_url=trace_url,
    )


def _finish_trace(turn: Turn, state: AgentState, user: CurrentUser) -> str | None:
    if not turn.callbacks:
        return None
    for cb in turn.callbacks:
        if isinstance(cb, LangChainTracer):
            cb.wait_for_futures()
    client = tracing.langsmith_client()
    if client is not None:
        client.flush()
    tracing.tag_run(
        turn.run_id, [*TRACE_TAGS, f"intent:{state.intent}", f"model:{state.model_used}"]
    )
    return tracing.run_url(turn.run_id) if str(user.role) in TRACE_ROLES else None


def abort_turn(
    db: Session, turn: Turn, graph: CompiledStateGraph, streamed_chars: int, reason: str
) -> None:
    """Charge the thread for what an unfinished turn already spent (failure or client
    disconnect), so the token budget can't be bypassed; close the turn with a marker message.
    Never raises."""
    try:
        db.rollback()
        try:
            values = graph.get_state(turn.config).values
            spent = int(AgentState.model_validate(values).token_usage["total_tokens"])
        except Exception:
            spent = 0
        spent += streamed_chars // 4  # respond output streamed before its usage was checkpointed
        meta = {"aborted": reason, "tokens": spent}
        append_message(db, turn.thread, ChatRole.ASSISTANT, "", meta)
        add_tokens(db, turn.thread, spent)
        db.commit()
        log.info("chat_turn_aborted", thread_id=str(turn.thread.id), reason=reason, tokens=spent)
    except Exception as exc:
        db.rollback()
        log.warning("chat_abort_failed", error=type(exc).__name__)


def chat(db: Session, user: CurrentUser, req: ChatRequest) -> ChatResponse:
    turn = start_turn(db, user, req)
    graph = _graph()
    try:
        graph.invoke(turn.graph_input, turn.config)
    except Exception as exc:
        log.warning("chat_failed", thread_id=str(turn.thread.id), error=type(exc).__name__)
        abort_turn(db, turn, graph, 0, "error")
        raise ServiceUnavailable("the assistant is unavailable; nothing was changed") from exc
    values = graph.get_state(turn.config).values
    return finish_turn(db, user, turn, values)


# --- SSE ------------------------------------------------------------------------------------


def sse(event: str, data: dict[str, Any]) -> str:
    return format_sse_event(event=event, data_str=json.dumps(data, ensure_ascii=False, default=str))


def stream(user: CurrentUser, req: ChatRequest) -> Iterator[str]:
    """SSE frames: meta → tool_start/tool_end* → token* → final (or error)."""
    engine = get_engine()
    if engine is None:
        yield sse("error", {"code": "unavailable", "message": "database is not configured"})
        return
    with sessionmaker(engine, expire_on_commit=False)() as db:
        try:
            yield from _stream_turn(db, user, req)
        except DomainError as exc:
            db.rollback()
            yield sse("error", {"code": exc.title.lower().replace(" ", "_"), "message": exc.detail})
        except Exception as exc:
            db.rollback()
            log.warning("chat_stream_failed", error=type(exc).__name__)
            yield sse("error", STREAM_ERROR)


def _stream_turn(db: Session, user: CurrentUser, req: ChatRequest) -> Iterator[str]:
    turn = start_turn(db, user, req)
    graph = _graph()
    streamed: list[str] = []
    finished = False
    try:
        yield from _graph_events(turn, graph, streamed)
        values = graph.get_state(turn.config).values
        response = finish_turn(db, user, turn, values)
        finished = True
    finally:
        # Runs on errors and on GeneratorExit (client disconnected mid-stream).
        if not finished:
            abort_turn(db, turn, graph, len("".join(streamed)), "disconnected_or_error")
    sent = "".join(streamed)
    if response.answer.startswith(sent) and len(response.answer) > len(sent):
        yield sse("token", {"text": response.answer[len(sent) :]})
    yield sse("final", response.model_dump(mode="json"))


def _graph_events(turn: Turn, graph: CompiledStateGraph, streamed: list[str]) -> Iterator[str]:
    for mode, chunk in graph.stream(
        turn.graph_input, turn.config, stream_mode=["updates", "messages"]
    ):
        if mode == "messages":
            msg, meta = chunk
            if meta.get("langgraph_node") == RESPOND_NODE and isinstance(msg, AIMessageChunk):
                text = msg.text if isinstance(msg.content, list) else str(msg.content)
                if text:
                    streamed.append(text)
                    yield sse("token", {"text": text})
            continue
        for node, raw_update in (chunk or {}).items():
            update: dict[str, Any] = raw_update if isinstance(raw_update, dict) else {}
            if node == "router":
                yield sse(
                    "meta",
                    {
                        "thread_id": str(turn.thread.id),
                        "intent": update.get("intent"),
                        "model": update.get("model_used"),
                        "language": turn.language,
                        "simulated": True,
                    },
                )
            elif node == "agent":
                for m in update.get("messages", []):
                    if isinstance(m, AIMessage):
                        for call in m.tool_calls:
                            yield sse("tool_start", {"name": call["name"], "id": call.get("id")})
            elif node == "tools":
                done = update.get("tool_calls_made", [])[-len(update.get("messages", [])) or 0 :]
                for rec in done:
                    yield sse(
                        "tool_end",
                        {
                            "name": rec["name"],
                            "id": rec["id"],
                            "ok": rec["ok"],
                            "args_summary": rec["args_summary"],
                            "error_code": rec["error_code"],
                        },
                    )
