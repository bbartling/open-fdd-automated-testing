"""Fault state API tests (GET /faults/active, /faults/state, /faults/definitions, /faults/bacnet-devices)."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from openfdd_stack.platform.api.main import app

client = TestClient(app)

_SITE_FILTER_SQL_FRAGMENT = (
    "fs.site_id = %s OR fs.site_id IN (SELECT name FROM sites WHERE id::text = %s)"
)


def _make_conn_with_execute_capture() -> tuple[MagicMock, list[tuple[str, tuple | list | None]]]:
    """Context-manager conn + cursor that record every cursor.execute(query, params)."""
    execute_calls: list[tuple[str, tuple | list | None]] = []

    def capture_execute(query, params=None):
        execute_calls.append((query, params))

    cursor = MagicMock()
    cursor.execute = MagicMock(side_effect=capture_execute)
    cursor.fetchall.return_value = []
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    return conn, execute_calls


def _assert_site_filter_execute(
    execute_calls: list[tuple[str, tuple | list | None]], site_key: str
) -> None:
    assert any(
        _SITE_FILTER_SQL_FRAGMENT in q and params == (site_key, site_key)
        for q, params in execute_calls
    ), f"expected site filter SQL + params in execute_calls, got: {execute_calls!r}"


def test_faults_bacnet_devices_returns_list():
    """GET /faults/bacnet-devices returns list from data model (points + equipment)."""
    with patch("openfdd_stack.platform.api.faults.get_conn") as mock_conn:
        conn = MagicMock()
        cur = MagicMock()
        cur.fetchall.return_value = []
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=None)
        mock_conn.return_value = conn
        r = client.get("/faults/bacnet-devices")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        assert "bacnet_device_id" in data[0] and "equipment_name" in data[0]


def test_faults_active_empty_without_table():
    with patch(
        "openfdd_stack.platform.api.faults._fault_state_table_exists", return_value=False
    ):
        r = client.get("/faults/active")
    assert r.status_code == 200
    assert r.json() == []


def test_faults_definitions_returns_list():
    r = client.get("/faults/definitions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_faults_bacnet_device_faults_infers_applicable_from_rule_brick_inputs(tmp_path):
    point_rows = [
        {
            "point_id": "pt-1",
            "site_uuid": "site-1",
            "site_name": "default",
            "bacnet_device_id": "3456789",
            "equipment_id": "eq-1",
            "equipment_name": "AHU-1",
            "equipment_type": "AHU",
            "external_id": "SA-T",
            "fdd_input": "sat",
            "brick_type": "brick:Supply_Air_Temperature_Sensor",
            "object_identifier": "analog-input,2",
            "object_name": "SA-T",
        }
    ]
    state_rows = [
        {
            "site_id": "default",
            "equipment_id": "eq-1",
            "fault_id": "flatline_flag",
            "active": True,
        }
    ]

    cursor = MagicMock()
    cursor.fetchall.side_effect = [point_rows, state_rows]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    fake_rules = [
        {
            "name": "bad_sensor_check",
            "flag": "bad_sensor_flag",
            "inputs": {
                "Supply_Air_Temperature_Sensor": {
                    "brick": "Supply_Air_Temperature_Sensor"
                }
            },
        }
    ]

    with (
        patch("openfdd_stack.platform.api.faults.get_conn", return_value=conn),
        patch(
            "openfdd_stack.platform.api.faults._rules_dir_resolved",
            return_value=str(tmp_path),
        ),
        patch("open_fdd.engine.runner.load_rules_from_dir", return_value=fake_rules),
    ):
        r = client.get("/faults/bacnet-device-faults")

    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    row = data[0]
    assert row["bacnet_device_id"] == "3456789"
    assert "bad_sensor_flag" in row["applicable_fault_ids"]
    assert "flatline_flag" in row["active_fault_ids"]
    matched = row["matched_points_by_fault"]["bad_sensor_flag"]
    assert len(matched) == 1
    assert matched[0]["external_id"] == "SA-T"


def test_faults_bacnet_device_faults_maps_active_when_fault_state_uses_equipment_name(
    tmp_path,
):
    point_rows = [
        {
            "point_id": "pt-1",
            "site_uuid": "site-1",
            "site_name": "default",
            "bacnet_device_id": "3456789",
            "equipment_id": "eq-uuid-1",
            "equipment_name": "AHU-1",
            "equipment_type": "AHU",
            "external_id": "SA-T",
            "fdd_input": "sat",
            "brick_type": "brick:Supply_Air_Temperature_Sensor",
            "object_identifier": "analog-input,2",
            "object_name": "SA-T",
        }
    ]
    state_rows = [
        {
            "site_id": "site-1",
            "equipment_id": "AHU-1",
            "fault_id": "bad_sensor_flag",
            "active": True,
        },
        {
            "site_id": "site-1",
            "equipment_id": "AHU-1",
            "fault_id": "flatline_flag",
            "active": True,
        },
    ]

    cursor = MagicMock()
    cursor.fetchall.side_effect = [point_rows, state_rows]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    fake_rules = [
        {"name": "bad_sensor_check", "flag": "bad_sensor_flag", "inputs": {}},
        {"name": "flatline_check", "flag": "flatline_flag", "inputs": {}},
    ]

    with (
        patch("openfdd_stack.platform.api.faults.get_conn", return_value=conn),
        patch(
            "openfdd_stack.platform.api.faults._rules_dir_resolved",
            return_value=str(tmp_path),
        ),
        patch("open_fdd.engine.runner.load_rules_from_dir", return_value=fake_rules),
    ):
        r = client.get("/faults/bacnet-device-faults?site_id=site-1")

    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    row = data[0]
    assert row["bacnet_device_id"] == "3456789"
    assert sorted(row["active_fault_ids"]) == ["bad_sensor_flag", "flatline_flag"]


def test_faults_bacnet_device_faults_active_mapping_is_device_id_agnostic(tmp_path):
    dynamic_device_id = "998877"
    point_rows = [
        {
            "point_id": "pt-2",
            "site_uuid": "site-x",
            "site_name": "Building-X",
            "bacnet_device_id": dynamic_device_id,
            "equipment_id": "equip-uuid-x",
            "equipment_name": "RTU-7",
            "equipment_type": "RTU",
            "external_id": "ZN-T",
            "fdd_input": "znt",
            "brick_type": "brick:Zone_Air_Temperature_Sensor",
            "object_identifier": "analog-input,11",
            "object_name": "ZN-T",
        }
    ]
    state_rows = [
        {
            "site_id": "Building-X",
            "equipment_id": "RTU-7",
            "fault_id": "flatline_flag",
            "active": True,
        }
    ]

    cursor = MagicMock()
    cursor.fetchall.side_effect = [point_rows, state_rows]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    fake_rules = [{"name": "flatline_check", "flag": "flatline_flag", "inputs": {}}]

    with (
        patch("openfdd_stack.platform.api.faults.get_conn", return_value=conn),
        patch(
            "openfdd_stack.platform.api.faults._rules_dir_resolved",
            return_value=str(tmp_path),
        ),
        patch("open_fdd.engine.runner.load_rules_from_dir", return_value=fake_rules),
    ):
        r = client.get("/faults/bacnet-device-faults?site_id=site-x")

    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    row = data[0]
    assert row["bacnet_device_id"] == dynamic_device_id
    assert row["active_fault_ids"] == ["flatline_flag"]


def test_faults_bacnet_device_faults_handles_missing_fault_state_table(tmp_path):
    point_rows = [
        {
            "point_id": "pt-3",
            "site_uuid": "site-z",
            "site_name": "Building-Z",
            "bacnet_device_id": "123123",
            "equipment_id": "equip-z",
            "equipment_name": "AHU-Z",
            "equipment_type": "AHU",
            "external_id": "SA-T",
            "fdd_input": "sat",
            "brick_type": "brick:Supply_Air_Temperature_Sensor",
            "object_identifier": "analog-input,2",
            "object_name": "SA-T",
        }
    ]

    cursor = MagicMock()
    cursor.fetchall.side_effect = [point_rows]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    fake_rules = [{"name": "bad_sensor_check", "flag": "bad_sensor_flag", "inputs": {}}]

    with (
        patch("openfdd_stack.platform.api.faults.get_conn", return_value=conn),
        patch(
            "openfdd_stack.platform.api.faults._rules_dir_resolved",
            return_value=str(tmp_path),
        ),
        patch("openfdd_stack.platform.api.faults._fault_state_table_exists", return_value=False),
        patch("open_fdd.engine.runner.load_rules_from_dir", return_value=fake_rules),
    ):
        r = client.get("/faults/bacnet-device-faults")

    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["bacnet_device_id"] == "123123"
    assert data[0]["active_fault_ids"] == []


def test_faults_active_site_filter_matches_uuid_or_stored_name():
    """
    Regression: /faults/active?site_id=<uuid> must match fault_state rows keyed by site
    display name (legacy) or UUID, same as /download/faults and analytics.
    """
    site_key = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    conn, execute_calls = _make_conn_with_execute_capture()

    with (
        patch(
            "openfdd_stack.platform.api.faults._fault_state_table_exists", return_value=True
        ),
        patch("openfdd_stack.platform.api.faults.get_conn", side_effect=lambda: conn),
    ):
        r = client.get(f"/faults/active?site_id={site_key}")

    assert r.status_code == 200
    assert r.json() == []
    assert len(execute_calls) >= 1
    _assert_site_filter_execute(execute_calls, site_key)


def test_faults_state_site_filter_matches_uuid_or_stored_name():
    """GET /faults/state?site_id= uses same dual-key site filter as /faults/active."""
    site_key = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    conn, execute_calls = _make_conn_with_execute_capture()

    with (
        patch(
            "openfdd_stack.platform.api.faults._fault_state_table_exists", return_value=True
        ),
        patch("openfdd_stack.platform.api.faults.get_conn", side_effect=lambda: conn),
    ):
        r = client.get(f"/faults/state?site_id={site_key}")

    assert r.status_code == 200
    assert r.json() == []
    assert len(execute_calls) >= 1
    _assert_site_filter_execute(execute_calls, site_key)


def test_faults_state_bacnet_subquery_handles_equipment_name_or_uuid():
    """
    Regression: fault_state.equipment_id can be an equipment name (e.g. "AHU-1")
    while points.equipment_id is UUID. Subquery must support both forms.
    """
    conn, execute_calls = _make_conn_with_execute_capture()

    with (
        patch(
            "openfdd_stack.platform.api.faults._fault_state_table_exists", return_value=True
        ),
        patch("openfdd_stack.platform.api.faults.get_conn", side_effect=lambda: conn),
    ):
        r = client.get("/faults/state")

    assert r.status_code == 200
    assert any(
        "p.equipment_id::text = fs.equipment_id" in q and "e.name = fs.equipment_id" in q
        for q, _ in execute_calls
    ), f"expected name/uuid tolerant bacnet_subquery, got: {execute_calls!r}"
