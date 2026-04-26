from __future__ import annotations

from datetime import datetime, timezone
import logging
from unittest.mock import MagicMock
from uuid import uuid4

from openfdd_stack.platform.drivers import onboard


def test_parse_building_filters_accepts_ids_and_names():
    assert onboard.parse_building_filters("66,67") == ["66", "67"]
    assert onboard.parse_building_filters("[66, 67]") == ["66", "67"]
    assert onboard.parse_building_filters('["Office Building"]') == ["Office Building"]
    assert onboard.parse_building_filters("") == []


def test_extract_rows_from_query_result_uses_converted_value():
    site_id = uuid4()
    point_id = uuid4()
    rows = onboard._extract_rows_from_query_result(
        {162748: point_id},
        site_id,
        [
            {
                "point_id": 162748,
                "columns": ["time", "raw", "F"],
                "values": [["2021-05-01T08:00:01Z", "61.5", 61.5]],
            }
        ],
    )
    assert len(rows) == 1
    assert rows[0][1] == str(site_id)
    assert rows[0][2] == point_id
    assert rows[0][3] == 61.5


def test_window_chunks_splits_time_range():
    start = datetime(2021, 5, 1, 8, tzinfo=timezone.utc)
    end = datetime(2021, 5, 1, 18, tzinfo=timezone.utc)
    chunks = onboard._window_chunks(start, end, step_minutes=240)
    assert len(chunks) == 3
    assert chunks[0] == (start, datetime(2021, 5, 1, 12, tzinfo=timezone.utc))
    assert chunks[-1] == (datetime(2021, 5, 1, 16, tzinfo=timezone.utc), end)


class _DummyCursor:
    def execute(self, _sql, _args=None):
        return None


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


def test_run_onboard_ingest_once_runs_backfill_then_incremental(monkeypatch):
    building = {"id": 66, "name": "Example Building"}
    now_start = datetime(2021, 5, 1, 8, tzinfo=timezone.utc)
    now_end = datetime(2021, 5, 1, 10, tzinfo=timezone.utc)
    site_uuid = uuid4()
    point_uuid = uuid4()
    save_calls: list[tuple] = []
    insert_calls: list[int] = []

    class _FakeClient:
        def __init__(self, base_url: str, api_key: str):
            self.base_url = base_url
            self.api_key = api_key

        def get_buildings(self, building_filters):
            assert building_filters == ["Office Building"]
            return [building]

        def get_points(self, building_id):
            assert building_id == 66
            return [{"id": 101, "topic": "onboard/topic/101"}]

        def query_v2(self, _start, _end, _point_ids):
            return [
                {
                    "point_id": 101,
                    "columns": ["time", "raw", "F"],
                    "values": [["2021-05-01T08:00:01Z", "61.5", 61.5]],
                }
            ]

    monkeypatch.setattr(onboard, "OnboardClient", _FakeClient)
    monkeypatch.setattr(onboard, "get_conn", lambda: _DummyConn())
    monkeypatch.setattr(onboard, "resolve_site_uuid", lambda *_args, **_kwargs: site_uuid)
    monkeypatch.setattr(
        onboard,
        "_load_state",
        lambda _cur, _key: {"state_key": "onboard:66", "backfill_done": False, "last_poll_end": None},
    )
    monkeypatch.setattr(
        onboard,
        "_save_state",
        lambda _cur, key, backfill_done, last_poll_end: save_calls.append(
            (key, backfill_done, last_poll_end)
        ),
    )
    monkeypatch.setattr(
        onboard, "_window_chunks", lambda _s, _e, step_minutes=180: [(now_start, now_end)]
    )
    monkeypatch.setattr(onboard, "_upsert_points_for_building", lambda *_args, **_kwargs: ({101: point_uuid}, 1))
    monkeypatch.setattr(
        onboard,
        "_insert_timeseries_rows",
        lambda _cur, rows: insert_calls.append(len(rows)) or len(rows),
    )
    log = MagicMock(spec=logging.Logger)
    summary = onboard.run_onboard_ingest_once(
        log=log,
        base_url="https://api.onboarddata.io",
        api_key="test-key",
        building_filters=["Office Building"],
        backfill_start=now_start,
        scrape_interval_min=180,
        site_id_strategy="onboard-building-id",
        create_points=True,
    )
    assert summary["buildings"] == 1
    assert summary["points_seen"] == 1
    assert summary["rows_inserted"] >= 1
    assert insert_calls
    assert save_calls and any(call[1] is True for call in save_calls)


def test_run_onboard_ingest_once_runs_incremental_after_backfill(monkeypatch):
    building = {"id": 66, "name": "Example Building"}
    now_start = datetime(2021, 5, 1, 8, tzinfo=timezone.utc)
    now_end = datetime(2021, 5, 1, 10, tzinfo=timezone.utc)
    site_uuid = uuid4()
    point_uuid = uuid4()
    save_calls: list[tuple] = []
    insert_calls: list[int] = []
    window_steps: list[int] = []

    class _FakeClient:
        def __init__(self, base_url: str, api_key: str):
            self.base_url = base_url
            self.api_key = api_key

        def get_buildings(self, building_filters):
            assert building_filters == ["Office Building"]
            return [building]

        def get_points(self, building_id):
            assert building_id == 66
            return [{"id": 101, "topic": "onboard/topic/101"}]

        def query_v2(self, _start, _end, _point_ids):
            return [
                {
                    "point_id": 101,
                    "columns": ["time", "raw", "F"],
                    "values": [["2021-05-01T08:00:01Z", "61.5", 61.5]],
                }
            ]

    monkeypatch.setattr(onboard, "OnboardClient", _FakeClient)
    monkeypatch.setattr(onboard, "get_conn", lambda: _DummyConn())
    monkeypatch.setattr(onboard, "resolve_site_uuid", lambda *_args, **_kwargs: site_uuid)
    monkeypatch.setattr(
        onboard,
        "_load_state",
        lambda _cur, _key: {
            "state_key": "onboard:66",
            "backfill_done": True,
            "last_poll_end": now_start,
        },
    )
    monkeypatch.setattr(
        onboard,
        "_save_state",
        lambda _cur, key, backfill_done, last_poll_end: save_calls.append(
            (key, backfill_done, last_poll_end)
        ),
    )
    monkeypatch.setattr(
        onboard,
        "_window_chunks",
        lambda _s, _e, step_minutes=180: window_steps.append(step_minutes) or [(now_start, now_end)],
    )
    monkeypatch.setattr(onboard, "_upsert_points_for_building", lambda *_args, **_kwargs: ({101: point_uuid}, 1))
    monkeypatch.setattr(
        onboard,
        "_insert_timeseries_rows",
        lambda _cur, rows: insert_calls.append(len(rows)) or len(rows),
    )
    log = MagicMock(spec=logging.Logger)
    summary = onboard.run_onboard_ingest_once(
        log=log,
        base_url="https://api.onboarddata.io",
        api_key="test-key",
        building_filters=["Office Building"],
        backfill_start=None,
        scrape_interval_min=180,
        site_id_strategy="onboard-building-id",
        create_points=True,
    )
    assert summary["buildings"] == 1
    assert summary["points_seen"] == 1
    assert summary["rows_inserted"] >= 1
    assert insert_calls
    assert save_calls and save_calls[0][1] is True
    assert window_steps == [180]
