#!/usr/bin/env python3
"""End-to-end smoke test of a running Setu deployment (API level). Exit code 1 if any step fails.

    BASE_URL=https://setu.example.com [AGENT_URL=https://agent.example.com] scripts/smoke_prod

BASE_URL is the web origin (the landing page); the agent API is AGENT_URL, else BASE_URL + /api
(how the web app and Vercel route it). Needs only httpx. It creates one judge sandbox, runs the whole
guided demo in replay, fires the hidden-text attack, verifies the signed audit chain, checks the
Privacy Gateway, resets and ends the sandbox. Nothing global is modified.
"""

import json
import os
import sys
import time
from collections.abc import Callable

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:3000").rstrip("/")
AGENT_URL = (os.environ.get("AGENT_URL") or f"{BASE_URL}/api").rstrip("/")
JUDGE = os.environ.get("SMOKE_JUDGE", "judge@demo.setu")
DEMO_TIMEOUT = float(os.environ.get("SMOKE_DEMO_TIMEOUT", "600"))
SAMPLE = (
    "Pay USD 12,500.00 to account 1234567890123 for Huaxin; call +8801712345678 "
    "or mail ops@huaxin.example"
)

results: list[tuple[str, bool, float, str]] = []


def expect(cond: object, message: str) -> None:
    if not cond:
        raise AssertionError(message)


def step(name: str) -> Callable[[Callable[[], str]], Callable[[], str]]:
    def deco(fn: Callable[[], str]) -> Callable[[], str]:
        t0 = time.perf_counter()
        try:
            detail, ok = fn() or "", True
        except Exception as exc:
            detail, ok = f"{type(exc).__name__}: {exc}", False
        dt = time.perf_counter() - t0
        results.append((name, ok, dt, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name:<34} {dt * 1000:8.0f} ms  {detail}", flush=True)
        return fn

    return deco


def main() -> int:
    print(f"web   {BASE_URL}\nagent {AGENT_URL}\n")
    api = httpx.Client(base_url=AGENT_URL, timeout=30.0, follow_redirects=True)
    web = httpx.Client(timeout=30.0, follow_redirects=True)
    ctx: dict[str, object] = {}

    @step("health: ready=true")
    def _() -> str:
        r = api.get("/health")
        expect(r.status_code == 200, f"HTTP {r.status_code}")
        h = r.json()
        flags = {k: h.get(k) for k in ("db", "kb_indexed", "audit_key_loaded")}
        flags["replay_fixtures_present"] = h.get("replay_fixtures_present")
        expect(h.get("ready") is True, f"not ready: {flags}")
        return f"git={h.get('git_sha')} built={h.get('built_at')} demo_replay={h.get('demo_replay')}"

    @step("landing page 200")
    def _() -> str:
        r = web.get(BASE_URL + "/")
        expect(r.status_code == 200, f"HTTP {r.status_code}")
        expect("text/html" in r.headers.get("content-type", ""), "not HTML")
        return f"{len(r.content)} bytes"

    @step("judge sandbox created")
    def _() -> str:
        r = api.post("/demo/sandbox", json={"fresh": True})
        expect(r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
        ctx["sandbox"] = r.json()["id"]
        expect(any(c.name == "setu_sandbox" for c in api.cookies.jar), "no sandbox cookie")
        return f"sandbox {str(ctx['sandbox'])[:8]}"

    @step("judge login")
    def _() -> str:
        r = api.post("/auth/demo-login", json={"email": JUDGE})
        expect(r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
        expect(r.json()["role"] == "JUDGE", f"role {r.json()['role']}")
        return JUDGE

    @step("guided demo replay (12 steps)")
    def _() -> str:
        steps = api.get("/demo/steps").json()["steps"]
        for st in steps:  # a passed scene is never run twice, so this is safe to repeat
            for sc in st["scenes"]:
                r = api.post(f"/demo/run/scenes/{st['n']}/{sc['k']}/run", timeout=DEMO_TIMEOUT)
                expect(r.status_code == 200, f"scene {st['n']}.{sc['k']} HTTP {r.status_code}")
        run = api.get("/demo/run").json()
        failed = [f"{s['n']}.{s['k']}" for s in run["scenes"] if s["status"] == "failed"]
        expect(not failed, f"failed scenes: {failed}")
        expect(run["failed"] == 0, "scenes failed")
        expect(run["completed"], f"{run['passed']}/{run['total_scenes']} scenes passed")
        card = [i for i in run["scorecard"] if i.get("ticked")]
        return f"{run['passed']}/{run['total_scenes']} scenes, scorecard {len(card)}/{len(run['scorecard'])}"

    @step("attack console: hidden text BLOCKED")
    def _() -> str:
        r = api.post("/security/injection/run", json={"attack_id": "hidden-white-text"})
        expect(r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
        out = r.json()
        expect(out["outcome"] == "blocked", f"outcome {out['outcome']}")
        expect(out["money_moved"] is False, "money moved")
        return f"layer {out['blocked_at_layer']}"

    @step("audit export + chain verify")
    def _() -> str:
        exp = api.get("/audit/export")
        expect(exp.status_code == 200, f"export HTTP {exp.status_code}")
        lines = [ln for ln in exp.text.splitlines() if ln.strip()]
        expect(len(lines) > 1, "export has no entries")
        for ln in lines:
            json.loads(ln)
        v = api.get("/audit/verify")
        expect(v.status_code == 200, f"verify HTTP {v.status_code}")
        body = v.json()
        expect(body["ok"] is True, f"chain broken at {body.get('broken_seq')}: {body.get('reason')}")
        expect(body["entries_checked"] >= len(lines) - 1, "verify checked fewer than exported")
        return f"{body['entries_checked']} entries, key {body['public_key_fingerprint'][:12]}"

    @step("privacy dry-run masks a sample")
    def _() -> str:
        r = api.post("/privacy/dry-run", json={"text": SAMPLE})
        expect(r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
        out = r.json()
        for raw in ("1234567890123", "+8801712345678", "ops@huaxin.example"):
            expect(raw not in out["masked"], f"{raw[:4]}... leaked into the masked text")
        expect("⟦" in out["masked"], "no tokens in the masked text")
        return f"{len(out['hits'])} items masked"

    @step("reset sandbox")
    def _() -> str:
        r = api.post("/demo/run/reset")
        expect(r.status_code == 200, f"HTTP {r.status_code} {r.text[:200]}")
        run = api.get("/demo/run").json()
        expect(run["passed"] == 0, f"{run['passed']} scenes still marked passed")
        return "back to the seed"

    @step("end sandbox")
    def _() -> str:
        r = api.delete("/demo/sandbox")
        expect(r.status_code == 204, f"HTTP {r.status_code}")
        return ""

    failed = [name for name, ok, _, _ in results if not ok]
    total = sum(dt for _, _, dt, _ in results)
    print(f"\n{len(results) - len(failed)}/{len(results)} steps passed in {total:.1f} s")
    if failed:
        print("FAILED: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
