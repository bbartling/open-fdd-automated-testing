"""Unit tests for the SeleneDB HTTP client (httpx MockTransport).

These tests exercise the client surface without a live Selene; the smoke
harness at ``scripts/selene_smoke.py`` covers live-server integration.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from openfdd_stack.platform.selene import (
    SeleneAuthError,
    SeleneClient,
    SeleneConnectionError,
    SeleneError,
    SeleneNotFound,
    SeleneQueryError,
    SeleneValidationError,
)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _make(handler) -> SeleneClient:
    return SeleneClient(
        "http://selene.local:8080",
        identity="admin",
        secret="dev",
        client=_mock_client(handler),
    )


def test_health_parses_payload():
    def h(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        assert request.headers["Authorization"] == "Bearer admin:dev"
        return httpx.Response(200, json={"status": "ok", "uptime_secs": 42})

    with _make(h) as client:
        body = client.health()
    assert body == {"status": "ok", "uptime_secs": 42}


def test_no_auth_header_when_credentials_missing():
    def h(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"status": "ok"})

    client = SeleneClient("http://selene.local:8080", client=_mock_client(h))
    client.health()


def test_gql_returns_full_payload_on_success():
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["query"].startswith("MATCH")
        assert body["parameters"] == {"x": 1}
        return httpx.Response(
            200,
            json={
                "status": "00000",
                "message": "Success",
                "row_count": 1,
                "data": [{"n": 1}],
            },
        )

    with _make(h) as client:
        resp = client.gql("MATCH (n) RETURN n", {"x": 1})
    assert resp["data"] == [{"n": 1}]


def test_gql_no_data_status_returns_empty_rows():
    def h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "02000", "message": "no data", "row_count": 0, "data": []},
        )

    with _make(h) as client:
        rows = client.gql_rows("MATCH (n:absent) RETURN n")
    assert rows == []


def test_gql_error_status_raises():
    def h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "42000", "message": "syntax", "row_count": 0, "data": []},
        )

    with _make(h) as client:
        with pytest.raises(SeleneQueryError) as info:
            client.gql("BOGUS")
    assert info.value.status == "42000"


def test_ts_write_returns_written_count():
    captured: dict[str, Any] = {}

    def h(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        assert request.url.path == "/ts/write"
        return httpx.Response(200, json={"written": 2})

    with _make(h) as client:
        n = client.ts_write(
            [
                {"entity_id": 1, "property": "t", "timestamp_nanos": 10, "value": 1.0},
                {"entity_id": 1, "property": "t", "timestamp_nanos": 20, "value": 2.0},
            ]
        )
    assert n == 2
    assert len(captured["body"]["samples"]) == 2


def test_ts_range_list_response():
    def h(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ts/1/temperature"
        assert request.url.params["start"] == "10"
        assert request.url.params["end"] == "20"
        return httpx.Response(
            200,
            json=[
                {"timestamp_nanos": 15, "value": 21.0},
                {"timestamp_nanos": 16, "value": 22.0},
            ],
        )

    with _make(h) as client:
        rows = client.ts_range(1, "temperature", start_nanos=10, end_nanos=20)
    assert len(rows) == 2


def test_ts_latest_empty_returns_none():
    def h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "02000", "message": "no data", "row_count": 0, "data": []},
        )

    with _make(h) as client:
        result = client.ts_latest(1, "temperature")
    assert result is None


def test_create_node_roundtrip():
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["labels"] == ["sensor"]
        assert body["properties"] == {"unit": "F"}
        return httpx.Response(
            201, json={"id": 7, "labels": ["sensor"], "properties": {"unit": "F"}}
        )

    with _make(h) as client:
        node = client.create_node(["sensor"], {"unit": "F"})
    assert node["id"] == 7


def test_register_node_schema_shape():
    def h(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["label"] == "sensor"
        assert body["properties"][0]["name"] == "unit"
        return httpx.Response(201, json=body)

    with _make(h) as client:
        client.register_node_schema(
            "sensor",
            properties=[
                {
                    "name": "unit",
                    "value_type": "String",
                    "required": True,
                    "default": None,
                }
            ],
            description="test",
        )


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, SeleneAuthError),
        (403, SeleneAuthError),
        (404, SeleneNotFound),
        (400, SeleneValidationError),
        (422, SeleneValidationError),
        (500, SeleneError),
    ],
)
def test_status_codes_map_to_exceptions(status: int, exc: type[SeleneError]):
    def h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "boom"})

    with _make(h) as client:
        with pytest.raises(exc):
            client.health()


def test_network_error_becomes_connection_error():
    def h(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with _make(h) as client:
        with pytest.raises(SeleneConnectionError):
            client.health()


def test_timeout_becomes_connection_error():
    def h(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with _make(h) as client:
        with pytest.raises(SeleneConnectionError):
            client.health()


def test_non_json_health_response_raises_selene_error():
    """Proxy HTML or plain-text bodies must produce SeleneError, not bare ValueError."""

    def h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html><body>502 Bad Gateway</body></html>",
            headers={"content-type": "text/html"},
        )

    with _make(h) as client:
        with pytest.raises(SeleneError):
            client.health()


def test_gql_non_dict_body_raises_selene_error():
    """Selene returning a JSON array instead of the expected object must raise typed."""

    def h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "shape"])

    with _make(h) as client:
        with pytest.raises(SeleneError):
            client.gql("MATCH (n) RETURN n")


def test_ts_write_non_dict_body_raises_selene_error():
    def h(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    with _make(h) as client:
        with pytest.raises(SeleneError):
            client.ts_write(
                [{"entity_id": 1, "property": "t", "timestamp_nanos": 1, "value": 1.0}]
            )
