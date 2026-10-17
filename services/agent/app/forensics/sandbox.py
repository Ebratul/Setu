"""Run the PDF parser in a child process with RLIMIT_AS / RLIMIT_CPU and a wall-clock timeout, so
a hostile file (decompression bomb, pathological content stream) cannot exhaust the API process.
The child gets a minimal environment (no database URL, no keys) and only the PDF bytes."""

import json
import os
import subprocess
import sys

from app.config import AGENT_DIR
from app.forensics.pdf_text import PdfText, from_dict, read_pdf


class PdfReadError(Exception):
    """The file could not be parsed within the limits (corrupt, too heavy, killed)."""


def read_pdf_sandboxed(data: bytes, *, timeout: float = 20.0, memory_mb: int = 1024) -> PdfText:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(AGENT_DIR),
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    cpu = max(1, int(timeout))
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "app.forensics.pdf_worker", str(memory_mb), str(cpu)],
            input=data,
            capture_output=True,
            timeout=timeout,
            cwd=AGENT_DIR,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PdfReadError("parsing timed out") from exc
    if proc.returncode != 0:
        raise PdfReadError(f"parser exited with code {proc.returncode}")
    try:
        return from_dict(json.loads(proc.stdout))
    except (ValueError, KeyError, TypeError) as exc:
        raise PdfReadError("parser returned invalid output") from exc


def parse_pdf(data: bytes, *, sandbox: bool, timeout: float, memory_mb: int) -> PdfText:
    return (
        read_pdf_sandboxed(data, timeout=timeout, memory_mb=memory_mb)
        if sandbox
        else read_pdf(data)
    )
