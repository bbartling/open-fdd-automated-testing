"""Unit tests for CRUD sync helpers in openfdd_stack.platform.selene.graph_crud."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from openfdd_stack.platform.selene import (
    EXTERNAL_ID_PROP,
    SITE_LABEL,
    SeleneClient,
    delete_site,
    upsert_site,
)


def _mock_client(handler) -> SeleneClient:
    return SeleneClient(
        "http://selene.local:8080",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


# ---------------------------------------------------------------------------
# upsert_site
# ---------------------------------------------------------------------------


def test_upsert_site_creates_node_when_absent():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            assert request.url.params["label"] == SITE_LABEL
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 3,
                    "labels": [SITE_LABEL],
                    "properties": captured["body"]["properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        out = upsert_site(
            client,
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "HQ",
                "description": "Campus HQ",
                "metadata": {"climate_zone": "4A"},
            },
        )

    assert out["id"] == 3
    assert captured["body"]["labels"] == [SITE_LABEL]
    props = captured["body"]["properties"]
    assert props[EXTERNAL_ID_PROP] == "11111111-1111-1111-1111-111111111111"
    assert props["name"] == "HQ"
    assert props["description"] == "Campus HQ"
    # metadata is JSON-serialized for Selene's flat property model
    assert json.loads(props["metadata_json"]) == {"climate_zone": "4A"}


def test_upsert_site_updates_existing_node_matched_by_external_id():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 5,
                            "labels": [SITE_LABEL],
                            "properties": {
                                EXTERNAL_ID_PROP: "11111111-1111-1111-1111-111111111111",
                                "name": "Old name",
                                "description": "To be removed",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "PUT" and request.url.path == "/nodes/5":
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "id": 5,
                    "labels": [SITE_LABEL],
                    "properties": captured["body"]["set_properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        upsert_site(
            client,
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "HQ v2",
                # description omitted — tests stale-key removal
                "metadata": None,
            },
        )

    assert captured["body"]["set_properties"]["name"] == "HQ v2"
    # description should be removed (not present in new payload)
    assert "description" in captured["body"]["remove_properties"]


def test_upsert_site_ignores_other_sites_when_matching_external_id():
    """Multiple :site nodes may exist; we only touch the one with our external_id."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 1,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "other-site"},
                        },
                        {
                            "id": 2,
                            "labels": [SITE_LABEL],
                            "properties": {
                                EXTERNAL_ID_PROP: "target-site",
                                "name": "Target",
                            },
                        },
                    ],
                    "total": 2,
                },
            )
        assert request.url.path == "/nodes/2", request.url.path
        return httpx.Response(200, json={"id": 2, "labels": [SITE_LABEL]})

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "target-site", "name": "New Target"})


def test_upsert_site_warns_on_duplicate_external_id(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 10,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "dup"},
                        },
                        {
                            "id": 11,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "dup"},
                        },
                    ],
                    "total": 2,
                },
            )
        return httpx.Response(200, json={"id": 10, "labels": [SITE_LABEL]})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            upsert_site(client, {"id": "dup", "name": "x"})
    assert any("dup" in rec.message for rec in caplog.records)


def test_upsert_site_returns_none_and_logs_on_selene_error(caplog):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            result = upsert_site(client, {"id": "x", "name": "y"})
    assert result is None
    assert any("selene upsert_site failed" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# delete_site
# ---------------------------------------------------------------------------


def test_delete_site_removes_node_when_present():
    saw_delete = {"called": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 42,
                            "labels": [SITE_LABEL],
                            "properties": {EXTERNAL_ID_PROP: "gone"},
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "DELETE" and request.url.path == "/nodes/42":
            saw_delete["called"] = True
            return httpx.Response(204)
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_client(handler) as client:
        assert delete_site(client, "gone") is True
    assert saw_delete["called"]


def test_delete_site_returns_false_when_node_missing():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nodes": [], "total": 0})

    with _mock_client(handler) as client:
        assert delete_site(client, "not-there") is False


def test_delete_site_returns_false_and_logs_on_selene_error(caplog):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _mock_client(handler) as client:
        with caplog.at_level("WARNING"):
            assert delete_site(client, "x") is False
    assert any("selene delete_site failed" in rec.message for rec in caplog.records)


def test_upsert_site_finds_match_beyond_first_page():
    """Portfolios with >100 nodes of a label must still locate the match.

    Regression test for the original single-page query — the target node
    appears on page 2 and we expect a PUT to its id.
    """
    call_log: list[tuple[str, str]] = []
    # Build 100 filler nodes for page 1, then the target at the start of page 2.
    page1 = [
        {
            "id": i,
            "labels": [SITE_LABEL],
            "properties": {EXTERNAL_ID_PROP: f"other-{i}"},
        }
        for i in range(100)
    ]
    page2 = [
        {
            "id": 9001,
            "labels": [SITE_LABEL],
            "properties": {EXTERNAL_ID_PROP: "target", "name": "Target"},
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        call_log.append((request.method, str(request.url)))
        if request.method == "GET" and request.url.path == "/nodes":
            offset = int(request.url.params.get("offset", "0"))
            if offset == 0:
                return httpx.Response(200, json={"nodes": page1, "total": 101})
            return httpx.Response(200, json={"nodes": page2, "total": 101})
        assert request.url.path == "/nodes/9001", request.url.path
        return httpx.Response(200, json={"id": 9001, "labels": [SITE_LABEL]})

    with _mock_client(handler) as client:
        upsert_site(client, {"id": "target", "name": "New Name"})

    # At least two GET pages were walked.
    get_pages = [c for c in call_log if c[0] == "GET"]
    assert len(get_pages) >= 2
