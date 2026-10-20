"""Runs the demo script in a judge's sandbox. A scene's actions call the real API in-process (same
app, same routers, same permission checks, as the scene's user) or a registered service call; the
expectations are then checked and stored. Nothing here is faked: a scene passes only when the
sandbox's real services give the expected answer. A failing or slow scene reports a friendly
message and never blocks the next one."""

import contextvars
import hashlib
import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import FastAPI
from sqlalchemy import select
from starlette.testclient import TestClient

from app.auth.demo import COOKIE_NAME as USER_COOKIE
from app.auth.demo import make_token
from app.config import REPO_ROOT, get_settings
from app.db.models import Deal, Document, Milestone, Party, User
from app.db.session import batch_session
from app.demo import sandbox
from app.demo.actions import CALLS
from app.demo.context import SandboxInfo
from app.demo.script import (
    Bi,
    SceneSpec,
    Script,
    ScriptError,
    check,
    dig,
    load_script,
    render,
)
from app.errors import DomainError
from app.llm import replay
from app.seed_ids import PI_KEY, RAHIMA

log = structlog.get_logger("setu.demo.runner")

DEMO_DIR = REPO_ROOT / "data" / "demo"
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="demo-scene")

FRIENDLY = Bi(
    en="This step could not finish just now. The rest of the demo still works: press Next.",
    bn="এই ধাপটি এখন শেষ করা যায়নি। বাকি ডেমো কাজ করছে: পরেরটিতে যান।",
)
TIMEOUT = Bi(
    en="This step took too long and was skipped. The rest of the demo still works.",
    bn="এই ধাপে অনেক সময় লাগায় বাদ দেওয়া হয়েছে। বাকি ডেমো কাজ করছে।",
)


def now() -> datetime:
    return datetime.now(UTC)


class ActionFailed(Exception):
    def __init__(self, action: str, status: int, detail: str, code: str | None = None) -> None:
        super().__init__(f"{action}: {status} {detail}")
        self.action, self.status, self.detail, self.code = action, status, detail, code


@dataclass
class SceneRun:
    """What one scene run can use: the in-process API as any demo user, static ids, variables."""

    app: FastAPI
    sandbox: SandboxInfo
    static: dict[str, Any]
    variables: dict[str, Any] = field(default_factory=dict)
    _tokens: dict[str, str] = field(default_factory=dict)
    _client: TestClient | None = None

    def _user_cookie(self, email: str) -> str:
        if email not in self._tokens:
            with batch_session() as db:
                uid = db.scalar(select(User.id).where(User.email == email, User.is_demo.is_(True)))
            if uid is None:
                raise ScriptError(f"unknown demo user {email}")
            self._tokens[email] = make_token(uid)
        return self._tokens[email]

    def http(
        self,
        email: str,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: Any = None,
    ) -> tuple[int, Any]:
        if self._client is None:
            self._client = TestClient(
                self.app, base_url="http://localhost", raise_server_exceptions=False
            )
        cookie = (
            f"{sandbox.COOKIE_NAME}={sandbox.make_token(self.sandbox.id)}; "
            f"{USER_COOKIE}={self._user_cookie(email)}"
        )
        resp = self._client.request(
            method,
            path,
            json=json,
            params=params or None,
            data=data or None,
            files=files,
            headers={"cookie": cookie},
        )
        try:
            body: Any = resp.json()
        except ValueError:
            body = {"text": resp.text[:500]}
        return resp.status_code, body


def static_vars() -> dict[str, Any]:
    """Ids the script refers to by name; they are the seed's stable ids, read from the sandbox."""
    with batch_session() as db:
        deal = db.scalar(select(Deal).where(Deal.reference == "SETU-2026-0001"))
        if deal is None:
            raise DomainError("the demo deal is missing from this sandbox", "SEED_MISSING")
        ms = {
            m.seq: m.id
            for m in db.scalars(select(Milestone).where(Milestone.deal_id == deal.id)).all()
        }
        parties = {p.code: p.id for p in db.scalars(select(Party)).all()}
        pi = db.scalar(select(Document.id).where(Document.key == PI_KEY))
        photo = db.scalar(
            select(Document.id).where(
                Document.deal_id == deal.id, Document.file_name == "production_photo_1.jpg"
            )
        )
    return {
        "deal": {"ref": deal.reference, "id": str(deal.id)},
        "buyer": {"code": RAHIMA},
        "m1": {"id": str(ms[1])},
        "m2": {"id": str(ms[2])},
        "m3": {"id": str(ms[3])},
        "huaxin": {"id": str(parties["shaoxing-huaxin"])},
        "huameng": {"id": str(parties["guangzhou-huameng"])},
        "pi": {"id": str(pi)},
        "photo1": {"id": str(photo)},
    }


