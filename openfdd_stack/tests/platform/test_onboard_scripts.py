import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    cur = Path(__file__).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("Could not locate repository root")


def test_onboard_list_metadata_requires_api_key():
    script = _repo_root() / "scripts" / "onboard_list_metadata.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Missing API key" in proc.stderr


def test_onboard_backfill_smoke_requires_api_key():
    script = _repo_root() / "scripts" / "onboard_backfill_smoke.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Missing API key" in proc.stderr
