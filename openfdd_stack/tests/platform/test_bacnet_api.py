"""BACnet API routes backed by the new in-process driver.

Strategy: patch ``api.bacnet._make_bip_transport`` with a
``_StubTransport`` implementing the ``Transport`` ABC. Selene writes
(used by the ``_to_graph`` endpoint) go through an
``httpx.MockTransport`` factory. No live rusty-bacnet required.

Covers the happy path for every route plus representative error paths
(device not found → 404, BacnetError → 502, validation → 400/422).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from openfdd_stack.platform.api import bacnet as bacnet_api
from openfdd_stack.platform.api.main import app
from openfdd_stack.platform.bacnet import (
    DiscoveredDevice,
    DiscoveredObject,
    PropertyReadResult,
    Transport,
)
from openfdd_stack.platform.bacnet.errors import BacnetTimeoutError
from openfdd_stack.platform.selene import SeleneClient

client = TestClient(app)


# ---------------------------------------------------------------------------
# Stub transport — only the methods each route calls are implemented
# ---------------------------------------------------------------------------


class _StubTransport(Transport):
    """Returns pre-baked responses; tracks calls for assertions.

    Each route pulls its own data out of instance fields so one stub
    type covers every test case (``discover_devices`` returns
    ``devices``, ``read_object_list`` returns ``objects``, etc.).
    """

    def __init__(
        self,
        *,
        devices: list[DiscoveredDevice] | None = None,
        objects: list[DiscoveredObject] | None = None,
        read_results: list[PropertyReadResult] | None = None,
        discover_raises: Exception | None = None,
        write_raises: Exception | None = None,
    ) -> None:
        self.devices = devices or []
        self.objects = objects or []
        self.read_results = read_results or []
        self.discover_raises = discover_raises
        self.write_raises = write_raises
        self.calls: list[tuple[str, Any]] = []

    async def connect(self) -> None:
        self.calls.append(("connect", None))

    async def close(self) -> None:
        self.calls.append(("close", None))

    async def discover_devices(
        self, *, timeout_ms=3000, low_limit=None, high_limit=None
    ) -> list[DiscoveredDevice]:
        self.calls.append(("discover_devices", (timeout_ms, low_limit, high_limit)))
        if self.discover_raises is not None:
            raise self.discover_raises
        return list(self.devices)

    async def read_device_properties(
        self, device: DiscoveredDevice
    ) -> DiscoveredDevice:
        self.calls.append(("read_device_properties", device.device_instance))
        return device

    async def read_object_list(
        self, device: DiscoveredDevice
    ) -> list[DiscoveredObject]:
        self.calls.append(("read_object_list", device.device_instance))
        return list(self.objects)

    async def enrich_objects(
        self, device: DiscoveredDevice, objects: list[DiscoveredObject]
    ) -> list[DiscoveredObject]:
        self.calls.append(("enrich_objects", device.device_instance))
        return list(self.objects)

    async def read_present_values(
        self, device: DiscoveredDevice, reads
    ) -> list[PropertyReadResult]:
        self.calls.append(("read_present_values", device.device_instance))
        return list(self.read_results)

    async def write_property(
        self,
        device: DiscoveredDevice,
        object_type: str,
        object_instance: int,
        property_name: str,
        value,
        *,
        priority: int | None = None,
    ) -> None:
        self.calls.append(
            (
                "write_property",
                (
                    device.device_instance,
                    object_type,
                    object_instance,
                    property_name,
                    value,
                    priority,
                ),
            )
        )
        if self.write_raises is not None:
            raise self.write_raises


def _patch_transport(monkeypatch: pytest.MonkeyPatch, tx: _StubTransport) -> None:
    """Replace ``_make_bip_transport`` so routes get our stub instead
    of building a real BipTransport (which would need rusty-bacnet +
    a UDP bind)."""
    monkeypatch.setattr(bacnet_api, "_make_bip_transport", lambda: tx)


def _patch_selene_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selene calls from the ``_to_graph`` endpoint hit a mock
    transport that accepts everything; we only care that the route
    returns 200, not the graph-write shape (graph tests live in
    ``test_bacnet_graph`` / ``test_bacnet_rusty_driver``)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/nodes":
            return httpx.Response(200, json={"nodes": [], "total": 0})
        if request.method == "POST" and request.url.path == "/nodes":
            return httpx.Response(201, json={"id": 1, "labels": [], "properties": {}})
        if (
            request.method == "GET"
            and request.url.path.startswith("/nodes/")
            and request.url.path.endswith("/edges")
        ):
            return httpx.Response(200, json={"node_id": 1, "edges": [], "total": 0})
        if request.method == "POST" and request.url.path == "/edges":
            return httpx.Response(
                201,
                json={"id": 2, "source": 1, "target": 1, "label": "x"},
            )
        return httpx.Response(404, json={"error": "not handled"})

    def factory() -> SeleneClient:
        return SeleneClient(
            "http://selene.local:8080",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            owns_client=True,
        )

    monkeypatch.setattr(
        "openfdd_stack.platform.api.bacnet.make_selene_client_from_settings",
        factory,
    )


# ---------------------------------------------------------------------------
# Gateway listing / health
# ---------------------------------------------------------------------------


def test_gateways_returns_single_embedded_entry():
    r = client.get("/bacnet/gateways")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["id"] == "default"
    assert body[0]["url"] == "embedded://rusty-bacnet"


def test_server_hello_returns_driver_config_without_network_traffic():
    """Shouldn't hit the transport — pure config echo."""
    # Intentionally do NOT patch the transport; if server_hello tried
    # to open a BipTransport the test would fail on rusty-bacnet import.
    r = client.post("/bacnet/server_hello", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["driver"] == "rusty-bacnet"
    assert body["transport"] == "bip"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_whois_range_returns_devices(monkeypatch: pytest.MonkeyPatch):
    _patch_selene_noop(monkeypatch)
    tx = _StubTransport(
        devices=[
            DiscoveredDevice(
                device_instance=100,
                address="10.0.0.100:47808",
                device_name="AHU-1",
                vendor_id=260,
            ),
            DiscoveredDevice(device_instance=200, address="10.0.0.200:47808"),
        ]
    )
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/whois_range",
        json={
            "request": {"start_instance": 1, "end_instance": 999},
            "timeout_ms": 1000,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["count"] == 2
    instances = {d["device_instance"] for d in body["devices"]}
    assert instances == {100, 200}


def test_whois_range_bacnet_error_becomes_502(monkeypatch: pytest.MonkeyPatch):
    _patch_selene_noop(monkeypatch)
    tx = _StubTransport(discover_raises=BacnetTimeoutError("socket timeout"))
    _patch_transport(monkeypatch, tx)

    r = client.post("/bacnet/whois_range", json={})
    assert r.status_code == 502
    body = r.json()
    # Stack error middleware wraps HTTPException detail; the timeout
    # message must be somewhere in the payload.
    assert "socket timeout" in str(body)


def test_point_discovery_returns_objects(monkeypatch: pytest.MonkeyPatch):
    _patch_selene_noop(monkeypatch)
    device = DiscoveredDevice(device_instance=100, address="10.0.0.100:47808")
    tx = _StubTransport(
        devices=[device],
        objects=[
            DiscoveredObject(
                device_instance=100,
                object_type="AnalogInput",
                object_instance=1,
                concept_curie="mnemo:BacnetAnalogInput",
                object_name="SupplyAirTemp",
            ),
        ],
    )
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/point_discovery",
        json={"instance": {"device_instance": 100}, "enrich": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["device_instance"] == 100
    assert body["count"] == 1
    obj = body["objects"][0]
    assert obj["object_identifier"] == "analog-input,1"
    assert obj["concept_curie"] == "mnemo:BacnetAnalogInput"
    assert obj["object_name"] == "SupplyAirTemp"


def test_point_discovery_404_when_device_not_responding(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_selene_noop(monkeypatch)
    tx = _StubTransport(devices=[])  # nothing comes back from directed Who-Is
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/point_discovery",
        json={"instance": {"device_instance": 9999}},
    )
    assert r.status_code == 404


def test_point_discovery_to_graph_persists_and_returns_objects(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_selene_noop(monkeypatch)
    device = DiscoveredDevice(
        device_instance=100,
        address="10.0.0.100:47808",
        device_name="AHU-1",
    )
    tx = _StubTransport(
        devices=[device],
        objects=[
            DiscoveredObject(
                device_instance=100,
                object_type="BinaryOutput",
                object_instance=5,
                concept_curie="mnemo:BacnetBinaryOutput",
            ),
        ],
    )
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/point_discovery_to_graph",
        json={"instance": {"device_instance": 100}, "enrich": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["device_address"] == "10.0.0.100:47808"
    assert body["objects"][0]["object_identifier"] == "binary-output,5"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def test_read_property_happy_path(monkeypatch: pytest.MonkeyPatch):
    _patch_selene_noop(monkeypatch)
    device = DiscoveredDevice(device_instance=100, address="10.0.0.100:47808")
    tx = _StubTransport(
        devices=[device],
        read_results=[
            PropertyReadResult(
                object_type="AnalogInput",
                object_instance=1,
                property="present_value",
                value=72.5,
            ),
        ],
    )
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/read_property",
        json={
            "device_instance": 100,
            "object_identifier": "analog-input,1",
            "property_identifier": "present_value",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["value"] == 72.5
    assert body["result"]["object_identifier"] == "analog-input,1"


def test_read_multiple_returns_one_entry_per_request(monkeypatch: pytest.MonkeyPatch):
    _patch_selene_noop(monkeypatch)
    device = DiscoveredDevice(device_instance=100, address="10.0.0.100:47808")
    tx = _StubTransport(
        devices=[device],
        read_results=[
            PropertyReadResult(
                object_type="AnalogInput",
                object_instance=1,
                property="present_value",
                value=72.5,
            ),
            PropertyReadResult(
                object_type="BinaryOutput",
                object_instance=3,
                property="present_value",
                value=True,
            ),
        ],
    )
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/read_multiple",
        json={
            "device_instance": 100,
            "requests": [
                {"object_identifier": "analog-input,1"},
                {"object_identifier": "binary-output,3"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["results"][0]["value"] == 72.5
    assert body["results"][1]["value"] is True


def test_read_property_invalid_object_identifier_returns_400():
    r = client.post(
        "/bacnet/read_property",
        json={
            "device_instance": 100,
            "object_identifier": "not-a-valid-string",  # no comma → 400
            "property_identifier": "present_value",
        },
    )
    assert r.status_code == 400


def test_write_property_happy_path(monkeypatch: pytest.MonkeyPatch):
    _patch_selene_noop(monkeypatch)
    device = DiscoveredDevice(device_instance=100, address="10.0.0.100:47808")
    tx = _StubTransport(devices=[device])
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/write_property",
        json={
            "device_instance": 100,
            "object_identifier": "analog-output,1",
            "property_identifier": "present_value",
            "value": 50.0,
            "priority": 8,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    # One write call was issued with the right shape.
    write_calls = [c for c in tx.calls if c[0] == "write_property"]
    assert len(write_calls) == 1
    _, args = write_calls[0]
    device_instance, object_type, object_instance, property_name, value, priority = args
    assert device_instance == 100
    assert object_type == "AnalogOutput"
    assert object_instance == 1
    assert property_name == "present_value"
    assert value == 50.0
    assert priority == 8


def test_write_property_requires_priority():
    """Schema validation — priority is mandatory per BACnet write rules."""
    r = client.post(
        "/bacnet/write_property",
        json={
            "device_instance": 100,
            "object_identifier": "analog-output,1",
            "value": 50.0,
            # priority deliberately missing
        },
    )
    assert r.status_code == 422  # FastAPI validation error


def test_write_property_bacnet_error_becomes_502(monkeypatch: pytest.MonkeyPatch):
    _patch_selene_noop(monkeypatch)
    device = DiscoveredDevice(device_instance=100, address="10.0.0.100:47808")
    tx = _StubTransport(
        devices=[device],
        write_raises=BacnetTimeoutError("timeout while writing"),
    )
    _patch_transport(monkeypatch, tx)

    r = client.post(
        "/bacnet/write_property",
        json={
            "device_instance": 100,
            "object_identifier": "analog-output,1",
            "value": 42.0,
            "priority": 8,
        },
    )
    assert r.status_code == 502
