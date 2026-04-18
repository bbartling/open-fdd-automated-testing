"""Backend-branching behavior in graph_model when OFDD_STORAGE_BACKEND=selene.

Confirms that the rdflib boot path is short-circuited and delegation to
SeleneConfigStore happens, without touching the rdflib module globals. These
tests do not require a running Selene — the SeleneClient is built from
settings via the shared factory, so we patch the store factory to feed a
MockTransport-backed client.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import httpx
import pytest

pytest.importorskip("pydantic_settings")

import openfdd_stack.platform.graph_model as graph_model_mod
from openfdd_stack.platform.selene import SELENE_CONFIG_LABEL, SeleneClient


def _mock_selene(handler) -> SeleneClient:
    return SeleneClient(
        "http://selene.local:8080",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _force_selene_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")
    # get_platform_settings() constructs fresh PlatformSettings on each call
    # (no caching), so monkeypatched env is picked up without invalidation.


def test_load_from_file_is_noop_when_selene_backend(monkeypatch: pytest.MonkeyPatch):
    """Selene owns graph state; no TTL file should be read or parsed."""
    _force_selene_backend(monkeypatch)

    with patch.object(graph_model_mod, "_ensure_graph") as ensure:
        graph_model_mod.load_from_file()
    ensure.assert_not_called()


def test_start_sync_thread_is_noop_when_selene_backend(monkeypatch: pytest.MonkeyPatch):
    """No background TTL serializer thread should spin up."""
    _force_selene_backend(monkeypatch)

    # Preserve module state — start/stop side-effects between tests.
    graph_model_mod._sync_thread = None
    graph_model_mod.start_sync_thread()
    assert graph_model_mod._sync_thread is None


def test_write_ttl_to_file_reports_success_without_writing(
    monkeypatch: pytest.MonkeyPatch,
):
    """Health state updates optimistically; no filesystem write happens."""
    _force_selene_backend(monkeypatch)

    graph_model_mod._last_serialization_ok = None
    graph_model_mod._last_serialization_error = "stale"
    ok, err = graph_model_mod.write_ttl_to_file()
    assert ok is True
    assert err is None
    assert graph_model_mod._last_serialization_ok is True
    assert graph_model_mod._last_serialization_error is None


def test_get_config_from_graph_reads_from_selene(monkeypatch: pytest.MonkeyPatch):
    """With selene backend, delegates to SeleneConfigStore.read_config()."""
    _force_selene_backend(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/nodes"
        assert request.url.params["label"] == SELENE_CONFIG_LABEL
        return httpx.Response(
            200,
            json={
                "nodes": [
                    {
                        "id": 9,
                        "labels": [SELENE_CONFIG_LABEL],
                        "properties": {
                            "rule_interval_hours": 3.0,
                            "bacnet_site_id": "default",
                        },
                    }
                ],
                "total": 1,
            },
        )

    client = _mock_selene(handler)
    # Patch the factory to return our MockTransport-backed client.
    monkeypatch.setattr(
        graph_model_mod,
        "_selene_config_store",
        lambda: (
            __import__(
                "openfdd_stack.platform.selene.graph_config",
                fromlist=["SeleneConfigStore"],
            ).SeleneConfigStore(client),
            client,
        ),
    )
    assert graph_model_mod.get_config_from_graph() == {
        "rule_interval_hours": 3.0,
        "bacnet_site_id": "default",
    }


def test_get_config_from_graph_degrades_gracefully_when_selene_unreachable(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """Boot must not block when Selene is temporarily down."""
    _force_selene_backend(monkeypatch)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = _mock_selene(handler)
    monkeypatch.setattr(
        graph_model_mod,
        "_selene_config_store",
        lambda: (
            __import__(
                "openfdd_stack.platform.selene.graph_config",
                fromlist=["SeleneConfigStore"],
            ).SeleneConfigStore(client),
            client,
        ),
    )

    with caplog.at_level("WARNING"):
        assert graph_model_mod.get_config_from_graph() == {}
    assert any("selene read_config failed" in rec.message for rec in caplog.records)


def test_set_config_in_graph_writes_to_selene(monkeypatch: pytest.MonkeyPatch):
    _force_selene_backend(monkeypatch)
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            import json as _json

            seen["body"] = _json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 1,
                    "labels": [SELENE_CONFIG_LABEL],
                    "properties": seen["body"]["properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    client = _mock_selene(handler)
    monkeypatch.setattr(
        graph_model_mod,
        "_selene_config_store",
        lambda: (
            __import__(
                "openfdd_stack.platform.selene.graph_config",
                fromlist=["SeleneConfigStore"],
            ).SeleneConfigStore(client),
            client,
        ),
    )

    graph_model_mod.set_config_in_graph({"rule_interval_hours": 2.0})
    assert seen["body"]["properties"] == {"rule_interval_hours": 2.0}


def test_timescale_backend_still_uses_rdflib(monkeypatch: pytest.MonkeyPatch):
    """Default (timescale) path must remain unchanged; _ensure_graph gets called."""
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "timescale")

    with patch.object(
        graph_model_mod, "_ensure_graph", wraps=graph_model_mod._ensure_graph
    ) as ensure:
        # get_config_from_graph exercises the rdflib branch; no selene client used.
        graph_model_mod.get_config_from_graph()
    ensure.assert_called()


# ---------------------------------------------------------------------------
# Backend-parity: only RDF-backed keys (CONFIG_KEY_TO_PREDICATE) are exposed
# to callers or persisted. Prevents arbitrary Selene properties from leaking
# into settings overlay (and sensitive fields from being written back).
# ---------------------------------------------------------------------------


def test_get_config_from_graph_filters_non_whitelisted_keys(
    monkeypatch: pytest.MonkeyPatch,
):
    _force_selene_backend(monkeypatch)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "nodes": [
                    {
                        "id": 1,
                        "labels": [SELENE_CONFIG_LABEL],
                        "properties": {
                            "rule_interval_hours": 3.0,  # whitelisted
                            "api_key": "SECRET",  # not in CONFIG_KEY_TO_PREDICATE
                            "jwt_secret": "NO",  # not in CONFIG_KEY_TO_PREDICATE
                            "storage_backend": "selene",  # not in CONFIG_KEY_TO_PREDICATE
                        },
                    }
                ],
                "total": 1,
            },
        )

    client = _mock_selene(handler)
    monkeypatch.setattr(
        graph_model_mod,
        "_selene_config_store",
        lambda: (
            __import__(
                "openfdd_stack.platform.selene.graph_config",
                fromlist=["SeleneConfigStore"],
            ).SeleneConfigStore(client),
            client,
        ),
    )

    out = graph_model_mod.get_config_from_graph()
    assert out == {"rule_interval_hours": 3.0}


def test_set_config_in_graph_filters_non_whitelisted_keys(
    monkeypatch: pytest.MonkeyPatch,
):
    _force_selene_backend(monkeypatch)
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        import json as _json

        seen["body"] = _json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [SELENE_CONFIG_LABEL],
                "properties": seen["body"]["properties"],
            },
        )

    client = _mock_selene(handler)
    monkeypatch.setattr(
        graph_model_mod,
        "_selene_config_store",
        lambda: (
            __import__(
                "openfdd_stack.platform.selene.graph_config",
                fromlist=["SeleneConfigStore"],
            ).SeleneConfigStore(client),
            client,
        ),
    )

    graph_model_mod.set_config_in_graph(
        {
            "rule_interval_hours": 3.0,
            "api_key": "SECRET",
            "jwt_secret": "NO",
            "unknown_future_key": "drop_me",
        }
    )
    # Only the whitelisted RDF-backed key must reach the wire.
    assert seen["body"]["properties"] == {"rule_interval_hours": 3.0}


def test_write_config_remove_properties_are_sorted():
    """Deterministic ordering for easier log / snapshot comparison."""
    import json as _json

    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 5,
                            "labels": [SELENE_CONFIG_LABEL],
                            "properties": {
                                "zulu_key": 1,
                                "alpha_key": 2,
                                "mike_key": 3,
                                "lookback_days": 3,
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        seen["body"] = _json.loads(request.content)
        return httpx.Response(200, json={"id": 5, "labels": [SELENE_CONFIG_LABEL]})

    client = _mock_selene(handler)
    from openfdd_stack.platform.selene.graph_config import SeleneConfigStore

    SeleneConfigStore(client).write_config({"lookback_days": 7})
    # Stale keys are zulu_key, alpha_key, mike_key — expect alphabetical:
    assert seen["body"]["remove_properties"] == ["alpha_key", "mike_key", "zulu_key"]
