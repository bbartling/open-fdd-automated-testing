"""Router-level tests for points CRUD Selene sync (Phase 2.3c)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from openfdd_stack.platform.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _stub_ttl_sync():
    """Keep tests hermetic (see test_sites_selene_sync for rationale)."""
    with patch("openfdd_stack.platform.api.points.sync_ttl_to_file"):
        yield


def _mock_conn_with_fetchone_sequence(fetchone_seq):
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.rowcount = 1
    cursor.fetchone.side_effect = list(fetchone_seq)
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)
    return conn


@contextmanager
def _patch_db(conn):
    with patch("openfdd_stack.platform.api.points.get_conn", side_effect=lambda: conn):
        yield


def _point_row(point_id, *, site_id=None, external_id="AHU_SA_Temp"):
    return {
        "id": point_id,
        "site_id": site_id or uuid4(),
        "external_id": external_id,
        "brick_type": "Supply_Air_Temperature_Sensor",
        "fdd_input": None,
        "unit": "degF",
        "description": None,
        "equipment_id": None,
        "bacnet_device_id": None,
        "object_identifier": None,
        "object_name": None,
        "polling": True,
        "modbus_config": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_post_point_triggers_selene_upsert_when_backend_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    point_id = uuid4()
    row = _point_row(point_id, site_id=site_id)

    # create_point calls fetchone twice: idempotency SELECT (None) + INSERT RETURNING
    conn = _mock_conn_with_fetchone_sequence([None, row])

    with _patch_db(conn):
        with patch(
            "openfdd_stack.platform.api.points._selene_upsert_point"
        ) as upsert_mock:
            r = client.post(
                "/points",
                json={
                    "site_id": str(site_id),
                    "external_id": "AHU_SA_Temp",
                    "brick_type": "Supply_Air_Temperature_Sensor",
                },
            )

    assert r.status_code == 200, r.text
    upsert_mock.assert_called_once()
    (sent_row,) = upsert_mock.call_args.args
    assert sent_row["id"] == point_id
    assert sent_row["external_id"] == "AHU_SA_Temp"


def test_post_point_idempotent_hit_does_not_trigger_selene_sync(
    monkeypatch: pytest.MonkeyPatch,
):
    """Existing point with same (site_id, external_id) returns the old row \u2014
    no new Postgres write happened, so no Selene sync either (the node is
    already in Selene from the original creation)."""
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    point_id = uuid4()
    row = _point_row(point_id, site_id=site_id)

    # First fetchone returns the existing row, short-circuiting the INSERT.
    conn = _mock_conn_with_fetchone_sequence([row])

    with _patch_db(conn):
        with patch(
            "openfdd_stack.platform.api.points._selene_upsert_point"
        ) as upsert_mock:
            r = client.post(
                "/points",
                json={"site_id": str(site_id), "external_id": "AHU_SA_Temp"},
            )

    assert r.status_code == 200
    upsert_mock.assert_not_called()


def test_delete_point_triggers_selene_delete_when_backend_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    point_id = uuid4()
    # delete_point: fetchone returns {"id": point_id} for the DELETE RETURNING
    conn = _mock_conn_with_fetchone_sequence([{"id": point_id}])

    with _patch_db(conn):
        with patch(
            "openfdd_stack.platform.api.points._selene_delete_point"
        ) as delete_mock:
            r = client.delete(f"/points/{point_id}")

    assert r.status_code == 200, r.text
    delete_mock.assert_called_once_with(str(point_id))


def test_post_point_skips_selene_upsert_when_backend_timescale(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OFDD_STORAGE_BACKEND", raising=False)
    site_id = uuid4()
    point_id = uuid4()
    row = _point_row(point_id, site_id=site_id)

    conn = _mock_conn_with_fetchone_sequence([None, row])

    with _patch_db(conn):
        # Selene client must not be constructed when backend=timescale.
        with patch(
            "openfdd_stack.platform.selene.graph_config.make_selene_client_from_settings",
            side_effect=AssertionError(
                "Selene client must not be constructed when backend=timescale"
            ),
        ):
            r = client.post(
                "/points",
                json={"site_id": str(site_id), "external_id": "p1"},
            )

    assert r.status_code == 200, r.text


def test_post_point_succeeds_even_if_selene_sync_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    point_id = uuid4()
    row = _point_row(point_id, site_id=site_id)

    conn = _mock_conn_with_fetchone_sequence([None, row])

    with _patch_db(conn):
        with patch(
            "openfdd_stack.platform.selene.graph_config.make_selene_client_from_settings",
            side_effect=RuntimeError("selene refused"),
        ):
            r = client.post(
                "/points",
                json={"site_id": str(site_id), "external_id": "p1"},
            )

    assert r.status_code == 200, r.text
