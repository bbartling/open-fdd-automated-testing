"""Regression tests for fault provenance evidence in loop results."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
from psycopg2.extras import Json
from open_fdd.schema import FDDResult

from openfdd_stack.platform.loop import (
    _point_lookup_for_equipment,
    _point_lookup_for_site,
    _results_with_provenance,
    _write_fault_results,
)


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


def _mock_conn_capture_execute_values():
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    return conn, cur


def test_write_fault_results_wraps_dict_evidence_for_psycopg2():
    conn, _cur = _mock_conn_capture_execute_values()
    captured = {}

    def _capture(_cur_obj, _sql, rows, page_size=500):
        captured["rows"] = rows
        captured["page_size"] = page_size

    results = [
        FDDResult(
            ts=datetime(2026, 4, 20, 20, 0, 0),
            site_id="site-1",
            equipment_id="AHU-1",
            fault_id="bad_sensor_flag",
            flag_value=1,
            evidence={"point_id": "pt-123"},
        )
    ]

    with patch("openfdd_stack.platform.loop.get_conn", return_value=conn), patch(
        "openfdd_stack.platform.loop.execute_values", side_effect=_capture
    ):
        _write_fault_results(results)

    assert "rows" in captured
    assert captured["page_size"] == 500
    evidence_arg = captured["rows"][0][5]
    assert isinstance(evidence_arg, Json)


def test_point_lookup_for_equipment_includes_fdd_input_key():
    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query, _params=None):
            return None

        def fetchall(self):
            return [
                {
                    "id": "pt-123",
                    "external_id": "SA-T",
                    "fdd_input": "Supply_Air_Temperature_Sensor",
                    "bacnet_device_id": "3456789",
                    "object_identifier": "analog-input,2",
                    "object_name": "Supply Air Temp",
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _Cursor()

    with patch("openfdd_stack.platform.loop.get_conn", return_value=_Conn()):
        lookup = _point_lookup_for_equipment(
            site_id="site-1",
            equipment_id="AHU-1",
            column_map={},
        )

    assert "Supply_Air_Temperature_Sensor" in lookup
    assert lookup["Supply_Air_Temperature_Sensor"]["point_id"] == "pt-123"
    assert lookup["Supply_Air_Temperature_Sensor"]["external_id"] == "SA-T"


def test_point_lookup_for_site_includes_semantic_and_external_keys():
    class _Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query, _params=None):
            return None

        def fetchall(self):
            return [
                {
                    "id": "pt-456",
                    "external_id": "MA-T",
                    "fdd_input": "Mixed_Air_Temperature_Sensor",
                    "bacnet_device_id": "3456789",
                    "object_identifier": "analog-input,3",
                    "object_name": "Mixed Air Temp",
                }
            ]

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _Cursor()

    with patch("openfdd_stack.platform.loop.get_conn", return_value=_Conn()):
        lookup = _point_lookup_for_site(site_id="site-1", column_map={})

    assert "MA-T" in lookup
    assert "Mixed_Air_Temperature_Sensor" in lookup
    assert lookup["MA-T"]["point_id"] == "pt-456"
