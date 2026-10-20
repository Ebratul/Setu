"""Record/replay for model calls (guided demo). Every model call is keyed by a hash of the masked
prompt (messages, bound tool names, structured-output schema) plus the model id. In replay the
recorded answer is returned, so a demo run is identical every time and works offline; in record
the real model is called and the answer is written under data/demo/fixtures/llm/.

Mode per call: off (plain model) | replay | record | live (a sandbox that switched "Use live AI" on,
budget-capped; falls back to replay when the budget is spent). The prompt is already masked by the
Privacy Gateway when it reaches this layer, and ids/timestamps that change per run are normalised
before hashing. A replay miss answers with the deterministic offline model and is noted, unless a
strict check is running (`pnpm demo:check`), which collects misses and fails on any.
"""

import hashlib
import json
import os
import re
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import structlog
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import ConfigDict

from app.config import get_settings

log = structlog.get_logger("setu.llm.replay")

Mode = Literal["off", "replay", "record", "live"]

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?")
_WRAP_ID = re.compile(r'(</?untrusted\b[^>]*?\bid=")[^"]*(")')
_RUN_ID = re.compile(r"\b(?:run|call|toolu|msg)_[A-Za-z0-9]{6,}")

_forced: ContextVar[Mode | None] = ContextVar("setu_replay_forced", default=None)
_misses: ContextVar[list[dict[str, Any]] | None] = ContextVar("setu_replay_misses", default=None)
_used: ContextVar[list[str] | None] = ContextVar("setu_replay_used", default=None)


class ReplayError(RuntimeError):
    pass


@dataclass(slots=True)
class StrictRun:
    """What a strict run saw: fixture keys hit and calls with no fixture."""

    hits: list[str] = field(default_factory=list)
    misses: list[dict[str, Any]] = field(default_factory=list)


@contextmanager
def strict_run() -> Iterator[StrictRun]:
    run = StrictRun()
    t1, t2 = _misses.set(run.misses), _used.set(run.hits)
    try:
        yield run
    finally:
        _misses.reset(t1)
        _used.reset(t2)


@contextmanager
def forced_mode(mode: Mode | None) -> Iterator[None]:
    token = _forced.set(mode)
    try:
        yield
    finally:
        _forced.reset(token)


def current_mode() -> Mode:
    forced = _forced.get()
    if forced is not None:
        return forced
    from app.demo.context import current_sandbox

    settings = get_settings()
    if settings.demo_record:
        return "record"
    sb = current_sandbox()
    if sb is not None:
        return "live" if sb.live_ai else "replay"
    return "replay" if settings.demo_replay else "off"


# --- keys & store ---------------------------------------------------------------------------


def _flatten(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in (None, "text"):
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)


def normalise(text: str) -> str:
    text = _WRAP_ID.sub(r"\1<id>\2", text)
    text = _UUID.sub("<uuid>", text)
    text = _TS.sub("<ts>", text)
    return _RUN_ID.sub("<call>", text)


def _canon_args(args: Any) -> Any:
    return json.loads(normalise(json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)))


def fixture_key(
    kind: str, model_id: str, messages: Sequence[BaseMessage], extra: Sequence[str] = ()
) -> str:
    canon = [
        {
            "t": m.type,
            "c": normalise(_flatten(m.content)),
            "tc": [
                {"n": tc["name"], "a": _canon_args(tc.get("args", {}))}
                for tc in (getattr(m, "tool_calls", None) or [])
            ],
        }
        for m in messages
    ]
    blob = json.dumps(
        {"k": kind, "m": model_id, "x": list(extra), "msgs": canon},
        sort_keys=True,
        ensure_ascii=False,
    )
    digest = hashlib.sha256(blob.encode()).hexdigest()
    debug = os.environ.get("SETU_DEMO_DEBUG_DIR")
    if (
        debug and get_settings().app_env != "prod"
    ):  # developer aid: the exact normalised prompt behind a key (never set in prod)
        Path(debug).mkdir(parents=True, exist_ok=True)
        (Path(debug) / f"{kind}-{digest[:12]}.json").write_text(blob, encoding="utf-8")
    return digest


def store_dir() -> Path:
    return get_settings().demo_fixtures_dir / "llm"


def fixture_path(key: str) -> Path:
    return store_dir() / f"{key[:24]}.json"


def load_fixture(key: str) -> dict[str, Any] | None:
    path = fixture_path(key)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if data.get("key") == key else None


