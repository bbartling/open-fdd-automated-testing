"""Unit tests for download API."""

from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from openfdd_stack.platform.api.main import app

client = TestClient(app)


def _mock_conn(fetchone=None, fetchall=None):
    """Build a mock DB connection."""
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.rowcount = 1
    cursor.fetchone.return_value = fetchone
    if fetchall is not None:
        cursor.fetchall.return_value = (
            fetchall if isinstance(fetchall, list) else [fetchall]
        )
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    conn.commit = MagicMock()
    return conn


def test_download_csv_404_site_not_found():
    """When resolve_site_uuid returns None, expect 404."""
    with patch("openfdd_stack.platform.api.download.resolve_site_uuid", return_value=None):
        r = client.post(
            "/download/csv",
            json={
                "site_id": "unknown-site",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        )
    assert r.status_code == 404
    msg = (r.json().get("error") or {}).get("message", "") or r.json().get("detail", "")
    assert "No site found" in msg


def test_download_csv_404_no_data():
    """When site exists but no rows, expect 404."""
    site_id = uuid4()
    conn = _mock_conn(fetchall=[])
    with (
        patch("openfdd_stack.platform.api.download.resolve_site_uuid", return_value=site_id),
        patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn),
    ):
        r = client.post(
            "/download/csv",
            json={
                "site_id": str(site_id),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        )
    assert r.status_code == 404
    msg = (r.json().get("error") or {}).get("message", "") or r.json().get("detail", "")
    assert "No data" in msg


def test_download_csv_200_wide():
    """When site exists with data, expect 200 and CSV body; wide = timestamp first (Excel-friendly)."""
    site_id = uuid4()
    rows = [
        {"ts": "2024-01-01 12:00:00", "external_id": "SA-T", "value": 72.5},
        {"ts": "2024-01-01 12:00:00", "external_id": "RA-T", "value": 70.0},
        {"ts": "2024-01-02 12:00:00", "external_id": "SA-T", "value": 73.0},
    ]
    conn = _mock_conn(fetchall=rows)
    with (
        patch("openfdd_stack.platform.api.download.resolve_site_uuid", return_value=site_id),
        patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn),
    ):
        r = client.post(
            "/download/csv",
            json={
                "site_id": str(site_id),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "format": "wide",
            },
        )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    body = r.text
    assert "timestamp" in body
    assert "SA-T" in body
    assert "RA-T" in body
    # Bulk download default: timestamp column on left for Excel/Sheets users (like BAS trend export)
    first_line = body.strip().split("\n")[0]
    assert first_line.startswith("\ufeff") or "timestamp" in first_line
    assert first_line.split(",")[0].lstrip("\ufeff") == "timestamp"


def test_download_csv_200_long():
    """Long format returns ts, point_key, value columns (no point_ids => external_id as point_key)."""
    site_id = uuid4()
    rows = [
        {"ts": "2024-01-01 12:00:00", "external_id": "SA-T", "value": 72.5},
    ]
    conn = _mock_conn(fetchall=rows)
    with (
        patch("openfdd_stack.platform.api.download.resolve_site_uuid", return_value=site_id),
        patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn),
    ):
        r = client.post(
            "/download/csv",
            json={
                "site_id": str(site_id),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "format": "long",
            },
        )
    assert r.status_code == 200
    assert "point_key" in r.text
    assert "SA-T" in r.text


def test_download_csv_200_long_weather_point_ids():
    """POST /download/csv with point_ids (e.g. Web weather page): long format uses point_id as point_key."""
    site_id = uuid4()
    pt_id_1 = uuid4()
    pt_id_2 = uuid4()
    valid_ids = [{"id": pt_id_1}, {"id": pt_id_2}]
    rows = [
        {
            "ts": "2024-01-01 12:00:00",
            "point_id": pt_id_1,
            "external_id": "temp_f",
            "value": 72.5,
        },
        {
            "ts": "2024-01-01 12:00:00",
            "point_id": pt_id_2,
            "external_id": "rh_pct",
            "value": 55.0,
        },
    ]
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchall.side_effect = [valid_ids, rows]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    conn.commit = MagicMock()

    with (
        patch("openfdd_stack.platform.api.download.resolve_site_uuid", return_value=site_id),
        patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn),
    ):
        r = client.post(
            "/download/csv",
            json={
                "site_id": str(site_id),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "format": "long",
                "point_ids": [str(pt_id_1), str(pt_id_2)],
            },
        )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    body = r.text
    assert "point_key" in body
    assert "timestamp" in body or "value" in body
    # point_key column should contain point UUIDs (same way frontend receives for Web weather charts)
    assert str(pt_id_1) in body or str(pt_id_2) in body


def test_download_faults_404_site_not_found():
    """When site_id is provided and site does not exist, expect 404."""
    with patch("openfdd_stack.platform.api.download.resolve_site_uuid", return_value=None):
        r = client.get(
            "/download/faults?site_id=nosuch&start_date=2024-01-01&end_date=2024-01-31&format=csv"
        )
    assert r.status_code == 404
    msg = (r.json().get("error") or {}).get("message", "") or r.json().get("detail", "")
    assert "No site found" in msg