def _friendly_detail(body: Any) -> tuple[str, str | None]:
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail[:200], body.get("code")
    return "unexpected response", None


def _expected(spec_status: int | list[int] | None, status: int) -> bool:
    if spec_status is None:
        return 200 <= status < 300
    return status in (spec_status if isinstance(spec_status, list) else [spec_status])


def _do_action(run: SceneRun, scene: SceneSpec, action: Any) -> None:
    email = action.as_ or scene.login_as
    if action.http:
        method, _, path = action.http.partition(" ")
        files = None
        if action.file:
            target = (DEMO_DIR / action.file.path).resolve()
            if DEMO_DIR.resolve() not in target.parents or not target.is_file():
                raise ScriptError(f"demo file not found: {action.file.path}")
            mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            files = {action.file.field: (target.name, target.read_bytes(), mime)}
        status, body = run.http(
            email,
            method,
            render(path, run.variables),
            json=render(action.json_, run.variables),
            params=render(action.query, run.variables),
            data=render(action.form, run.variables),
            files=files,
        )
    else:
        fn = CALLS.get(action.call or "")
        if fn is None:
            raise ScriptError(f"unknown call {action.call}")
        try:
            out = fn(run, **render(action.args, run.variables))
        except DomainError as exc:
            raise ActionFailed(action.id, exc.status, exc.detail, exc.code) from exc
        status, body = out["status"], out["body"]
    result: dict[str, Any] = {"status": status, "body": body}
    run.variables[action.id] = result
    if not _expected(action.expect_status, status):
        detail, code = _friendly_detail(body)
        raise ActionFailed(action.id, status, detail, code)
    for name, path in action.save.items():
        result[name] = dig(result, path)


def _fact(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list) and all(isinstance(x, dict) and "name" in x for x in value):
        return [x["name"] for x in value][:12]
    text = str(value)
    return text if len(text) <= 200 else text[:199] + "…"


def _saved(variables: dict[str, Any], action_ids: list[str]) -> dict[str, Any]:
    """Only what later scenes need: values an action `save`d (not whole response bodies)."""
    keep: dict[str, Any] = {}
    for aid in action_ids:
        entry = variables.get(aid)
        if isinstance(entry, dict):
            extra = {k: v for k, v in entry.items() if k not in ("status", "body")}
            if extra:
                keep[aid] = extra
    return keep


