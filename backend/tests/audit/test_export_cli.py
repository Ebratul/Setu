"""Export file + `python -m app.audit.verify` run as a subprocess with nothing but the file and a
public key (no database, no signing key in its environment), and the keygen CLI."""

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.audit import keygen, keys
from app.audit.export import export_lines
from app.audit.keys import public_pem
from app.audit.writer import write_audit
from app.config import AGENT_DIR, get_settings
from app.db.session import batch_session

pytestmark = pytest.mark.db

SEED = bytes(range(1, 33))
OTHER = bytes(range(101, 133))
DEAL_A, DEAL_B = uuid.uuid4(), uuid.uuid4()


def pem_of(seed: bytes) -> str:
    return public_pem(Ed25519PrivateKey.from_private_bytes(seed).public_key())


@pytest.fixture
def chain(migrated_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Six entries signed with SEED (alternating deals), after the default test key is replaced."""
    monkeypatch.setenv("AUDIT_SIGNING_KEY", SEED.hex())
    get_settings.cache_clear()
    with batch_session() as s:
        for i in range(6):
            write_audit(
                s,
                actor="system",
                action="ESCROW_FUNDED" if i % 2 else "TRANCHE_RELEASED",
                tier=1,
                params={"amount": "5760.00", "i": i},
                result="SIMULATED_OK",
                deal_id=DEAL_A if i % 2 else DEAL_B,
            )


def export_to(path: Path, **kw: object) -> list[str]:
    with batch_session() as s:
        lines = list(export_lines(s, **kw))  # type: ignore[arg-type]
    path.write_text("".join(lines), encoding="utf-8")
    return lines


def verify_cli(tmp_path: Path, file: Path, pem: Path) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(AGENT_DIR)}
    return subprocess.run(
        [sys.executable, "-m", "app.audit.verify", "--file", str(file), "--pubkey", str(pem)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_standalone_verifier_accepts_an_untouched_export(chain: None, tmp_path: Path) -> None:
    export_to(tmp_path / "log.jsonl")
    (tmp_path / "pub.pem").write_text(pem_of(SEED))
    res = verify_cli(tmp_path, tmp_path / "log.jsonl", tmp_path / "pub.pem")
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith("OK: 6 entries verified, seq 1..6")


def test_standalone_verifier_rejects_a_different_public_key(chain: None, tmp_path: Path) -> None:
    export_to(tmp_path / "log.jsonl")
    (tmp_path / "other.pem").write_text(pem_of(OTHER))
    res = verify_cli(tmp_path, tmp_path / "log.jsonl", tmp_path / "other.pem")
    assert res.returncode == 1
    assert "bad_signature" in res.stdout and "seq 1" in res.stdout


def test_standalone_verifier_names_the_exact_seq_of_a_tampered_payload(
    chain: None, tmp_path: Path
) -> None:
    lines = export_to(tmp_path / "log.jsonl")
    (tmp_path / "pub.pem").write_text(pem_of(SEED))
    assert '"amount":"5760.00"' in lines[3]
    forged = list(lines)
    forged[3] = lines[3].replace('"amount":"5760.00"', '"amount":"5761.00"')  # entry seq 3
    bad = tmp_path / "forged.jsonl"
    bad.write_text("".join(forged), encoding="utf-8")
    res = verify_cli(tmp_path, bad, tmp_path / "pub.pem")
    assert res.returncode == 1
    assert "BROKEN at seq 3" in res.stdout and "hash_mismatch" in res.stdout


def test_export_header_carries_the_documented_fields(chain: None, tmp_path: Path) -> None:
    lines = export_to(tmp_path / "log.jsonl")
    header = json.loads(lines[0])
    assert {
        "scheme",
        "genesis",
        "public_key_fingerprint",
        "generated_at",
        "entry_count",
        "first_seq",
        "last_seq",
        "how_to_verify",
    } <= set(header)
    assert header["scheme"] == "setu-audit-v2" and header["genesis"] == "0" * 64
    assert (header["entry_count"], header["first_seq"], header["last_seq"]) == (6, 1, 6)
    assert header["contiguous"] is True
    assert header["public_key_fingerprint"] == keys.fingerprint(
        Ed25519PrivateKey.from_private_bytes(SEED).public_key()
    )
    assert "app.audit.verify" in header["how_to_verify"]
    assert len(lines) == 7 and all(ln.endswith("\n") for ln in lines)


def test_deal_filtered_export_is_marked_non_contiguous_and_still_verifies(
    chain: None, tmp_path: Path
) -> None:
    lines = export_to(tmp_path / "deal.jsonl", deal_id=DEAL_A)
    header = json.loads(lines[0])
    assert header["contiguous"] is False and header["entry_count"] == 3
    assert [json.loads(ln)["seq"] for ln in lines[1:]] == [2, 4, 6]
    (tmp_path / "pub.pem").write_text(pem_of(SEED))
    res = verify_cli(tmp_path, tmp_path / "deal.jsonl", tmp_path / "pub.pem")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PARTIAL" in res.stdout


def test_range_export_header_reports_the_slice(chain: None, tmp_path: Path) -> None:
    header = json.loads(export_to(tmp_path / "r.jsonl", lo=2, hi=4)[0])
    assert (header["first_seq"], header["last_seq"], header["entry_count"]) == (2, 4, 3)


# --- keygen ------------------------------------------------------------------------------------


@pytest.fixture
def keygen_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    key_path, pub_path = tmp_path / "keys" / "dev.key", tmp_path / "pub" / "audit.pem"
    s = get_settings().model_copy(
        update={"audit_signing_key": None, "audit_dev_key_path": key_path}
    )
    monkeypatch.setattr(keys, "get_settings", lambda: s)
    monkeypatch.setattr(keygen, "get_settings", lambda: s)
    monkeypatch.setattr(keygen, "PUBLIC_KEY_PATH", pub_path)
    return key_path, pub_path


def test_keygen_creates_a_private_key_and_public_pem_once(
    keygen_paths: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, pub_path = keygen_paths
    assert keygen.main() == 0
    assert key_path.exists() and key_path.stat().st_mode & 0o077 == 0
    assert pub_path.read_text().startswith("-----BEGIN PUBLIC KEY-----")
    assert "created dev signing key" in capsys.readouterr().out


def test_keygen_never_overwrites_an_existing_key(
    keygen_paths: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, pub_path = keygen_paths
    keygen.main()
    key_before, pub_before = key_path.read_bytes(), pub_path.read_text()
    capsys.readouterr()
    assert keygen.main() == 0
    assert key_path.read_bytes() == key_before and pub_path.read_text() == pub_before
    assert "created dev signing key" not in capsys.readouterr().out


def test_keygen_warns_and_fails_when_the_committed_public_key_does_not_match(
    keygen_paths: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, pub_path = keygen_paths
    pub_path.parent.mkdir(parents=True)
    pub_path.write_text(pem_of(OTHER))
    assert keygen.main() == 1
    assert pub_path.read_text() == pem_of(OTHER)
    assert "does not match" in capsys.readouterr().err
    assert key_path.exists()
