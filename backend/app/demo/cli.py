"""Command line for the guided demo.

    pnpm demo:run       run the 12 steps once in a throwaway sandbox and print the table
    pnpm demo:check     the same, strictly in replay: fails if a fixture is missing, a step fails
                        or the fixtures are stale (CI / pre-flight before a presentation)
    pnpm demo:record    run with the real model and (re)write the AI fixtures + manifest
    pnpm demo:verify    dirty a sandbox, reset it, run the seed verification on the result
    pnpm demo:cleanup   drop expired judge sandboxes

Replay is the default for every sandbox; `record` is the only mode that spends model tokens."""

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.demo import preflight, runner, sandbox
from app.demo.script import load_script
from app.llm import replay


def _app() -> Any:
    from app.main import app

    return app


def run_all(*, keep: bool = False) -> dict[str, Any]:
    """One full run in a fresh sandbox. Returns {"state": ..., "seconds": ...}."""
    app = _app()
    row = sandbox.create_sandbox()
    try:
        import time

        t0 = time.monotonic()
        for n, k in load_script().scene_ids():
            runner.run_scene(app, row.id, n, k)
        return {"state": runner.get_state(row.id), "seconds": round(time.monotonic() - t0, 2)}
    finally:
        if not keep:
            sandbox.delete_sandbox(row.id)


def _table(state: dict[str, Any]) -> list[str]:
    lines = []
    for key, res in sorted(
        state["scenes"].items(), key=lambda kv: tuple(int(x) for x in kv[0].split("."))
    ):
        mark = "ok  " if res["status"] == "passed" else "FAIL"
        llm = res.get("llm") or {}
        note = (
            f" ai:{llm['fixtures_used']}hit/{llm['misses']}miss"
            if llm.get("fixtures_used") or llm.get("misses")
            else ""
        )
        bad = [a["label"]["en"] for a in res["assertions"] if not a["ok"]]
        lines.append(f"  {mark} {key:<5} {res['duration_ms']:>6} ms{note}  {'; '.join(bad)}")
    return lines


def cmd_run(_: argparse.Namespace) -> int:
    out = run_all()
    print("\n".join(_table(out["state"])))
    failed = [k for k, v in out["state"]["scenes"].items() if v["status"] != "passed"]
    total = len(out["state"]["scenes"])
    print(f"{total - len(failed)}/{total} scenes passed in {out['seconds']} s")
    return 1 if failed else 0


def verify_fixtures(state: dict[str, Any]) -> list[str]:
    """Problems with the recorded fixtures for a finished run (empty = all good)."""
    problems: list[str] = []
    manifest = preflight.read_manifest()
    if manifest is None:
        return ["no fixtures manifest: run `pnpm demo:record`"]
    if manifest.get("script") != preflight.script_digest():
        problems.append("the demo script changed since the fixtures were recorded")
    if manifest.get("prompts") != preflight.prompts_digest():
        problems.append("the prompts changed since the fixtures were recorded")
    for entry in manifest.get("fixtures", []):
        if replay.load_fixture(entry["key"]) is None:
            problems.append(
                f"fixture file missing for scene {entry.get('scene')} ({entry['key'][:12]})"
            )
    for key, res in state["scenes"].items():
        for miss in (res.get("_keys") or {}).get("misses", []):
            asked = miss["last_user"][:60]
            problems.append(
                f"scene {key}: no fixture for a {miss['kind']} call ({miss['key'][:12]}): {asked!r}"
            )
    return problems


def cmd_check(_: argparse.Namespace) -> int:
    """Strict replay run: every scene passes, no AI call without a fixture, manifest is current."""
    with replay.forced_mode("replay"):
        out = run_all()
    state = out["state"]
    print("\n".join(_table(state)))
    problems = [
        f"scene {k} did not pass" for k, v in state["scenes"].items() if v["status"] != "passed"
    ]
    problems += verify_fixtures(state)
    for p in problems:
        print(f"  problem: {p}")
    print(f"demo:check {'FAILED' if problems else 'ok'} ({out['seconds']} s)")
    return 1 if problems else 0


def cmd_record(args: argparse.Namespace) -> int:
    """Run with the real model; write one fixture per model call and the manifest."""
    settings = get_settings()
    if settings.active_llm_provider is None and not args.allow_mock:
        print("no AI key: set OPENROUTER_API_KEY or ANTHROPIC_API_KEY, or pass --allow-mock")
        return 2
    with replay.forced_mode("record"):
        out = run_all()
    state = out["state"]
    print("\n".join(_table(state)))
    entries: list[dict[str, Any]] = []
    for key, res in sorted(state["scenes"].items()):
        for fk in dict.fromkeys((res.get("_keys") or {}).get("hits", [])):
            fx = replay.load_fixture(fk)
            if fx:
                entries.append(
                    {
                        "key": fk,
                        "scene": key,
                        "kind": fx["kind"],
                        "model": fx["model"],
                        "source": fx["source"],
                    }
                )
    manifest = {
        "script": preflight.script_digest(),
        "prompts": preflight.prompts_digest(),
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "fixtures": entries,
    }
    path = preflight.manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sources = sorted({e["source"] for e in entries})
    print(f"recorded {len(entries)} fixtures ({', '.join(sources) or 'none'}) -> {path}")
    failed = [k for k, v in state["scenes"].items() if v["status"] != "passed"]
    return 1 if failed else 0


def cmd_verify(_: argparse.Namespace) -> int:
    """Reset a used sandbox and run the seed verification (profile "demo") on the result."""
    from sqlalchemy import text

    from app.db import tenancy
    from app.db.session import batch_session
    from seed.verify import print_table, run_checks

    row = sandbox.create_sandbox()
    try:
        with tenancy.use_schema(row.schema_name), batch_session() as db:
            db.execute(text("DELETE FROM alerts"))
            db.execute(text("UPDATE parties SET cash_balance = 0"))
        sandbox.reset_sandbox(row.id)
        with tenancy.use_schema(row.schema_name), batch_session() as db:
            checks = run_checks(db, profile=sandbox.PROFILE)
    finally:
        sandbox.delete_sandbox(row.id)
    print_table(checks)
    failed = [c for c in checks if not c.ok]
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed after reset")
    return 1 if failed else 0


def cmd_cleanup(_: argparse.Namespace) -> int:
    print(f"dropped {sandbox.cleanup_expired()} expired sandbox(es)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo", description="Setu guided demo (simulated data)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run").set_defaults(fn=cmd_run)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    rec = sub.add_parser("record")
    rec.add_argument("--allow-mock", action="store_true", help="record the offline model's answers")
    rec.set_defaults(fn=cmd_record)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    sub.add_parser("cleanup").set_defaults(fn=cmd_cleanup)
    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
