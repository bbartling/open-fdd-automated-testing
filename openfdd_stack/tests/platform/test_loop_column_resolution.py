from datetime import datetime
from unittest.mock import patch
import logging

import openfdd_stack.platform.loop as loop


def test_external_to_semantic_column_map_inverts_unique_pairs():
    out = loop._external_to_semantic_column_map(
        {
            "Zone_Temperature_Sensor": "ZoneTemp",
            "Supply_Air_Temperature_Sensor": "SA-T",
        }
    )
    assert out["ZoneTemp"] == "Zone_Temperature_Sensor"
    assert out["SA-T"] == "Supply_Air_Temperature_Sensor"


def test_runner_column_map_targets_semantic_dataframe_columns():
    out = loop._runner_column_map(
        {
            "Zone_Temperature_Sensor": "ZoneTemp",
            "Supply_Air_Temperature_Sensor": "SA-T",
            "sat": "SA-T",
        }
    )
    assert out["Zone_Temperature_Sensor"] == "Zone_Temperature_Sensor"
    assert out["Supply_Air_Temperature_Sensor"] == "Supply_Air_Temperature_Sensor"
    assert out["sat"] == "Supply_Air_Temperature_Sensor"


def test_load_timeseries_for_site_renames_external_id_columns_to_semantic_keys():
    site_uuid = "11111111-1111-1111-1111-111111111111"
    stage = {"n": 0}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query, _params=None):
            return None

        def fetchall(self):
            stage["n"] += 1
            # First DB call: points list
            if stage["n"] == 1:
                return [
                    {"id": "pt-zone", "external_id": "ZoneTemp"},
                    {"id": "pt-sat", "external_id": "SA-T"},
                ]
            # Second DB call: timeseries rows
            return [
                {
                    "ts": datetime(2026, 4, 24, 10, 0, 0),
                    "external_id": "ZoneTemp",
                    "value": 778.0,
                },
                {
                    "ts": datetime(2026, 4, 24, 10, 0, 0),
                    "external_id": "SA-T",
                    "value": 55.0,
                },
            ]

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    with patch.object(loop, "resolve_site_uuid", return_value=site_uuid), patch.object(
        loop, "get_conn", return_value=FakeConn()
    ):
        df = loop.load_timeseries_for_site(
            site_id="default",
            start_ts=datetime(2026, 4, 24, 9, 0, 0),
            end_ts=datetime(2026, 4, 24, 11, 0, 0),
            column_map={
                "Zone_Temperature_Sensor": "ZoneTemp",
                "Supply_Air_Temperature_Sensor": "SA-T",
            },
        )

    assert df is not None
    assert "Zone_Temperature_Sensor" in df.columns
    assert "Supply_Air_Temperature_Sensor" in df.columns
    assert "ZoneTemp" not in df.columns
    assert "SA-T" not in df.columns


def test_load_timeseries_for_equipment_renames_external_id_columns_to_semantic_keys():
    stage = {"n": 0}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query, _params=None):
            return None

        def fetchall(self):
            stage["n"] += 1
            if stage["n"] == 1:
                return [
                    {"id": "pt-zone", "external_id": "ZoneTemp"},
                    {"id": "pt-zaf", "external_id": "ZAF"},
                ]
            return [
                {
                    "ts": datetime(2026, 4, 24, 10, 0, 0),
                    "external_id": "ZoneTemp",
                    "value": 778.0,
                },
                {
                    "ts": datetime(2026, 4, 24, 10, 0, 0),
                    "external_id": "ZAF",
                    "value": 1200.0,
                },
            ]

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return FakeCursor()

    with patch.object(loop, "get_conn", return_value=FakeConn()):
        df = loop.load_timeseries_for_equipment(
            site_id="site-1",
            equipment_id="VAV-1",
            start_ts=datetime(2026, 4, 24, 9, 0, 0),
            end_ts=datetime(2026, 4, 24, 11, 0, 0),
            column_map={
                "Zone_Temperature_Sensor": "ZoneTemp",
                "Zone_Air_Flow_Sensor": "ZAF",
            },
        )
    assert df is not None
    assert "Zone_Temperature_Sensor" in df.columns
    assert "Zone_Air_Flow_Sensor" in df.columns
    assert "ZoneTemp" not in df.columns
    assert "ZAF" not in df.columns


def test_log_missing_rule_inputs_non_strict_short_circuits_in_strict_mode(caplog):
    caplog.set_level(logging.INFO)
    loop._log_missing_rule_inputs_non_strict(
        df=None,
        rules=[{"name": "r", "inputs": {"Zone_Temperature_Sensor": {}}}],
        strict=True,
        scope="site=x",
        column_map={},
    )
    assert "Non-strict mode: rule" not in caplog.text


def test_log_missing_rule_inputs_non_strict_emits_diagnostic(caplog):
    import pandas as pd

    caplog.set_level(logging.INFO)
    df = pd.DataFrame(
        [{"timestamp": datetime(2026, 4, 24, 10, 0, 0), "Zone_Temperature_Sensor": 72.0}]
    )
    rules = [
        {
            "name": "bad_sensor_check",
            "inputs": {
                "Zone_Temperature_Sensor": {"brick": "Zone_Temperature_Sensor"},
                "Supply_Air_Temperature_Sensor": {"brick": "Supply_Air_Temperature_Sensor"},
            },
        }
    ]
    loop._log_missing_rule_inputs_non_strict(
        df=df,
        rules=rules,
        strict=False,
        scope="site=default equipment=VAV-1",
        column_map={},
    )
    assert "missing inputs after column resolution" in caplog.text
    assert "Supply_Air_Temperature_Sensor" in caplog.text
