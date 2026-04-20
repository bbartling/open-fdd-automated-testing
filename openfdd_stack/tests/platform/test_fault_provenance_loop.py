"""Regression tests for fault provenance evidence in loop results."""

from datetime import datetime

import pandas as pd

from openfdd_stack.platform.loop import _results_with_provenance


def test_results_with_provenance_populates_point_identity_from_rule_inputs():
    df = pd.DataFrame(
        [
            {
                "timestamp": datetime(2026, 4, 20, 12, 0, 0),
                "Supply_Air_Temperature_Sensor": 180.0,
                "bad_sensor_flag": 1,
            }
        ]
    )
    rules = [
        {
            "name": "bad_sensor_check",
            "flag": "bad_sensor_flag",
            "inputs": {"Supply_Air_Temperature_Sensor": {"brick": "Supply_Air_Temperature_Sensor"}},
        }
    ]
    point_lookup = {
        "Supply_Air_Temperature_Sensor": {
            "point_id": "pt-123",
            "external_id": "SA-T",
            "object_identifier": "analog-input,2",
            "object_name": "Supply Air Temp",
        }
    }

    out = _results_with_provenance(
        df,
        "site-1",
        "AHU-1",
        rules,
        point_lookup,
        timestamp_col="timestamp",
    )

    assert len(out) == 1
    ev = out[0].evidence
    assert isinstance(ev, dict)
    assert ev["point_id"] == "pt-123"
    assert ev["external_id"] == "SA-T"
    assert ev["object_identifier"] == "analog-input,2"
    assert ev["object_name"] == "Supply Air Temp"
    assert isinstance(ev.get("source"), dict)
    assert "Supply_Air_Temperature_Sensor" in ev["source"].get("input_keys", [])


def test_results_with_provenance_keeps_fault_when_no_point_lookup_match():
    df = pd.DataFrame(
        [{"timestamp": datetime(2026, 4, 20, 12, 1, 0), "flatline_flag": 1}]
    )
    rules = [{"name": "sensor_flatline", "flag": "flatline_flag", "inputs": {"Unknown": {}}}]

    out = _results_with_provenance(
        df,
        "site-1",
        "AHU-1",
        rules,
        point_lookup={},
        timestamp_col="timestamp",
    )

    assert len(out) == 1
    ev = out[0].evidence
    assert isinstance(ev, dict)
    assert ev.get("point_id") is None
    assert ev["fault_flag"] == "flatline_flag"
