"""Selene graph writers for discovered BACnet state.

Uses ``httpx.MockTransport`` to simulate Selene. Tests cover: create-path
on empty graph, update-path when the node exists, stale-property pruning,
edge creation from network → device / device → object, graceful Selene
errors.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from openfdd_stack.platform.bacnet.graph import (
    BACNET_DEVICE_LABEL,
    BACNET_NETWORK_LABEL,
    BACNET_OBJECT_LABEL,
    EXPOSES_OBJECT_EDGE,
    HAS_DEVICE_EDGE,
    PROTOCOL_BINDING_EDGE,
    bind_object_to_point,
    device_external_id,
    ensure_bacnet_network,
    network_external_id,
    object_external_id,
    upsert_bacnet_device,
    upsert_bacnet_object,
)
from openfdd_stack.platform.bacnet.transport import (
    DiscoveredDevice,
    DiscoveredObject,
)
from openfdd_stack.platform.selene import SeleneClient


def _mock_selene(handler) -> SeleneClient:
    return SeleneClient(
        "http://selene.local:8080",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        owns_client=True,
    )


# ---------------------------------------------------------------------------
# external_id conventions
# ---------------------------------------------------------------------------


def test_external_id_helpers_are_stable_and_parseable():
    """external_id strings are the debug key — formatting must not drift."""
    assert network_external_id("default") == "bacnet:net:default"
    assert device_external_id(1234567) == "bacnet:device:1234567"
    assert (
        object_external_id(
            device_instance=1234567, object_type="AnalogInput", object_instance=1
        )
        == "bacnet:obj:1234567:AnalogInput:1"
    )


# ---------------------------------------------------------------------------
# Network upsert
# ---------------------------------------------------------------------------


def test_ensure_bacnet_network_creates_node_when_absent():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            import json as _json

            captured["body"] = _json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 100,
                    "labels": [BACNET_NETWORK_LABEL],
                    "properties": captured["body"]["properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_selene(handler) as client:
        node = ensure_bacnet_network(
            client, name="default", broadcast_address="10.0.0.255"
        )
    assert node is not None
    assert node["id"] == 100
    assert captured["body"]["labels"] == [BACNET_NETWORK_LABEL]
    props = captured["body"]["properties"]
    assert props["name"] == "default"
    assert props["network_type"] == "bacnet"
    assert props["broadcast_address"] == "10.0.0.255"
    assert props["port"] == 47808
    assert props["transport"] == "bip"
    assert props["external_id"] == "bacnet:net:default"


# ---------------------------------------------------------------------------
# Device upsert
# ---------------------------------------------------------------------------


def test_upsert_bacnet_device_creates_node_and_links_network():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            captured["node_body"] = _json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 42,
                    "labels": [BACNET_DEVICE_LABEL],
                    "properties": captured["node_body"]["properties"],
                },
            )
        if (
            request.method == "GET"
            and request.url.path.startswith("/nodes/")
            and request.url.path.endswith("/edges")
        ):
            # Pre-check used by ``_ensure_edge`` — no pre-existing edges.
            return httpx.Response(
                200,
                json={"node_id": 100, "edges": [], "total": 0},
            )
        if request.method == "POST" and request.url.path == "/edges":
            captured["edge_body"] = _json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 7,
                    "source": captured["edge_body"]["source"],
                    "target": captured["edge_body"]["target"],
                    "label": captured["edge_body"]["label"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    device = DiscoveredDevice(
        device_instance=1234567,
        address="10.0.0.100:47808",
        vendor_id=260,
        device_name="AHU-1",
        vendor_name="ACME",
        model_name="BAC-2000",
    )
    with _mock_selene(handler) as client:
        node = upsert_bacnet_device(client, device, network_node_id=100)

    assert node is not None
    assert captured["node_body"]["labels"] == [BACNET_DEVICE_LABEL]
    props = captured["node_body"]["properties"]
    assert props["name"] == "AHU-1"
    assert props["instance"] == 1234567
    assert props["address"] == "10.0.0.100:47808"
    assert props["vendor_id"] == 260
    assert props["vendor_name"] == "ACME"
    assert props["model_name"] == "BAC-2000"
    assert props["external_id"] == "bacnet:device:1234567"

    assert captured["edge_body"]["source"] == 100
    assert captured["edge_body"]["target"] == 42
    assert captured["edge_body"]["label"] == HAS_DEVICE_EDGE


def test_upsert_bacnet_device_uses_placeholder_name_without_enrichment():
    """Pre-enrichment, the schema's required ``name`` still gets a value."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = _json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [BACNET_DEVICE_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    device = DiscoveredDevice(device_instance=99, address="10.0.0.99:47808")
    with _mock_selene(handler) as client:
        upsert_bacnet_device(client, device)
    assert captured["body"]["properties"]["name"] == "BACnet Device 99"


