"""Shared helpers for Onboard troubleshooting CLI scripts."""

from __future__ import annotations

from pathlib import Path


def fallback_api_key_from_stack_env() -> str:
    """Read OFDD_ONBOARD_API_KEY from stack/.env when available."""
    env_path = Path(__file__).resolve().parents[1] / "stack" / ".env"
    if not env_path.exists():
        return ""
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if not line.startswith("OFDD_ONBOARD_API_KEY="):
            continue
        value = line.split("=", 1)[1].strip()
        if not value:
            return ""
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            return value[1:-1].strip()
        if "#" in value:
            value = value.split("#", 1)[0].rstrip()
        return value.strip()
    return ""
