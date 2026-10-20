"""Pre-flight for the guided demo: a green/red list a presenter can read in one glance."""

import hashlib
import json
from pathlib import Path

from sqlalchemy import func, select, text

from app.audit.keys import load_signing_key
from app.config import REPO_ROOT, get_settings
from app.db.models import DemoSandbox, KbChunk
from app.db.session import ping
from app.demo import sandbox
from app.demo.script import Bi, ScriptError, load_script
from app.llm import replay
from app.schemas.demo import PreflightItem, PreflightOut

DEMO_DIR = REPO_ROOT / "data" / "demo"


def manifest_path() -> Path:
    return get_settings().demo_fixtures_dir / "manifest.json"


def script_digest() -> str:
    """Digest of what feeds the AI fixtures: the chat messages the script sends."""
    script = load_script()
    asked = [
        (a.id, json.dumps(a.json_, sort_keys=True, ensure_ascii=False))
        for step in script.steps
        for scene in step.scenes
        for a in scene.actions
        if a.http and a.http.endswith("/chat")
    ]
    return hashlib.sha256(json.dumps(asked, ensure_ascii=False).encode()).hexdigest()[:16]


def prompts_digest() -> str:
    """Prompt files feed the fixture keys: when they change, fixtures must be re-recorded."""
    root = REPO_ROOT / "services" / "agent" / "app"
    files = sorted([root / "agent" / "prompts.py", *(root / "llm" / "prompts").glob("*")])
    h = hashlib.sha256()
    for f in files:
        if f.is_file():
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def read_manifest() -> dict | None:
    p = manifest_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _item(id_: str, en: str, bn: str, ok: bool, detail: str) -> PreflightItem:
    return PreflightItem(id=id_, label=Bi(en=en, bn=bn), ok=ok, detail=detail)


def run() -> PreflightOut:
    settings = get_settings()
    items: list[PreflightItem] = [
        _item("agent", "Agent API is up", "এজেন্ট এপিআই চালু", True, settings.app_version)
    ]

    db_ok = ping()
    detail = "reachable" if db_ok else "not reachable"
    active = 0
    if db_ok:
        try:
            with sandbox.registry() as db:
                db.execute(text("SELECT 1 FROM demo_sandboxes LIMIT 1"))
                active = (
                    db.scalar(
                        select(func.count())
                        .select_from(DemoSandbox)
                        .where(DemoSandbox.status == "ACTIVE")
                    )
                    or 0
                )
            detail = f"reachable, {active} active sandbox(es)"
        except Exception:
            db_ok, detail = False, "reachable, but the sandbox table is missing (run migrations)"
    items.append(_item("db", "Database and sandboxes", "ডাটাবেস ও স্যান্ডবক্স", db_ok, detail))
    cap_ok = active < settings.sandbox_max_active
    items.append(
        _item(
            "capacity",
            "Room for another sandbox",
            "আরেকটি স্যান্ডবক্সের জায়গা আছে",
            cap_ok,
            f"{active} of {settings.sandbox_max_active} in use",
        )
    )

    try:
        script = load_script()
        script_ok, sdetail = True, f"{len(script.steps)} steps, {len(script.scene_ids())} scenes"
    except (ValueError, OSError, ScriptError) as exc:
        script_ok, sdetail = False, f"invalid script: {type(exc).__name__}"
    items.append(_item("script", "Demo script is valid", "ডেমো স্ক্রিপ্ট সঠিক", script_ok, sdetail))

    missing = []
    if script_ok:
        for step in script.steps:
            for scene in step.scenes:
                for action in scene.actions:
                    if action.file and not (DEMO_DIR / action.file.path).is_file():
                        missing.append(action.file.path)
    items.append(
        _item(
            "files",
            "Demo documents are present",
            "ডেমো নথি আছে",
            not missing,
            "all present" if not missing else f"missing: {', '.join(sorted(set(missing)))}",
        )
    )

    manifest = read_manifest()
    fx_ok, fdetail = False, "no fixtures recorded (run: pnpm demo:record)"
    if manifest:
        keys = [e["key"] for e in manifest.get("fixtures", [])]
        absent = [k for k in keys if replay.load_fixture(k) is None]
        stale = manifest.get("script") != script_digest() or manifest.get("prompts") != (
            prompts_digest()
        )
        fx_ok = bool(keys) and not absent and not stale
        fdetail = (
            f"{len(keys)} fixtures"
            if fx_ok
            else f"{len(absent)} missing"
            if absent
            else "stale: the script or prompts changed (run: pnpm demo:record)"
        )
    items.append(_item("fixtures", "AI replay fixtures", "এআই রিপ্লে ফিক্সচার", fx_ok, fdetail))

    try:
        key = load_signing_key()
        key_ok, kdetail = True, "loaded"
        del key
    except Exception:
        key_ok, kdetail = False, "audit signing key not available"
    items.append(_item("audit_key", "Audit signing key", "অডিট সাইনিং কী", key_ok, kdetail))

    kb_ok, kb_detail = False, "not indexed (run: pnpm kb:index)"
    try:
        with sandbox.registry() as db:
            n = db.scalar(select(func.count()).select_from(KbChunk)) or 0
        kb_ok, kb_detail = n > 0, f"{n} chunks"
    except Exception:
        pass
    items.append(_item("kb", "Knowledge base indexed", "নলেজ বেস ইনডেক্সড", kb_ok, kb_detail))

    live = settings.active_llm_provider is not None
    items.append(
        _item(
            "live_ai",
            "Live AI available (optional)",
            "লাইভ এআই আছে (ঐচ্ছিক)",
            True,
            "a model key is configured" if live else "no key: replay only",
        )
    )
    return PreflightOut(
        ok=all(i.ok for i in items), replay=replay.current_mode() != "live", items=items
    )
