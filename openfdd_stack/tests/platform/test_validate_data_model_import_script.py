import json
import subprocess
import sys
from pathlib import Path


def _script_path() -> str:
    cur = Path(__file__).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "pyproject.toml").exists():
            candidate = parent / "scripts" / "validate_data_model_import.py"
            if candidate.exists():
                return str(candidate)
            raise FileNotFoundError(
                f"validate_data_model_import.py not found at expected path: {candidate}"
            )
    raise RuntimeError("Could not locate repository root for validate_data_model_import.py")


def test_validate_data_model_import_script_accepts_valid_payload(tmp_path):
    payload = {
        "points": [
            {
                "point_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                "brick_type": "Supply_Air_Temperature_Sensor",
                "rule_input": "sat",
            }
        ]
    }
    payload_file = tmp_path / "valid-import.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, _script_path(), str(payload_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "VALID:" in proc.stdout


def test_validate_data_model_import_script_reports_validation_path(tmp_path):
    payload = {
        "points": [
            {
                "point_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
                "brick_type": "Supply_Air_Temperature_Sensor",
                "unknown_key": "x",
            }
        ]
    }
    payload_file = tmp_path / "invalid-import.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, _script_path(), str(payload_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "points[0].unknown_key" in proc.stderr
    assert "Extra inputs are not permitted" in proc.stderr
