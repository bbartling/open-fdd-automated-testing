"""Router-level tests for equipment CRUD Selene sync (Phase 2.3b)."""

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
    with patch("openfdd_stack.platform.api.equipment.sync_ttl_to_file"):
        yield


def _mock_conn(fetchone=None, fetchall=None):
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


@contextmanager
def _patch_db(conn):
    with patch(
        "openfdd_stack.platform.api.equipment.get_conn", side_effect=lambda: conn
    ):
        yield


def _equipment_row(
    equipment_id,
    *,
    site_id=None,
    name="AHU-1",
    equipment_type="AHU",
):
    return {
        "id": equipment_id,
        "site_id": site_id or uuid4(),
        "name": name,
        "description": None,
        "equipment_type": equipment_type,
        "metadata": {},
        "feeds_equipment_id": None,
        "fed_by_equipment_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_post_equipment_triggers_selene_upsert_when_backend_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    equipment_id = uuid4()
    row = _equipment_row(equipment_id, site_id=site_id)

    cursor = MagicMock()
    cursor.execute.return_value = None
    # POST calls fetchone twice: duplicate-check (None) + INSERT RETURNING (row)
    cursor.fetchone.side_effect = [None, row]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with patch(
        "openfdd_stack.platform.api.equipment.get_conn", side_effect=lambda: conn
    ):
        with patch(
            "openfdd_stack.platform.api.equipment._selene_upsert_equipment"
        ) as upsert_mock:
            r = client.post(
                "/equipment",
                json={
                    "site_id": str(site_id),
                    "name": "AHU-1",
                    "equipment_type": "AHU",
                },
            )

    assert r.status_code == 200, r.text
    upsert_mock.assert_called_once()
    (sent_row,) = upsert_mock.call_args.args
    assert sent_row["id"] == equipment_id
    assert sent_row["site_id"] == site_id


def test_delete_equipment_triggers_selene_delete_when_backend_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    equipment_id = uuid4()
    conn = _mock_conn(fetchone={"id": equipment_id})
    with _patch_db(conn):
        with patch(
            "openfdd_stack.platform.api.equipment._selene_delete_equipment"
        ) as delete_mock:
            r = client.delete(f"/equipment/{equipment_id}")

    assert r.status_code == 200, r.text
    delete_mock.assert_called_once_with(str(equipment_id))


def test_post_equipment_skips_selene_upsert_when_backend_timescale(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OFDD_STORAGE_BACKEND", raising=False)
    site_id = uuid4()
    equipment_id = uuid4()
    row = _equipment_row(equipment_id, site_id=site_id)

    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.side_effect = [None, row]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with patch(
        "openfdd_stack.platform.api.equipment.get_conn", side_effect=lambda: conn
    ):
        with patch(
            "openfdd_stack.platform.selene.graph_config.make_selene_client_from_settings",
            side_effect=AssertionError(
                "Selene client must not be constructed when backend=timescale"
            ),
        ):
            r = client.post(
                "/equipment",
                json={
                    "site_id": str(site_id),
                    "name": "Bare",
                    "equipment_type": "AHU",
                },
            )

    assert r.status_code == 200, r.text


def test_post_equipment_succeeds_even_if_selene_sync_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    equipment_id = uuid4()
    row = _equipment_row(equipment_id, site_id=site_id)

    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.side_effect = [None, row]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with patch(
        "openfdd_stack.platform.api.equipment.get_conn", side_effect=lambda: conn
    ):
        with patch(
            "openfdd_stack.platform.selene.graph_config.make_selene_client_from_settings",
            side_effect=RuntimeError("selene refused"),
        ):
            r = client.post(
                "/equipment",
                json={
                    "site_id": str(site_id),
                    "name": "AHU-1",
                    "equipment_type": "AHU",
                },
            )

    assert r.status_code == 200, r.text