def test_upsert_bacnet_device_updates_existing_and_removes_stale_keys():
    """Rename: stale property (vendor_name) must be removed on update."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 11,
                            "labels": [BACNET_DEVICE_LABEL],
                            "properties": {
                                "external_id": "bacnet:device:77",
                                "name": "old-name",
                                "instance": 77,
                                "address": "10.0.0.77:47808",
                                "vendor_name": "old-vendor",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "PUT" and request.url.path == "/nodes/11":
            captured["body"] = _json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "id": 11,
                    "labels": [BACNET_DEVICE_LABEL],
                    "properties": captured["body"]["set_properties"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    device = DiscoveredDevice(
        device_instance=77, address="10.0.0.77:47808", device_name="new-name"
    )
    with _mock_selene(handler) as client:
        upsert_bacnet_device(client, device)

    assert captured["body"]["set_properties"]["name"] == "new-name"
    # vendor_name was on the stored node but not in the new property dict
    assert "vendor_name" in captured["body"]["remove_properties"]


# ---------------------------------------------------------------------------
# Object upsert
# ---------------------------------------------------------------------------


def test_upsert_bacnet_object_creates_node_and_links_device():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            captured["node_body"] = _json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 500,
                    "labels": [BACNET_OBJECT_LABEL],
                    "properties": captured["node_body"]["properties"],
                },
            )
        if (
            request.method == "GET"
            and request.url.path.startswith("/nodes/")
            and request.url.path.endswith("/edges")
        ):
            return httpx.Response(
                200,
                json={"node_id": 42, "edges": [], "total": 0},
            )
        if request.method == "POST" and request.url.path == "/edges":
            captured["edge_body"] = _json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 33,
                    "source": captured["edge_body"]["source"],
                    "target": captured["edge_body"]["target"],
                    "label": captured["edge_body"]["label"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    obj = DiscoveredObject(
        device_instance=1234567,
        object_type="AnalogInput",
        object_instance=1,
        concept_curie="mnemo:BacnetAnalogInput",
        object_name="SupplyAirTemp",
        units="degreesFahrenheit",
    )
    with _mock_selene(handler) as client:
        node = upsert_bacnet_object(client, obj, device_node_id=42)

    assert node is not None
    props = captured["node_body"]["properties"]
    assert props["concept_curie"] == "mnemo:BacnetAnalogInput"
    assert props["object_name"] == "SupplyAirTemp"
    assert props["object_type"] == "AnalogInput"
    assert props["instance"] == 1
    assert props["units"] == "degreesFahrenheit"
    assert props["external_id"] == "bacnet:obj:1234567:AnalogInput:1"

    assert captured["edge_body"]["source"] == 42
    assert captured["edge_body"]["target"] == 500
    assert captured["edge_body"]["label"] == EXPOSES_OBJECT_EDGE


def test_upsert_bacnet_object_uses_placeholder_object_name_without_enrichment():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if request.method == "GET":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        captured["body"] = _json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": 1,
                "labels": [BACNET_OBJECT_LABEL],
                "properties": captured["body"]["properties"],
            },
        )

    obj = DiscoveredObject(
        device_instance=5,
        object_type="BinaryInput",
        object_instance=12,
        concept_curie="mnemo:BacnetBinaryInput",
    )
    with _mock_selene(handler) as client:
        upsert_bacnet_object(client, obj)
    assert captured["body"]["properties"]["object_name"] == "BinaryInput 12"


# ---------------------------------------------------------------------------
# Graceful error path
# ---------------------------------------------------------------------------


def test_upsert_bacnet_device_skips_edge_when_already_present():
    """Re-running device upsert must not append duplicate hasDevice edges.

    Emulates a Selene that already has the device node *and* the
    ``hasDevice`` edge from a prior discovery pass. The writer calls
    ``get_node_edges`` (pre-check), sees the edge, and skips the
    ``POST /edges``.
    """
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        calls.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(
                200,
                json={
                    "nodes": [
                        {
                            "id": 11,
                            "labels": [BACNET_DEVICE_LABEL],
                            "properties": {
                                "external_id": "bacnet:device:5",
                                "name": "Prev",
                                "instance": 5,
                                "address": "10.0.0.5:47808",
                            },
                        }
                    ],
                    "total": 1,
                },
            )
        if request.method == "PUT" and request.url.path == "/nodes/11":
            body = _json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "id": 11,
                    "labels": [BACNET_DEVICE_LABEL],
                    "properties": body["set_properties"],
                },
            )
        if request.method == "GET" and request.url.path == "/nodes/100/edges":
            return httpx.Response(
                200,
                json={
                    "node_id": 100,
                    "edges": [
                        {
                            "id": 99,
                            "source": 100,
                            "target": 11,
                            "label": HAS_DEVICE_EDGE,
                        }
                    ],
                    "total": 1,
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    device = DiscoveredDevice(
        device_instance=5, address="10.0.0.5:47808", device_name="Prev"
    )
    with _mock_selene(handler) as client:
        upsert_bacnet_device(client, device, network_node_id=100)

    # No POST /edges issued — the pre-check found the edge and skipped.
    assert ("POST", "/edges") not in calls


def test_upsert_bacnet_device_returns_none_on_selene_error(caplog):
    """Selene errors must not escape the writer; best-effort posture."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    device = DiscoveredDevice(device_instance=99, address="10.0.0.99:47808")
    with _mock_selene(handler) as client:
        with caplog.at_level("WARNING"):
            result = upsert_bacnet_device(client, device)
    assert result is None
    assert any("upsert_bacnet_device" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# bind_object_to_point
# ---------------------------------------------------------------------------


def test_bind_object_to_point_creates_edge_with_property():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if (
            request.method == "GET"
            and request.url.path.startswith("/nodes/")
            and request.url.path.endswith("/edges")
        ):
            return httpx.Response(200, json={"node_id": 200, "edges": [], "total": 0})
        if request.method == "POST" and request.url.path == "/edges":
            captured["body"] = _json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": 77,
                    "source": captured["body"]["source"],
                    "target": captured["body"]["target"],
                    "label": captured["body"]["label"],
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_selene(handler) as client:
        bind_object_to_point(client, bacnet_object_node_id=200, point_node_id=500)

    assert captured["body"]["source"] == 200
    assert captured["body"]["target"] == 500
    assert captured["body"]["label"] == PROTOCOL_BINDING_EDGE
    assert captured["body"]["properties"]["property"] == "present_value"


def test_bind_object_to_point_is_idempotent_when_edge_exists():
    """Re-binding must not create a second protocolBinding edge."""
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if (
            request.method == "GET"
            and request.url.path.startswith("/nodes/")
            and request.url.path.endswith("/edges")
        ):
            return httpx.Response(
                200,
                json={
                    "node_id": 200,
                    "edges": [
                        {
                            "id": 77,
                            "source": 200,
                            "target": 500,
                            "label": PROTOCOL_BINDING_EDGE,
                        }
                    ],
                    "total": 1,
                },
            )
        raise AssertionError(f"unexpected {request.method} {request.url.path}")

    with _mock_selene(handler) as client:
        bind_object_to_point(client, bacnet_object_node_id=200, point_node_id=500)

    # No POST /edges issued — the pre-check matched.
    assert ("POST", "/edges") not in calls
