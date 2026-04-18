"""BacnetDriver orchestration — transport + graph wiring.

Uses a lightweight in-process ``FakeTransport`` that implements the
``Transport`` ABC without requiring rusty-bacnet. Pairs it with an
``httpx.MockTransport``-backed ``SeleneClient`` to prove the
async-to-sync handoff via ``asyncio.to_thread`` writes the right nodes
and edges into Selene.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from openfdd_stack.platform.bacnet import (
    BacnetDriver,
    DiscoveredDevice,
    DiscoveredObject,
    Transport,
)
from openfdd_stack.platform.selene import SeleneClient

# ---------------------------------------------------------------------------
# FakeTransport — drop-in replacement for BipTransport in tests
# ---------------------------------------------------------------------------


class FakeTransport(Transport):
    """In-memory Transport for orchestration tests.

    Stores fixed return values; records which methods were called with
    which inputs so tests can assert on the call sequence. Errors can
    be injected per-method for negative-path coverage.
    """

    def __init__(
        self,
        *,
        devices: list[DiscoveredDevice] | None = None,
        objects_by_device: dict[int, list[DiscoveredObject]] | None = None,
        enrich_device_raises: Exception | None = None,
        enrich_objects_raises: Exception | None = None,
    ) -> None:
        self.devices = devices or []
        self.objects_by_device = objects_by_device or {}
        self.enrich_device_raises = enrich_device_raises
        self.enrich_objects_raises = enrich_objects_raises
        self.calls: list[tuple[str, Any]] = []

    async def connect(self) -> None:
        self.calls.append(("connect", None))

    async def close(self) -> None:
        self.calls.append(("close", None))

    async def discover_devices(
        self,
        *,
        timeout_ms: int = 3000,
        low_limit: int | None = None,
        high_limit: int | None = None,
    ) -> list[DiscoveredDevice]:
        self.calls.append(("discover_devices", (timeout_ms, low_limit, high_limit)))
        return list(self.devices)

    async def read_device_properties(
        self, device: DiscoveredDevice
    ) -> DiscoveredDevice:
        self.calls.append(("read_device_properties", device.device_instance))
        if self.enrich_device_raises is not None:
            raise self.enrich_device_raises
        return DiscoveredDevice(
            device_instance=device.device_instance,
            address=device.address,
            mac_address=device.mac_address,
            max_apdu_length=device.max_apdu_length,
            segmentation_supported=device.segmentation_supported,
            vendor_id=device.vendor_id,
            device_name=f"Device-{device.device_instance}",
            vendor_name="FakeVendor",
            model_name="FakeModel",
            firmware_revision="1.0",
        )

    async def read_object_list(
        self, device: DiscoveredDevice
    ) -> list[DiscoveredObject]:
        self.calls.append(("read_object_list", device.device_instance))
        return list(self.objects_by_device.get(device.device_instance, []))

    async def enrich_objects(
        self, device: DiscoveredDevice, objects: list[DiscoveredObject]
    ) -> list[DiscoveredObject]:
        self.calls.append(("enrich_objects", device.device_instance))
        if self.enrich_objects_raises is not None:
            raise self.enrich_objects_raises
        return [
            DiscoveredObject(
                device_instance=o.device_instance,
                object_type=o.object_type,
                object_instance=o.object_instance,
                concept_curie=o.concept_curie,
                object_name=o.object_name or f"{o.object_type}-{o.object_instance}",
                description=o.description or "enriched",
                units=o.units,
            )
            for o in objects
        ]


# ---------------------------------------------------------------------------
# Selene mock — tracks which nodes + edges got created
# ---------------------------------------------------------------------------


class _SeleneState:
    """Minimal in-process Selene emulation for MockTransport handlers.

    Tracks created nodes and edges, answers the paged ``list_nodes``
    query used by the graph writer, and assigns sequential IDs.
    """

    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self._next_id = 1

    def handle(self, request: httpx.Request) -> httpx.Response:
        import json as _json

        path = request.url.path
        method = request.method

        if method == "GET" and path == "/nodes":
            label = request.url.params.get("label")
            matches = [n for n in self.nodes if label in n["labels"]]
            return httpx.Response(200, json={"nodes": matches, "total": len(matches)})

        if method == "POST" and path == "/nodes":
            body = _json.loads(request.content)
            node = {
                "id": self._next_id,
                "labels": body["labels"],
                "properties": body.get("properties") or {},
            }
            self._next_id += 1
            self.nodes.append(node)
            return httpx.Response(201, json=node)

        if method == "PUT" and path.startswith("/nodes/"):
            node_id = int(path.rsplit("/", 1)[1])
            body = _json.loads(request.content)
            for n in self.nodes:
                if n["id"] == node_id:
                    props = dict(n["properties"])
                    props.update(body.get("set_properties") or {})
                    for k in body.get("remove_properties") or []:
                        props.pop(k, None)
                    n["properties"] = props
                    return httpx.Response(200, json=n)
            return httpx.Response(404, json={"error": "not found"})

        if method == "POST" and path == "/edges":
            body = _json.loads(request.content)
            edge = {
                "id": self._next_id,
                "source": body["source"],
                "target": body["target"],
                "label": body["label"],
            }
            self._next_id += 1
            self.edges.append(edge)
            return httpx.Response(201, json=edge)

        if method == "GET" and path.startswith("/nodes/") and path.endswith("/edges"):
            # ``_ensure_edge`` pre-check — return whichever edges the
            # emulated Selene already has anchored on this node.
            node_id = int(path.split("/")[2])
            relevant = [
                e
                for e in self.edges
                if e["source"] == node_id or e["target"] == node_id
            ]
            return httpx.Response(
                200,
                json={"node_id": node_id, "edges": relevant, "total": len(relevant)},
            )

        raise AssertionError(f"unexpected {method} {path}")


def _selene_factory(state: _SeleneState):
    def factory() -> SeleneClient:
        return SeleneClient(
            "http://selene.local:8080",
            client=httpx.Client(transport=httpx.MockTransport(state.handle)),
            owns_client=True,
        )

    return factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_discover_devices_enriches_and_writes_network_and_devices():
    state = _SeleneState()
    devices = [
        DiscoveredDevice(device_instance=1, address="10.0.0.1:47808"),
        DiscoveredDevice(device_instance=2, address="10.0.0.2:47808"),
    ]
    tx = FakeTransport(devices=devices)
    driver = BacnetDriver(tx, _selene_factory(state), network_name="unit-test")

    result = asyncio.run(driver.discover_devices(timeout_ms=1000))

    assert len(result) == 2
    # Enriched devices carry names from FakeTransport.read_device_properties.
    assert {d.device_name for d in result} == {"Device-1", "Device-2"}

    # Graph state: one network + two devices + two hasDevice edges.
    net_nodes = [n for n in state.nodes if "bacnet_network" in n["labels"]]
    dev_nodes = [n for n in state.nodes if "bacnet_device" in n["labels"]]
    assert len(net_nodes) == 1
    assert net_nodes[0]["properties"]["name"] == "unit-test"
    assert len(dev_nodes) == 2
    assert {d["properties"]["instance"] for d in dev_nodes} == {1, 2}

    has_device_edges = [e for e in state.edges if e["label"] == "hasDevice"]
    assert len(has_device_edges) == 2
    assert all(e["source"] == net_nodes[0]["id"] for e in has_device_edges)


def test_discover_devices_enrich_false_skips_read_device_properties():
    """Quick scan path — no per-device enrichment."""
    state = _SeleneState()
    tx = FakeTransport(
        devices=[DiscoveredDevice(device_instance=7, address="10.0.0.7:47808")],
    )
    driver = BacnetDriver(tx, _selene_factory(state))

    asyncio.run(driver.discover_devices(enrich=False))

    assert not any(name == "read_device_properties" for name, _ in tx.calls)
    dev_node = next(n for n in state.nodes if "bacnet_device" in n["labels"])
    # Without enrichment the writer falls back to the placeholder name.
    assert dev_node["properties"]["name"] == "BACnet Device 7"


def test_discover_devices_tolerates_enrichment_failure_for_one_device():
    """One flaky enrich must not poison the whole discovery pass."""
    state = _SeleneState()

    class PartialFailTransport(FakeTransport):
        async def read_device_properties(self, device):
            if device.device_instance == 2:
                raise RuntimeError("simulated enrich failure")
            return await super().read_device_properties(device)

    tx = PartialFailTransport(
        devices=[
            DiscoveredDevice(device_instance=1, address="10.0.0.1:47808"),
            DiscoveredDevice(device_instance=2, address="10.0.0.2:47808"),
        ],
    )
    driver = BacnetDriver(tx, _selene_factory(state))

    result = asyncio.run(driver.discover_devices())

    # Both devices still land in the graph; device 2 uses the placeholder name.
    names = {
        n["properties"]["name"] for n in state.nodes if "bacnet_device" in n["labels"]
    }
    assert "Device-1" in names
    assert "BACnet Device 2" in names
    assert len(result) == 2


def test_discover_device_objects_writes_objects_and_edges():
    state = _SeleneState()
    device = DiscoveredDevice(
        device_instance=1234567,
        address="10.0.0.100:47808",
        device_name="AHU-1",
    )
    tx = FakeTransport(
        devices=[device],
        objects_by_device={
            1234567: [
                DiscoveredObject(
                    device_instance=1234567,
                    object_type="AnalogInput",
                    object_instance=1,
                    concept_curie="mnemo:BacnetAnalogInput",
                ),
                DiscoveredObject(
                    device_instance=1234567,
                    object_type="BinaryOutput",
                    object_instance=2,
                    concept_curie="mnemo:BacnetBinaryOutput",
                ),
            ]
        },
    )
    driver = BacnetDriver(tx, _selene_factory(state))

    objects = asyncio.run(driver.discover_device_objects(device))

    # Enrichment filled object_name + description.
    assert {o.object_name for o in objects} == {"AnalogInput-1", "BinaryOutput-2"}

    obj_nodes = [n for n in state.nodes if "bacnet_object" in n["labels"]]
    assert len(obj_nodes) == 2
    exposes_edges = [e for e in state.edges if e["label"] == "exposesObject"]
    assert len(exposes_edges) == 2


def test_discover_device_objects_keeps_partial_results_when_enrich_fails():
    state = _SeleneState()
    device = DiscoveredDevice(device_instance=1, address="10.0.0.1:47808")
    tx = FakeTransport(
        devices=[device],
        objects_by_device={
            1: [
                DiscoveredObject(
                    device_instance=1,
                    object_type="AnalogInput",
                    object_instance=5,
                    concept_curie="mnemo:BacnetAnalogInput",
                )
            ]
        },
        enrich_objects_raises=RuntimeError("simulated enrich failure"),
    )
    driver = BacnetDriver(tx, _selene_factory(state))
    result = asyncio.run(driver.discover_device_objects(device))

    assert len(result) == 1
    # Un-enriched object gets the placeholder object_name in the writer.
    obj_nodes = [n for n in state.nodes if "bacnet_object" in n["labels"]]
    assert obj_nodes[0]["properties"]["object_name"] == "AnalogInput 5"


def test_discover_end_to_end_returns_objects_per_device():
    """Full pass: one call that walks devices then objects."""
    state = _SeleneState()
    tx = FakeTransport(
        devices=[DiscoveredDevice(device_instance=10, address="10.0.0.10:47808")],
        objects_by_device={
            10: [
                DiscoveredObject(
                    device_instance=10,
                    object_type="AnalogInput",
                    object_instance=0,
                    concept_curie="mnemo:BacnetAnalogInput",
                )
            ]
        },
    )
    driver = BacnetDriver(tx, _selene_factory(state))
    out = asyncio.run(driver.discover())

    assert set(out.keys()) == {10}
    assert len(out[10]) == 1
    labels = [n["labels"][0] for n in state.nodes]
    assert "bacnet_network" in labels
    assert "bacnet_device" in labels
    assert "bacnet_object" in labels


def test_discover_devices_twice_does_not_duplicate_edges():
    """Re-running discovery must be idempotent — no duplicate hasDevice edges.

    Regression guard for the ``_ensure_edge`` pre-check. Without it,
    every discovery run would append another ``hasDevice`` edge for the
    same device and the graph would grow unboundedly on repeated scans.
    """
    state = _SeleneState()
    tx = FakeTransport(
        devices=[DiscoveredDevice(device_instance=42, address="10.0.0.42:47808")],
    )
    driver = BacnetDriver(tx, _selene_factory(state))

    asyncio.run(driver.discover_devices())
    asyncio.run(driver.discover_devices())
    asyncio.run(driver.discover_devices())

    has_device_edges = [e for e in state.edges if e["label"] == "hasDevice"]
    assert (
        len(has_device_edges) == 1
    ), f"expected exactly 1 hasDevice edge, got {len(has_device_edges)}"


def test_discover_device_objects_twice_does_not_duplicate_edges():
    """Same guard for ``exposesObject`` when re-scanning a device."""
    state = _SeleneState()
    device = DiscoveredDevice(
        device_instance=7,
        address="10.0.0.7:47808",
        device_name="Repeat-Device",
    )
    tx = FakeTransport(
        devices=[device],
        objects_by_device={
            7: [
                DiscoveredObject(
                    device_instance=7,
                    object_type="AnalogInput",
                    object_instance=1,
                    concept_curie="mnemo:BacnetAnalogInput",
                )
            ]
        },
    )
    driver = BacnetDriver(tx, _selene_factory(state))

    asyncio.run(driver.discover_device_objects(device))
    asyncio.run(driver.discover_device_objects(device))

    exposes_edges = [e for e in state.edges if e["label"] == "exposesObject"]
    assert len(exposes_edges) == 1


@pytest.mark.parametrize("name", ["default", "site-a", "branch-office"])
def test_network_name_propagates_to_network_node(name: str):
    state = _SeleneState()
    tx = FakeTransport(
        devices=[DiscoveredDevice(device_instance=1, address="ip:47808")]
    )
    driver = BacnetDriver(tx, _selene_factory(state), network_name=name)
    asyncio.run(driver.discover_devices(enrich=False))

    net_node = next(n for n in state.nodes if "bacnet_network" in n["labels"])
    assert net_node["properties"]["name"] == name
    assert net_node["properties"]["external_id"] == f"bacnet:net:{name}"
