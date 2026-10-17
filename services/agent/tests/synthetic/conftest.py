import json
from pathlib import Path

import pytest

from synthetic.generator import generate

SEED = 42
CLEAN, TAMPERED = 30, 60  # 6 packs per fraud type: 3 obvious + 3 subtle


@pytest.fixture(scope="session")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[dict]]:
    out = tmp_path_factory.mktemp("synthetic")
    generate(CLEAN, TAMPERED, SEED, out)
    lines = (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    return out, [json.loads(line) for line in lines]