def save_fixture(record: dict[str, Any]) -> None:
    path = fixture_path(record["key"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def list_fixtures() -> list[dict[str, Any]]:
    root = store_dir()
    if not root.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*.json"))]


def _summary(messages: Sequence[BaseMessage]) -> dict[str, str]:
    human = next((m for m in reversed(messages) if m.type == "human"), None)
    system = next((m for m in messages if m.type == "system"), None)
    return {
        "system": normalise(_flatten(system.content))[:160] if system else "",
        "last_user": normalise(_flatten(human.content))[:240] if human else "",
    }


def _usage(msg: AIMessage) -> dict[str, int] | None:
    u = getattr(msg, "usage_metadata", None)
    return dict(u) if u else None


def _spend_live() -> bool:
    from app.demo import sandbox
    from app.demo.context import current_sandbox

    sb = current_sandbox()
    return sb is not None and sandbox.spend_live_call(sb.id)


def _is_mock(model: BaseChatModel | None) -> bool:
    return model is None or type(model).__name__ == "MockChatModel"


# --- the model ------------------------------------------------------------------------------


class ReplayChatModel(BaseChatModel):
    """Wraps the real model (or None offline) and the deterministic fallback."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    model_id: str
    inner: Any = None
    fallback: BaseChatModel
    bound_tools: tuple[str, ...] = ()
    bound_defs: tuple[Any, ...] = ()

    @property
    def _llm_type(self) -> str:
        return "setu-replay"

    def bind_tools(
        self, tools: Sequence[Any], **kwargs: Any
    ) -> Runnable[LanguageModelInput, AIMessage]:
        names = tuple(
            t["name"] if isinstance(t, dict) else getattr(t, "name", str(t)) for t in tools
        )
        return self.model_copy(update={"bound_tools": names, "bound_defs": tuple(tools)})

    # -- helpers
    def _resolve(self, base: BaseChatModel) -> tuple[BaseChatModel, dict[str, Any]]:
        """The model (and call kwargs) to run `base` with its tools bound. Calls go straight to
        `_generate` / `_stream`, so streaming and callbacks behave as without the wrapper."""
        if not self.bound_defs:
            return base, {}
        bound = base.bind_tools(list(self.bound_defs))
        if isinstance(bound, BaseChatModel):
            return bound, {}
        return bound.bound, dict(bound.kwargs)  # type: ignore[attr-defined]

    def _record(self, key: str, kind: str, messages: Sequence[BaseMessage], response: dict) -> None:
        save_fixture(
            {
                "key": key,
                "kind": kind,
                "model": self.model_id,
                "tools": list(self.bound_tools),
                "source": "mock" if _is_mock(self.inner) else "real",
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "request": _summary(messages),
                "response": response,
            }
        )

    @staticmethod
    def _ai(response: dict) -> AIMessage:
        return AIMessage(
            content=response.get("content", ""),
            tool_calls=[
                {"name": c["name"], "args": c["args"], "id": c["id"], "type": "tool_call"}
                for c in response.get("tool_calls", [])
            ],
            usage_metadata=response.get("usage"),
        )

    def _plan(self, messages: list[BaseMessage]) -> tuple[str, str, dict[str, Any] | None]:
        """(mode, key, fixture): what to do for this call. A spent live budget becomes replay."""
        mode = current_mode()
        if mode == "off":
            return "off", "", None
        key = fixture_key("chat", self.model_id, messages, self.bound_tools)
        if mode == "live" and not _spend_live():
            mode = "replay"
        if mode == "replay":
            fx = load_fixture(key)
            if fx is not None:
                hits = _used.get()
                if hits is not None:
                    hits.append(key)
                return "hit", key, fx["response"]
            misses = _misses.get()
            if misses is not None:
                misses.append(
                    {"key": key, "kind": "chat", "model": self.model_id, **_summary(messages)}
                )
            log.info("replay_miss", kind="chat", model=self.model_id, key=key[:12])
            return "miss", key, None
        return mode, key, None  # live | record

    def _real_model(self) -> tuple[BaseChatModel, dict[str, Any]]:
        if self.inner is None:
            raise ReplayError("no real model is configured for this call")
        return self._resolve(self.inner)

    @staticmethod
    def _response_of(ai: AIMessage, seconds: float) -> dict[str, Any]:
        return {
            "content": ai.content,
            "tool_calls": [
                {"name": c["name"], "args": c["args"], "id": c["id"]} for c in ai.tool_calls
            ],
            "usage": _usage(ai),
            "seconds": round(seconds, 2),
        }

    def _note_used(self, key: str) -> None:
        hits = _used.get()
        if hits is not None:
            hits.append(key)

    # -- BaseChatModel
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        mode, key, fixture = self._plan(messages)
        if mode == "hit":
            assert fixture is not None
            return ChatResult(generations=[ChatGeneration(message=self._ai(fixture))])
        if mode in ("miss", "off") and (mode == "miss" or self.inner is None):
            model, extra = self._resolve(self.fallback)
        else:
            model, extra = self._real_model()
        t0 = time.monotonic()
        result = model._generate(
            messages, stop=stop, run_manager=run_manager, **{**extra, **kwargs}
        )
        if mode in ("record", "live"):
            self._note_used(key)
            if mode == "record":
                ai = result.generations[0].message
                assert isinstance(ai, AIMessage)
                self._record(key, "chat", messages, self._response_of(ai, time.monotonic() - t0))
        return result

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        mode, key, fixture = self._plan(messages)
        if mode == "hit":
            assert fixture is not None
            yield from self._replay_chunks(self._ai(fixture), run_manager)
            return
        if mode in ("miss", "off") and (mode == "miss" or self.inner is None):
            model, extra = self._resolve(self.fallback)
        else:
            model, extra = self._real_model()
        t0 = time.monotonic()
        whole: AIMessageChunk | None = None
        for chunk in model._stream(
            messages, stop=stop, run_manager=run_manager, **{**extra, **kwargs}
        ):
            if mode == "record" and isinstance(chunk.message, AIMessageChunk):
                whole = chunk.message if whole is None else whole + chunk.message
            yield chunk
        if mode in ("record", "live"):
            self._note_used(key)
        if mode == "record" and whole is not None:
            ai = AIMessage(
                content=whole.content,
                tool_calls=whole.tool_calls,
                usage_metadata=whole.usage_metadata,
            )
            self._record(key, "chat", messages, self._response_of(ai, time.monotonic() - t0))

    @staticmethod
    def _replay_chunks(
        msg: AIMessage, run_manager: CallbackManagerForLLMRun | None
    ) -> Iterator[ChatGenerationChunk]:
        if msg.tool_calls:
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {"name": c["name"], "args": json.dumps(c["args"]), "id": c["id"], "index": i}
                    for i, c in enumerate(msg.tool_calls)
                ],
                usage_metadata=msg.usage_metadata,
            )
            yield ChatGenerationChunk(message=chunk)
            return
        pieces = re.findall(r"\S+\s*", _flatten(msg.content)) or [""]
        for i, piece in enumerate(pieces):
            last = i == len(pieces) - 1
            chunk = AIMessageChunk(
                content=piece, usage_metadata=msg.usage_metadata if last else None
            )
            yield ChatGenerationChunk(message=chunk)

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Runnable:
        extra = (getattr(schema, "__name__", str(schema)),)

        def run(value: Any, config: Any = None) -> Any:
            messages = value if isinstance(value, list) else value.to_messages()
            mode = current_mode()

            def offline() -> Any:
                return self.fallback.with_structured_output(
                    schema, include_raw=include_raw, **kwargs
                ).invoke(messages, config=config)

            def shape(parsed: Any) -> Any:
                if not include_raw:
                    return parsed
                raw = AIMessage(content="")
                return {"raw": raw, "parsed": parsed, "parsing_error": None}

            if mode == "off":
                target = self.inner or self.fallback
                return target.with_structured_output(
                    schema, include_raw=include_raw, **kwargs
                ).invoke(messages, config=config)
            key = fixture_key("structured", self.model_id, messages, extra)
            if mode == "live" and not _spend_live():
                mode = "replay"
            if mode in ("live", "record"):
                if self.inner is None:
                    raise ReplayError("no real model is configured for this call")
                res = self.inner.with_structured_output(schema, include_raw=True, **kwargs).invoke(
                    messages, config=config
                )
                parsed = res["parsed"] if isinstance(res, dict) else res
                hits = _used.get()
                if hits is not None:
                    hits.append(key)
                if mode == "record":
                    data = parsed.model_dump(mode="json")
                    self._record(key, "structured", messages, {"parsed": data})
                return shape(parsed)
            fx = load_fixture(key)
            if fx is not None:
                hits = _used.get()
                if hits is not None:
                    hits.append(key)
                return shape(schema.model_validate(fx["response"]["parsed"]))
            misses = _misses.get()
            if misses is not None:
                misses.append(
                    {"key": key, "kind": "structured", "model": self.model_id, **_summary(messages)}
                )
            log.info("replay_miss", kind="structured", model=self.model_id, key=key[:12])
            return offline()

        return RunnableLambda(run, name="replay_structured")


def wrap(inner: BaseChatModel | None, model_id: str, *, fallback: BaseChatModel) -> ReplayChatModel:
    return ReplayChatModel(model_id=model_id, inner=inner, fallback=fallback)
