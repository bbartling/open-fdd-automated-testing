from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd

from openfdd_stack.platform.drivers import csv_driver


def test_parse_csv_sources_json():
    sources = csv_driver.parse_csv_sources(
        '[{"path":"examples/csv/AHU7.csv","site_id":"ahu7"},{"path":"examples/csv/RTU11.csv","site_id":"rtu11"}]'
    )
    assert len(sources) == 2
    assert sources[0].path.endswith("AHU7.csv")
    assert sources[0].site_id == "ahu7"


def test_infer_timestamp_column():
    col = csv_driver._infer_timestamp_column(["Value", "Timestamp", "Other"])
    assert col == "Timestamp"


class _DummyCursor:
    def __init__(self):
        self._last_sql = ""
        self._last_args = None

    def execute(self, sql, args=None):
        self._last_sql = str(sql)
        self._last_args = args

    def fetchone(self):
        if "FROM csv_ingest_state" in self._last_sql:
            return None
        if "RETURNING id" in self._last_sql:
            return {"id": uuid4()}
        return None

    def fetchall(self):
        return []


class _DummyConn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        class _Ctx:
            def __enter__(self_nonlocal):
                return _DummyCursor()

            def __exit__(self_nonlocal, exc_type, exc, tb):
                return False

        return _Ctx()

    def commit(self):
        return None

    def rollback(self):
        return None


def test_run_csv_ingest_once(monkeypatch):
    inserted_counts: list[int] = []

    monkeypatch.setattr(csv_driver, "get_conn", lambda: _DummyConn())
    monkeypatch.setattr(csv_driver, "resolve_site_uuid", lambda *_args, **_kwargs: uuid4())
    monkeypatch.setattr(
        csv_driver,
        "pd",
        type(
            "P",
            (),
            {
                "read_csv": staticmethod(
                    lambda _p: pd.DataFrame(
                        {
                            "timestamp": ["2025-01-01 00:00:00", "2025-01-01 01:00:00"],
                            "SAT (°F)": [60.0, 61.0],
                            "MAT (°F)": [55.0, 56.0],
                        }
                    )
                ),
                "to_datetime": staticmethod(pd.to_datetime),
            },
        ),
    )
    monkeypatch.setattr(
        csv_driver,
        "_insert_timeseries_rows",
        lambda _cur, rows: inserted_counts.append(len(rows)) or len(rows),
    )
    monkeypatch.setattr(csv_driver.Path, "exists", lambda _self: True)

    summary = csv_driver.run_csv_ingest_once(
        log=type("L", (), {"warning": lambda *a, **k: None})(),
        sources=[csv_driver.CsvSource(path="examples/csv/AHU7.csv", site_id="ahu7")],
        backfill_start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        backfill_end=None,
        create_points=True,
    )
    assert summary["sources"] == 1
    assert summary["rows_inserted"] == 2
    assert inserted_counts == [2]
