"""Guided demo and judge sandboxes. A sandbox is the judge's own copy of the demo data (see
app/demo/sandbox.py); the run endpoints execute the 12-step story on it with the real services.
Everything is simulated."""

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, Response
from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import DemoSandbox, PrivacyRecord
from app.db.session import batch_session
from app.demo import preflight, runner, sandbox, summary
from app.demo.actions import skip_open_cooling_off
from app.demo.context import SandboxInfo, current_sandbox, use_sandbox
from app.demo.script import load_script
from app.errors import Forbidden, NotFound, TooManyRequests
from app.schemas.demo import (
    CoolingOffOut,
    CursorOut,
    GotoIn,
    LiveAiIn,
    PreflightOut,
    RunOut,
    SandboxCreateIn,
    SandboxOut,
    SceneDefOut,
    SceneResultOut,
    ScoreDefOut,
    ScoreItemOut,
    ScriptOut,
    StepDefOut,
    SummaryOut,
)

router = APIRouter(prefix="/demo", tags=["demo"])


def _require_sandbox() -> SandboxInfo:
    info = current_sandbox()
    if info is None:
        raise NotFound("no sandbox yet: start one first", "SANDBOX_REQUIRED")
    return info


def _out(row: DemoSandbox) -> SandboxOut:
    settings = get_settings()
    return SandboxOut(
        id=row.id,
        created_at=row.created_at,
        expires_at=row.expires_at,
        replay=not row.live_ai,
        live_ai=row.live_ai,
        live_ai_available=settings.active_llm_provider is not None
        and settings.sandbox_live_ai_budget > 0,
        live_ai_budget_left=sandbox.live_ai_budget_left(row),
        resets=row.resets,
    )


def _set_cookie(response: Response, row: DemoSandbox) -> None:
    settings = get_settings()
    response.set_cookie(
        sandbox.COOKIE_NAME,
        sandbox.make_token(row.id),
        max_age=int(settings.sandbox_ttl_hours * 3600),
        httponly=True,
        samesite="lax",
        secure=settings.demo_cookie_secure,
        path="/",
    )


def _caller(request: Request) -> str:
    """The address the platform saw: its own header, else the nearest proxy's hop (the right-most
    X-Forwarded-For entry; the left-most is client-supplied and can be spoofed)."""
    h = request.headers
    for name in ("x-vercel-forwarded-for", "x-real-ip"):
        if h.get(name):
            return h[name].split(",")[0].strip()
    hops = [x.strip() for x in h.get("x-forwarded-for", "").split(",") if x.strip()]
    return hops[-1] if hops else (request.client.host if request.client else "unknown")


def _public(scene: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in scene.items() if not k.startswith("_")}


def _run_out(request: Request, last: dict[str, Any] | None = None) -> RunOut:
    info = _require_sandbox()
    script = load_script()
    state = runner.get_state(info.id)
    with sandbox.registry() as db:
        row = sandbox.get_row(db, info.id)
        db.expunge(row)
    variables = {**state.get("vars", {})}
    with use_sandbox(info):
        variables.update(runner.static_vars())
    scenes = [SceneResultOut.model_validate(_public(s)) for s in state["scenes"].values()]
    scenes.sort(key=lambda s: (s.n, s.k))
    cursor = state.get("cursor")
    n, _, k = (cursor or "").partition(".")
    return RunOut(
        sandbox=_out(row),
        cursor=CursorOut(n=int(n), k=int(k)) if cursor else None,
        scenes=scenes,
        scorecard=[
            ScoreItemOut.model_validate(i) for i in runner.scorecard(script, state, variables)
        ],
        total_scenes=len(script.scene_ids()),
        passed=sum(1 for s in scenes if s.status == "passed"),
        failed=sum(1 for s in scenes if s.status == "failed"),
        completed=len(scenes) >= len(script.scene_ids()),
        last=SceneResultOut.model_validate(_public(last)) if last else None,
    )


@router.get("/steps", response_model=ScriptOut)
def steps() -> ScriptOut:
    """The story: titles, narration, presenter notes, scenes and the scorecard (EN and BN)."""
    script = load_script()
    return ScriptOut(
        steps=[
            StepDefOut(
                n=s.n,
                id=s.id,
                tag=s.tag,
                title=s.title,
                narration=s.narration,
                notes=s.notes,
                scenes=[
                    SceneDefOut(
                        k=c.k,
                        view=c.view,
                        login_as=c.login_as,
                        route=c.route,
                        highlight=c.highlight,
                        caption=c.caption,
                    )
                    for c in s.scenes
                ],
            )
            for s in script.steps
        ],
        scorecard=[
            ScoreDefOut(id=i.id, group=i.group, after=i.after, link=i.link, label=i.label)
            for i in script.scorecard
        ],
        total_scenes=len(script.scene_ids()),
    )


@router.get("/preflight", response_model=PreflightOut)
def get_preflight() -> PreflightOut:
    """Green/red readiness list: API, database, fixtures, audit key, knowledge base."""
    return preflight.run()


