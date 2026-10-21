import asyncio
import json
import subprocess
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.audit.keys import load_signing_key
from app.config import REPO_ROOT, get_settings
from app.db import session
from app.llm import replay

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Public readiness report. Booleans and build identity only: no keys, URLs or counts."""

    model_config = ConfigDict(extra="allow")

    status: Literal["ok"]
    service: Literal["setu-agent"]
    db: Literal["ok", "unavailable"]
    version: str
    ready: bool = False
    kb_indexed: bool = False
    audit_key_loaded: bool = False
    replay_fixtures_present: bool = False
    git_sha: str = "unknown"
    built_at: str | None = None
    demo_mode: bool = False
    demo_replay: bool = False


@lru_cache
def _git_sha() -> str:
    """Env first (GIT_SHA / VERCEL_GIT_COMMIT_SHA), then `git rev-parse`; cached for the process."""
    configured = get_settings().git_sha
    if configured and configured.strip():
        return configured.strip()[:7]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=1.5,
            check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"
    return out[:7] or "unknown"


def _kb_indexed() -> bool:
    try:
        engine = session.get_engine()
        if engine is None:
            return False
        with engine.connect() as conn:
            return conn.execute(text("SELECT 1 FROM kb_chunks LIMIT 1")).first() is not None
    except Exception:
        return False


def _audit_key_loaded() -> bool:
    try:
        load_signing_key()
    except Exception:
        return False
    return True


def _replay_fixtures_present() -> bool:
    """The P21 manifest exists and every fixture file it lists is on disk (stat only)."""
    try:
        manifest = json.loads(
            (get_settings().demo_fixtures_dir / "manifest.json").read_text(encoding="utf-8")
        )
        keys = [e["key"] for e in manifest.get("fixtures", [])]
        return bool(keys) and all(replay.fixture_path(k).is_file() for k in keys)
    except Exception:
        return False


def _db_checks() -> tuple[bool, bool]:
    if not session.ping():
        return False, False
    return True, _kb_indexed()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    try:
        db_ok, kb_ok = await asyncio.wait_for(
            run_in_threadpool(_db_checks), timeout=settings.db_check_timeout_seconds + 1
        )
    except TimeoutError:
        db_ok, kb_ok = False, False
    audit_ok = _audit_key_loaded()
    replay_ok = _replay_fixtures_present()
    return HealthResponse(
        status="ok",
        service="setu-agent",
        db="ok" if db_ok else "unavailable",
        version=settings.app_version,
        ready=db_ok and kb_ok and audit_ok and replay_ok,
        kb_indexed=kb_ok,
        audit_key_loaded=audit_ok,
        replay_fixtures_present=replay_ok,
        git_sha=_git_sha(),
        built_at=settings.build_time or None,
        demo_mode=settings.demo_mode,
        demo_replay=settings.demo_replay,
    )
