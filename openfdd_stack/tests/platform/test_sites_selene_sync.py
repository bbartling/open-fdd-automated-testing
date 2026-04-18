"""Router-level tests for sites CRUD Selene sync (Phase 2.3a).

Confirms that when ``OFDD_STORAGE_BACKEND=selene``, POST / PATCH / DELETE on
``/sites`` triggers the graph_crud sync helpers; when the flag is unset or
``timescale``, the sync is not called (zero behavior change on default
deployments).
"""

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
    """Keep these tests hermetic: the real ``sync_ttl_to_file`` schedules a
    background Timer and touches the filesystem, which can leak threads and
    introduce cross-test flake. Matches the pattern in ``test_crud_api.py``.
    """
    with patch("openfdd_stack.platform.api.sites.sync_ttl_to_file"):
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
    with patch("openfdd_stack.platform.api.sites.get_conn", side_effect=lambda: conn):
        yield


def _site_row(site_id, name="HQ", description=None, metadata=None):
    return {
        "id": site_id,
        "name": name,
        "description": description,
        "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# backend = selene: sync helpers are invoked
# ---------------------------------------------------------------------------


def test_post_site_triggers_selene_upsert_when_backend_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()

    # create_site calls fetchone TWICE: once for duplicate-name check (None),
    # once for the INSERT ... RETURNING row.
    fetchone_row = _site_row(site_id, name="HQ")
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.side_effect = [None, fetchone_row]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with patch("openfdd_stack.platform.api.sites.get_conn", side_effect=lambda: conn):
        with patch(
            "openfdd_stack.platform.api.sites._selene_upsert_site"
        ) as upsert_mock:
            r = client.post("/sites", json={"name": "HQ"})

    assert r.status_code == 200, r.text
    upsert_mock.assert_called_once()
    # Argument should be the row dict
    (sent_row,) = upsert_mock.call_args.args
    assert sent_row["id"] == site_id
    assert sent_row["name"] == "HQ"


def test_patch_site_triggers_selene_upsert_when_backend_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    updated = _site_row(site_id, name="HQ v2", description="new")

    conn = _mock_conn(fetchone=updated)
    with _patch_db(conn):
        with patch(
            "openfdd_stack.platform.api.sites._selene_upsert_site"
        ) as upsert_mock:
            r = client.patch(f"/sites/{site_id}", json={"description": "new"})

    assert r.status_code == 200, r.text
    upsert_mock.assert_called_once()


def test_delete_site_triggers_selene_delete_when_backend_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    # delete_site fetchone returns row with id + name
    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.return_value = {"id": site_id, "name": "HQ"}
    cursor.rowcount = 1
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with patch("openfdd_stack.platform.api.sites.get_conn", side_effect=lambda: conn):
        with patch(
            "openfdd_stack.platform.api.sites._selene_delete_site"
        ) as delete_mock:
            r = client.delete(f"/sites/{site_id}")

    assert r.status_code == 200, r.text
    delete_mock.assert_called_once_with(str(site_id))


# ---------------------------------------------------------------------------
# backend = timescale (default): sync helpers are NOT invoked
# ---------------------------------------------------------------------------


def test_post_site_skips_selene_upsert_when_backend_timescale(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("OFDD_STORAGE_BACKEND", raising=False)
    site_id = uuid4()
    fetchone_row = _site_row(site_id)

    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.side_effect = [None, fetchone_row]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with patch("openfdd_stack.platform.api.sites.get_conn", side_effect=lambda: conn):
        # The helper is called but should early-return before touching Selene —
        # patch make_selene_client_from_settings to fail loudly if reached.
        with patch(
            "openfdd_stack.platform.selene.graph_config.make_selene_client_from_settings",
            side_effect=AssertionError(
                "Selene client must not be constructed when backend=timescale"
            ),
        ):
            r = client.post("/sites", json={"name": "Default"})

    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# backend = selene but sync fails: CRUD still succeeds
# ---------------------------------------------------------------------------


def test_post_site_succeeds_even_if_selene_sync_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    site_id = uuid4()
    fetchone_row = _site_row(site_id)

    cursor = MagicMock()
    cursor.execute.return_value = None
    cursor.fetchone.side_effect = [None, fetchone_row]
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=None)
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    with patch("openfdd_stack.platform.api.sites.get_conn", side_effect=lambda: conn):
        # Make make_selene_client_from_settings raise; _selene_upsert_site must
        # swallow and log, not fail the request.
        with patch(
            "openfdd_stack.platform.selene.graph_config.make_selene_client_from_settings",
            side_effect=RuntimeError("selene refused"),
        ):
            r = client.post("/sites", json={"name": "HQ"})

    assert r.status_code == 200, r.text
