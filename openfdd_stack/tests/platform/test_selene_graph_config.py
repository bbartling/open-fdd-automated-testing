"""Unit tests for the SeleneDB-backed platform config store."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from openfdd_stack.platform.selene import (
    SELENE_CONFIG_LABEL,
    SeleneClient,
    SeleneConfigStore,
    SeleneError,
)


def _mock_client(handler) -> SeleneClient:
    return SeleneClient(
        "http://selene.local:8080",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def test_read_config_returns_empty_on_missing_node():
    """Fresh Selene with no ofdd_platform_config node yet."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/nodes"
        assert request.url.params["label"] == SELENE_CONFIG_LABEL
        return httpx.Response(200, json={"nodes": [], "total": 0})

    with _mock_client(handler) as client:
        assert SeleneConfigStore(client).read_config() == {}


def test_read_config_returns_properties_from_first_node():
    config = {
        "rule_interval_hours": 3.0,
        "lookback_days": 3,
        "bacnet_server_url": "http://host.docker.internal:8080",
    }

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "nodes": [
                    {"id": 42, "labels": [SELENE_CONFIG_LABEL], "properties": config}
                ],
                "total": 1,
            },
        )

    with _mock_client(handler) as client:
        assert SeleneConfigStore(client).read_config() == config


def test_read_config_warns_but_returns_first_on_duplicates(caplog):
    config = {"rule_interval_hours": 3.0}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "nodes": [
                    {"id": 1, "labels": [SELENE_CONFIG_LABEL], "properties": config},
                    {"id": 2, "labels": [SELENE_CONFIG_LABEL], "properties": {}},
                ],
                "total": 2,
            },
        )

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            assert SeleneConfigStore(client).read_config() == config
    assert any(SELENE_CONFIG_LABEL in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# Write (upsert)
# ---------------------------------------------------------------------------


def test_write_config_creates_node_when_absent():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 7,
                    "labels": [SELENE_CONFIG_LABEL],
                    "properties": captured["body"]["properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        result = SeleneConfigStore(client).write_config(
            {"rule_interval_hours": 3.0, "lookback_days": 3}
        )
    assert captured["body"]["labels"] == [SELENE_CONFIG_LABEL]
    assert captured["body"]["properties"] == {
        "rule_interval_hours": 3.0,
        "lookback_days": 3,
    }
    assert result["id"] == 7


def test_write_config_updates_existing_node_and_removes_stale_keys():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 11,
                            "labels": [SELENE_CONFIG_LABEL],
                            "properties": {
                                "rule_interval_hours": 3.0,
                                "deprecated_key": "removeme",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "PUT" and request.url.path == "/nodes/11":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "id": 11,
                    "labels": [SELENE_CONFIG_LABEL],
                    "properties": captured["body"]["set_properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        SeleneConfigStore(client).write_config(
            {"rule_interval_hours": 4.0, "lookback_days": 7}
        )

    assert captured["body"]["set_properties"] == {
        "rule_interval_hours": 4.0,
        "lookback_days": 7,
    }
    # deprecated_key must be scheduled for removal
    assert "deprecated_key" in captured["body"]["remove_properties"]


def test_write_config_skips_none_values():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [SELENE_CONFIG_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    with _mock_client(handler) as client:
        SeleneConfigStore(client).write_config(
            {"rule_interval_hours": 3.0, "jwt_secret": None, "bacnet_gateways": None}
        )
    assert captured["body"]["properties"] == {"rule_interval_hours": 3.0}


# ---------------------------------------------------------------------------
# Auth / network failure surfaces as typed error
# ---------------------------------------------------------------------------


def test_read_config_propagates_selene_error_on_auth_failure():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    with _mock_client(handler) as client:
        with pytest.raises(SeleneError):
            SeleneConfigStore(client).read_config()
