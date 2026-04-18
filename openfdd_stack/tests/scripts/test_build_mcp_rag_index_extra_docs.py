"""Regression: build_mcp_rag_index --extra-docs-dir (upstream sparse docs)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "build_mcp_rag_index.py"


@pytest.mark.skipif(not SCRIPT.is_file(), reason="build_mcp_rag_index.py missing")
def test_extra_docs_dir_produces_upstream_sources(tmp_path: Path) -> None:
    primary = tmp_path / "stack-docs" / "docs"
    primary.mkdir(parents=True)
    (primary / "local.md").write_text("# Local\n\nlocal only content here.\n")

    vendor_root = tmp_path / "vendor" / "open-fdd" / "docs"
    vendor_root.mkdir(parents=True)
    (vendor_root / "engine.md").write_text("# Engine\n\npandas yaml rules dataframe.\n")

    out = tmp_path / "rag_index.json"
    subprocess.check_call(
        [
            sys.executable,
            str(SCRIPT),
            "--docs-dir",
            str(primary),
            "--extra-docs-dir",
            str(vendor_root),
            "--output",
            str(out),
            "--chunk-size",
            "80",
        ],
        cwd=str(REPO_ROOT),
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    tags = {tuple(d.get("tags", ())) for d in data["docs"]}
    assert any("upstream:open-fdd" in t for t in tags)
    sources = {d["source"] for d in data["docs"]}
    assert any(s.startswith("open-fdd/docs/") for s in sources)
