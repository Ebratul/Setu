"""demo:check must fail when a fixture is missing; pre-flight reflects the same facts."""

from pathlib import Path

import pytest

from app.config import get_settings
from app.demo import cli, preflight

pytestmark = pytest.mark.db


def test_check_passes_with_the_committed_fixtures(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["check"]) == 0
    out = capsys.readouterr().out
    assert "demo:check ok" in out
    assert not [ln for ln in out.splitlines() if ln.startswith("  FAIL")]


def test_check_fails_when_the_fixtures_are_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEMO_FIXTURES_DIR", str(tmp_path))
    get_settings.cache_clear()
    assert cli.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "demo:check FAILED" in out
    assert "no fixtures manifest" in out


def test_check_fails_when_a_single_fixture_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import shutil

    real = get_settings().demo_fixtures_dir
    shutil.copytree(real, tmp_path / "fx")
    victim = sorted((tmp_path / "fx" / "llm").glob("*.json"))[0]
    victim.unlink()
    monkeypatch.setenv("DEMO_FIXTURES_DIR", str(tmp_path / "fx"))
    get_settings.cache_clear()
    assert cli.main(["check"]) == 1
    out = capsys.readouterr().out
    assert "fixture file missing" in out or "no fixture for a" in out


def test_check_fails_when_the_prompts_changed_since_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    import shutil

    shutil.copytree(get_settings().demo_fixtures_dir, tmp_path / "fx")
    path = tmp_path / "fx" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["prompts"] = "0" * 16
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("DEMO_FIXTURES_DIR", str(tmp_path / "fx"))
    get_settings.cache_clear()
    assert cli.main(["check"]) == 1
    assert "prompts changed" in capsys.readouterr().out


def test_record_refuses_without_a_model_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    assert cli.main(["record"]) == 2
    assert "no AI key" in capsys.readouterr().out


def test_preflight_lists_what_a_presenter_needs() -> None:
    result = preflight.run()
    ids = {i.id for i in result.items}
    assert {"agent", "db", "capacity", "script", "files", "fixtures", "audit_key", "kb"} <= ids
    by = {i.id: i for i in result.items}
    assert by["script"].ok and by["files"].ok and by["fixtures"].ok and by["audit_key"].ok
    assert by["db"].ok
    for item in result.items:  # both languages for every label
        assert item.label.en and item.label.bn


def test_preflight_goes_red_for_stale_fixtures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_FIXTURES_DIR", str(tmp_path))
    get_settings.cache_clear()
    by = {i.id: i for i in preflight.run().items}
    assert by["fixtures"].ok is False and "pnpm demo:record" in by["fixtures"].detail