def test_download_faults_site_filter_matches_uuid_or_stored_name():
    """
    Regression: clients (e.g. OpenClaw bench) pass GET /sites UUID while fault_results
    may store site_id as the display name. The WHERE clause must use the same dual-key
    pattern as analytics, not bare site_id = %s.
    """
    site_uuid = uuid4()
    uuid_str = str(site_uuid)
    rows = [
        {
            "ts": "2024-01-15 10:00:00",
            "site_id": "TestBenchSite",
            "equipment_id": "ahu-1",
            "fault_id": "flatline_flag",
            "flag_value": 1,
            "evidence": None,
        },
    ]
    execute_calls: list[tuple[str, tuple | list | None]] = []

    def capture_execute(query, params=None):
        execute_calls.append((query, params))

    cursor = MagicMock()
    cursor.execute = MagicMock(side_effect=capture_execute)
    cursor.fetchall.return_value = rows
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with (
        patch(
            "openfdd_stack.platform.api.download.resolve_site_uuid", return_value=site_uuid
        ),
        patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn),
    ):
        r = client.get(
            f"/download/faults?site_id={uuid_str}"
            "&start_date=2024-01-01&end_date=2024-01-31&format=json"
        )

    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert len(execute_calls) == 1
    q, params = execute_calls[0]
    assert "site_id = %s OR site_id IN (SELECT name FROM sites WHERE id::text = %s)" in q
    assert params is not None
    # date range, then the same site key twice for (direct match OR subquery match)
    assert list(params)[0:2] == [date(2024, 1, 1), date(2024, 1, 31)]
    assert list(params)[2] == uuid_str and list(params)[3] == uuid_str


def test_download_faults_200_csv():
    """Faults CSV: 200, timestamp first column, Excel-friendly (BOM, ISO timestamps)."""
    rows = [
        {
            "ts": "2024-01-15 10:00:00",
            "site_id": "default",
            "equipment_id": "ahu-1",
            "fault_id": "fault_flatline_flag",
            "flag_value": 1,
            "evidence": None,
        },
    ]
    conn = _mock_conn(fetchall=rows)
    with patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn):
        r = client.get(
            "/download/faults?start_date=2024-01-01&end_date=2024-01-31&format=csv"
        )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "openfdd_faults" in r.headers["content-disposition"]
    body = r.text
    assert body.startswith("\ufeff")  # UTF-8 BOM for Excel
    first_line = body.strip().split("\n")[0].lstrip("\ufeff")
    assert first_line.split(",")[0] == "timestamp"
    assert "fault_flatline_flag" in body
    assert "default" in body


def test_download_faults_identity_columns_from_evidence_csv_and_json():
    """When evidence includes point identity, export includes those fields for CSV and JSON."""
    rows = [
        {
            "ts": "2024-01-15 10:00:00",
            "site_id": "default",
            "equipment_id": "AHU-1",
            "fault_id": "bad_sensor_flag",
            "flag_value": 1,
            "evidence": {
                "point_id": "pt-123",
                "external_id": "SA-T",
                "object_identifier": "analog-input,2",
                "object_name": "Supply Air Temp",
            },
        },
    ]
    conn = _mock_conn(fetchall=rows)
    with patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn):
        r_csv = client.get(
            "/download/faults?start_date=2024-01-01&end_date=2024-01-31&format=csv"
        )
    assert r_csv.status_code == 200
    csv_body = r_csv.text
    assert "point_id" in csv_body
    assert "external_id" in csv_body
    assert "object_identifier" in csv_body
    assert "object_name" in csv_body
    assert "pt-123" in csv_body
    assert "SA-T" in csv_body
    assert "analog-input,2" in csv_body
    assert "Supply Air Temp" in csv_body

    conn2 = _mock_conn(fetchall=rows)
    with patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn2):
        r_json = client.get(
            "/download/faults?start_date=2024-01-01&end_date=2024-01-31&format=json"
        )
    assert r_json.status_code == 200
    out = r_json.json()
    row = out["faults"][0]
    assert row["point_id"] == "pt-123"
    assert row["external_id"] == "SA-T"
    assert row["object_identifier"] == "analog-input,2"
    assert row["object_name"] == "Supply Air Temp"


def test_download_faults_rejects_datetime_query_values():
    """Contract: /download/faults accepts date-only query params, not full datetimes."""
    r = client.get(
        "/download/faults?start_date=2026-04-20T11:00:00Z&end_date=2026-04-21T11:00:00Z&format=json"
    )
    assert r.status_code == 422
    errors = (
        (r.json().get("error") or {})
        .get("details", {})
        .get("errors", [])
    )
    assert isinstance(errors, list)
    assert any("start_date" in str(d.get("loc", "")) for d in errors if isinstance(d, dict))
    assert any("zero time" in str(d.get("msg", "")).lower() for d in errors if isinstance(d, dict))


def test_download_faults_200_json():
    """Faults JSON: 200, faults array and count for API/cloud integration."""
    rows = [
        {
            "ts": "2024-01-15 10:00:00",
            "site_id": "default",
            "equipment_id": "ahu-1",
            "fault_id": "fault_flatline_flag",
            "flag_value": 1,
            "evidence": None,
        },
    ]
    conn = _mock_conn(fetchall=rows)
    with patch("openfdd_stack.platform.api.download.get_conn", side_effect=lambda: conn):
        r = client.get(
            "/download/faults?start_date=2024-01-01&end_date=2024-01-31&format=json"
        )
    assert r.status_code == 200
    data = r.json()
    assert "faults" in data
    assert data["count"] == 1
    assert data["faults"][0]["fault_id"] == "fault_flatline_flag"
    assert "ts" in data["faults"][0]