@router.post("/sandbox", response_model=SandboxOut)
def start_sandbox(body: SandboxCreateIn, request: Request, response: Response) -> SandboxOut:
    """Start (or resume) the judge's own sandbox: a private copy of the demo data."""
    raw = request.cookies.get(sandbox.COOKIE_NAME)
    old = sandbox.parse_token(raw) if raw else None
    existing = sandbox.lookup(old) if old is not None else None
    if existing is not None and not body.fresh:
        with sandbox.registry() as db:
            row = sandbox.get_row(db, existing.id)
            db.expunge(row)
        _set_cookie(response, row)
        return _out(row)
    caller = _caller(request)
    wait = sandbox.allow_create(caller)
    if wait is not None:
        raise TooManyRequests(
            "too many new sandboxes from this address; try again later", "SANDBOX_RATE_LIMIT"
        )
    row = sandbox.create_sandbox()
    if old is not None:
        sandbox.delete_sandbox(old)
    _set_cookie(response, row)
    return _out(row)


@router.get("/sandbox", response_model=SandboxOut)
def get_sandbox() -> SandboxOut:
    info = _require_sandbox()
    with sandbox.registry() as db:
        row = sandbox.get_row(db, info.id)
        db.expunge(row)
    return _out(row)


@router.delete("/sandbox", status_code=204)
def end_sandbox(request: Request, response: Response) -> Response:
    """End the sandbox now and drop its data."""
    raw = request.cookies.get(sandbox.COOKIE_NAME)
    sandbox_id = sandbox.parse_token(raw) if raw else None
    if sandbox_id is not None:
        sandbox.delete_sandbox(sandbox_id)
    response.delete_cookie(sandbox.COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.post("/sandbox/live-ai", response_model=SandboxOut)
def live_ai(body: LiveAiIn) -> SandboxOut:
    """Use the real model for this sandbox's AI answers (budget-capped); off = recorded replay."""
    info = _require_sandbox()
    settings = get_settings()
    if body.enabled and settings.active_llm_provider is None:
        raise Forbidden("no AI key is configured on this server", "LIVE_AI_UNAVAILABLE")
    with sandbox.registry() as db:
        row = sandbox.get_row(db, info.id)
        if body.enabled and sandbox.live_ai_budget_left(row) <= 0:
            raise Forbidden("this sandbox has used its live-AI budget", "LIVE_AI_BUDGET")
    return _out(sandbox.set_live_ai(info.id, body.enabled))


@router.post("/sandbox/skip-cooling-off", response_model=CoolingOffOut)
def skip_cooling_off() -> CoolingOffOut:
    """ "Skip cooling-off (demo only)": ends the pause of this sandbox's open Tier 3 requests."""
    info = _require_sandbox()
    if get_settings().app_env == "prod":
        raise Forbidden("this control is only for demos", "DEMO_ONLY")
    return CoolingOffOut(skipped=skip_open_cooling_off(sandbox_id=str(info.id))["skipped"])


@router.get("/run", response_model=RunOut)
def get_run(request: Request) -> RunOut:
    return _run_out(request)


@router.post("/run/scenes/{n}/{k}/run", response_model=RunOut)
def run_scene(n: int, k: int, request: Request, force: Annotated[bool, Query()] = False) -> RunOut:
    """Run one scene's real actions in this sandbox (a passed scene is not run twice)."""
    info = _require_sandbox()
    result = runner.run_scene(request.app, info.id, n, k, force=force)
    return _run_out(request, result)


@router.post("/run/goto", response_model=RunOut)
def goto(body: GotoIn, request: Request) -> RunOut:
    """Deep link / jump: run every earlier scene that has not run, so the state is right."""
    info = _require_sandbox()
    runner.goto(request.app, info.id, body.step)
    return _run_out(request)


@router.post("/run/reset", response_model=RunOut)
def reset(request: Request) -> RunOut:
    """Rebuild only this sandbox from the seed (audited as DEMO_RESET)."""
    info = _require_sandbox()
    sandbox.reset_sandbox(info.id)
    fresh = sandbox.lookup(info.id)  # the rebuilt copy lives in a new schema
    with use_sandbox(fresh):
        return _run_out(request)


@router.get("/run/summary", response_model=SummaryOut)
def run_summary() -> SummaryOut:
    info = _require_sandbox()
    state = runner.get_state(info.id)
    protected: int | None = None
    try:
        with use_sandbox(info), batch_session() as db:
            protected = int(db.scalar(select(func.coalesce(func.sum(PrivacyRecord.protected), 0))))
    except Exception:
        protected = None
    return summary.build(state, len(load_script().scene_ids()), protected)


@router.post("/cleanup")
def cleanup(authorization: Annotated[str | None, Header()] = None) -> dict[str, int]:
    """Drop expired sandboxes (for a scheduler). Needs `Authorization: Bearer $CRON_SECRET`."""
    configured = get_settings().cron_secret
    secret = configured.get_secret_value() if configured else ""
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not secret or not hmac.compare_digest(given.encode(), secret.encode()):
        raise Forbidden("cleanup needs the cron secret")
    return {"dropped": sandbox.cleanup_expired()}