def _execute(
    app: FastAPI, sandbox_id: Any, n: int, k: int, persisted_vars: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one scene. Returns (result dict, saved variables)."""
    script = load_script()
    _step, scene = script.find(n, k)
    started = now()
    t0 = time.monotonic()
    result: dict[str, Any] = {
        "n": n,
        "k": k,
        "status": "failed",
        "started_at": started.isoformat(),
        "assertions": [],
        "facts": {},
        "route": None,
        "message": None,
        "error_code": None,
        "llm": None,
    }
    saved: dict[str, Any] = {}
    with sandbox.acting_in(sandbox_id) as info, replay.strict_run() as llm:
        run = SceneRun(app=app, sandbox=info, static=static_vars())
        run.variables = {**run.static, **persisted_vars}
        try:
            for action in scene.actions:
                _do_action(run, scene, action)
            ok_all = True
            for spec in scene.expect:
                ok, expected, actual = check(spec, run.variables)
                ok_all &= ok
                result["assertions"].append(
                    {
                        "label": spec.label.model_dump(),
                        "ok": ok,
                        "expected": expected,
                        "actual": actual,
                    }
                )
            result["facts"] = {
                key: p[1:-1]
                if len(p) > 1 and p[0] == p[-1] == "'"
                else _fact(dig(run.variables, p))
                for key, p in scene.facts.items()
            }
            result["route"] = render(scene.route, run.variables)
            result["status"] = "passed" if ok_all else "failed"
            if not ok_all:
                result["message"] = FRIENDLY.model_dump()
                result["error_code"] = "EXPECTATION_FAILED"
        except ActionFailed as exc:
            log.warning(
                "scene_action_failed", scene=f"{n}.{k}", action=exc.action, status=exc.status
            )
            result["message"] = FRIENDLY.model_dump()
            result["error_code"] = exc.code or f"HTTP_{exc.status}"
            result["assertions"].append(
                {
                    "label": {
                        "en": f"Action '{exc.action}' succeeds",
                        "bn": f"'{exc.action}' সফল হয়",
                    },
                    "ok": False,
                    "expected": "2xx",
                    "actual": f"{exc.status} {exc.detail}",
                }
            )
            try:
                result["route"] = render(scene.route, run.variables)
            except ScriptError:
                result["route"] = None
        except ScriptError as exc:
            log.error("scene_script_error", scene=f"{n}.{k}", error=str(exc))
            result["message"] = FRIENDLY.model_dump()
            result["error_code"] = "SCRIPT_ERROR"
        except Exception as exc:  # never show a stack trace; the log has the type
            log.error("scene_crashed", scene=f"{n}.{k}", error=type(exc).__name__)
            result["message"] = FRIENDLY.model_dump()
            result["error_code"] = "SCENE_ERROR"
        saved = _saved(run.variables, [a.id for a in scene.actions])
        result["llm"] = {
            "mode": replay.current_mode(),
            "fixtures_used": len(llm.hits),
            "misses": len(llm.misses),
        }
        result["_keys"] = {
            "hits": list(llm.hits),
            "misses": [
                {k: m[k] for k in ("key", "kind", "model", "last_user")} for m in llm.misses
            ],
        }
    result["duration_ms"] = int((time.monotonic() - t0) * 1000)
    return result, saved


def _fresh_state() -> dict[str, Any]:
    return {"scenes": {}, "vars": {}, "cursor": None, "started_at": now().isoformat()}


def get_state(sandbox_id: Any) -> dict[str, Any]:
    state = sandbox.load_state(sandbox_id)
    return state if "scenes" in state else _fresh_state()


def run_scene(
    app: FastAPI, sandbox_id: Any, n: int, k: int, *, force: bool = False
) -> dict[str, Any]:
    """Run scene n.k once (a passed scene is returned as stored unless `force`)."""
    script = load_script()
    try:
        script.find(n, k)
    except KeyError as exc:
        raise DomainError(f"there is no scene {n}.{k}", "UNKNOWN_SCENE") from exc
    key = f"{n}.{k}"
    state = get_state(sandbox_id)
    existing = state["scenes"].get(key)
    if existing and existing["status"] == "passed" and not force:
        return existing

    ctx = contextvars.copy_context()

    def work() -> tuple[dict[str, Any], dict[str, Any]]:
        with sandbox.sandbox_lock(sandbox_id):
            current = get_state(sandbox_id)
            out = ctx.run(_execute, app, sandbox_id, n, k, current["vars"])
            current["scenes"][key] = out[0]
            current["vars"].update(out[1])
            current["cursor"] = key
            sandbox.save_state(sandbox_id, current)
            return out

    future = _POOL.submit(work)
    try:
        result, _ = future.result(timeout=get_settings().demo_step_timeout_seconds)
    except FutureTimeout:
        log.error("scene_timeout", scene=key)
        result = {
            "n": n,
            "k": k,
            "status": "failed",
            "started_at": now().isoformat(),
            "duration_ms": int(get_settings().demo_step_timeout_seconds * 1000),
            "assertions": [],
            "facts": {},
            "route": None,
            "message": TIMEOUT.model_dump(),
            "error_code": "TIMEOUT",
            "llm": None,
        }
    return result


def goto(app: FastAPI, sandbox_id: Any, step: int) -> list[dict[str, Any]]:
    """Fast-forward: run, in order, every scene before step `step` that has not run yet."""
    ran: list[dict[str, Any]] = []
    state = get_state(sandbox_id)
    for n, k in load_script().scene_ids():
        if n >= step:
            break
        if f"{n}.{k}" in state["scenes"]:
            continue
        ran.append(run_scene(app, sandbox_id, n, k))
    return ran


def scorecard(
    script: Script, state: dict[str, Any], variables: dict[str, Any]
) -> list[dict[str, Any]]:
    items = []
    for item in script.scorecard:
        res = state["scenes"].get(item.after)
        try:
            link = render(item.link, variables)
        except ScriptError:
            link = item.link
        items.append(
            {
                "id": item.id,
                "group": item.group,
                "label": item.label.model_dump(),
                "link": link,
                "after": item.after,
                "ticked": bool(res and res["status"] == "passed"),
            }
        )
    return items


def fixtures_signature() -> str:
    """Short digest of the recorded fixtures (for the pre-flight and the run report)."""
    keys = sorted(f["key"] for f in replay.list_fixtures())
    return hashlib.sha256("".join(keys).encode()).hexdigest()[:12]
