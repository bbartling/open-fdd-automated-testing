"""BacnetScraper + load_scrape_plan unit tests.

Uses a minimal ``_ScrapeTransport`` that implements the Transport ABC
(only ``read_present_values`` / lifecycle are exercised) paired with
an httpx.MockTransport Selene that tracks ts_write payloads and
answers the REST enumeration calls in ``load_scrape_plan``.
"""

from __future__ import annotations

import asyncio

import httpx

from openfdd_stack.platform.bacnet import (
    BacnetScraper,
    DiscoveredDevice,
    PropertyRead,
    PropertyReadResult,
    ScrapeBinding,
    ScrapePlan,
    Transport,
    load_scrape_plan,
)
from openfdd_stack.platform.bacnet.errors import BacnetTimeoutError
from openfdd_stack.platform.selene import SeleneClient

# ---------------------------------------------------------------------------
# Minimal Transport stub — only the methods the scraper uses
# ---------------------------------------------------------------------------


class _ScrapeTransport(Transport):
    """Only implements what BacnetScraper needs; discovery methods raise.

    Takes a ``results_by_device: {device_instance: list[PropertyReadResult]}``.
    ``read_present_values`` returns the pre-baked list (order matching
    the per-device bindings the test sets up). An injected
    ``raises_for_device`` makes a specific device's RPM call raise so
    we can cover the per-device-failure path.
    """

    def __init__(
        self,
        *,
        results_by_device: dict[int, list[PropertyReadResult]] | None = None,
        raises_for_device: dict[int, Exception] | None = None,
    ) -> None:
        self.results_by_device = results_by_device or {}
        self.raises_for_device = raises_for_device or {}
        self.calls: list[tuple[int, list[PropertyRead]]] = []

    async def connect(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def discover_devices(
        self, *, timeout_ms=3000, low_limit=None, high_limit=None
    ):
        raise NotImplementedError("_ScrapeTransport only supports read_present_values")

    async def read_device_properties(self, device):
        raise NotImplementedError

    async def read_object_list(self, device):
        raise NotImplementedError

    async def enrich_objects(self, device, objects):
        raise NotImplementedError

    async def read_present_values(self, device, reads):
        self.calls.append((device.device_instance, list(reads)))
        if device.device_instance in self.raises_for_device:
            raise self.raises_for_device[device.device_instance]
        return list(self.results_by_device.get(device.device_instance, []))

    async def write_property(
        self,
        device,
        object_type,
        object_instance,
        property_name,
        value,
        *,
        priority=None,
    ):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Selene mock — handles list_nodes / list_edges / ts_write
# ---------------------------------------------------------------------------


class _SeleneForScrape:
    """Fake Selene server for scrape tests.

    Seed ``nodes`` and ``edges`` in the constructor for
    ``load_scrape_plan`` tests; ``ts_write_calls`` captures payloads
    for ``BacnetScraper.scrape_once`` assertions.
    """

    def __init__(
        self,
        *,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
    ) -> None:
        self.nodes = nodes or []
        self.edges = edges or []
        self.ts_write_calls: list[list[dict]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        import json as _json

        path = request.url.path
        method = request.method

        if method == "GET" and path == "/nodes":
            label = request.url.params.get("label")
            matches = [n for n in self.nodes if label in n["labels"]]
            # Simple paging — all tests fit in one page so offset is ignored.
            return httpx.Response(200, json={"nodes": matches, "total": len(matches)})

        if method == "GET" and path == "/edges":
            label = request.url.params.get("label")
            matches = [e for e in self.edges if e.get("label") == label]
            return httpx.Response(200, json={"edges": matches, "total": len(matches)})

        if method == "POST" and path == "/ts/write":
            body = _json.loads(request.content)
            samples = body.get("samples") or []
            self.ts_write_calls.append(samples)
            return httpx.Response(200, json={"written": len(samples)})

        raise AssertionError(f"unexpected {method} {path}")


def _selene_factory(state: _SeleneForScrape):
    def factory() -> SeleneClient:
        return SeleneClient(
            "http://selene.local:8080",
            client=httpx.Client(transport=httpx.MockTransport(state.handle)),
            owns_client=True,
        )

    return factory


# ---------------------------------------------------------------------------
# load_scrape_plan
# ---------------------------------------------------------------------------


def test_load_scrape_plan_composes_bindings_by_device():
    """Four REST reads must compose into ``{device_instance: [bindings]}``."""
    # Two devices, three objects (two on device A, one on device B),
    # three bindings (one per object).
    nodes = [
        {
            "id": 100,
            "labels": ["bacnet_device"],
            "properties": {
                "external_id": "bacnet:device:1",
                "instance": 1,
                "address": "10.0.0.1:47808",
                "name": "Device-1",
            },
        },
        {
            "id": 101,
            "labels": ["bacnet_device"],
            "properties": {
                "external_id": "bacnet:device:2",
                "instance": 2,
                "address": "10.0.0.2:47808",
                "name": "Device-2",
            },
        },
        {
            "id": 200,
            "labels": ["bacnet_object"],
            "properties": {
                "external_id": "bacnet:obj:1:AnalogInput:1",
                "object_type": "AnalogInput",
                "instance": 1,
            },
        },
        {
            "id": 201,
            "labels": ["bacnet_object"],
            "properties": {
                "external_id": "bacnet:obj:1:BinaryOutput:3",
                "object_type": "BinaryOutput",
                "instance": 3,
            },
        },
        {
            "id": 202,
            "labels": ["bacnet_object"],
            "properties": {
                "external_id": "bacnet:obj:2:AnalogValue:5",
                "object_type": "AnalogValue",
                "instance": 5,
            },
        },
    ]
    edges = [
        # exposesObject: device -> object
        {"id": 1, "source": 100, "target": 200, "label": "exposesObject"},
        {"id": 2, "source": 100, "target": 201, "label": "exposesObject"},
        {"id": 3, "source": 101, "target": 202, "label": "exposesObject"},
        # protocolBinding: object -> point
        {
            "id": 4,
            "source": 200,
            "target": 500,
            "label": "protocolBinding",
            "properties": {"property": "present_value"},
        },
        {
            "id": 5,
            "source": 201,
            "target": 501,
            "label": "protocolBinding",
            "properties": {"property": "present_value"},
        },
        {
            "id": 6,
            "source": 202,
            "target": 502,
            "label": "protocolBinding",
            "properties": {"property": "present_value"},
        },
    ]
    state = _SeleneForScrape(nodes=nodes, edges=edges)
    with _selene_factory(state)() as client:
        plan = load_scrape_plan(client)

    assert set(plan.bindings_by_device.keys()) == {1, 2}
    assert len(plan.bindings_by_device[1]) == 2
    assert len(plan.bindings_by_device[2]) == 1
    assert plan.binding_count == 3

    # Device-1 bindings should carry the correct point ids.
    dev_1_points = {b.point_node_id for b in plan.bindings_by_device[1]}
    assert dev_1_points == {500, 501}


def test_load_scrape_plan_skips_orphan_objects():
    """A protocolBinding whose object has no device edge must drop out."""
    nodes = [
        {
            "id": 200,
            "labels": ["bacnet_object"],
            "properties": {
                "external_id": "bacnet:obj:orphan",
                "object_type": "AnalogInput",
                "instance": 1,
            },
        }
    ]
    edges = [
        {
            "id": 1,
            "source": 200,
            "target": 500,
            "label": "protocolBinding",
            "properties": {"property": "present_value"},
        }
    ]
    state = _SeleneForScrape(nodes=nodes, edges=edges)
    with _selene_factory(state)() as client:
        plan = load_scrape_plan(client)
    assert plan.bindings_by_device == {}


def test_load_scrape_plan_defaults_property_to_present_value_when_missing():
    """An edge without a ``property`` property still binds as present_value."""
    nodes = [
        {
            "id": 100,
            "labels": ["bacnet_device"],
            "properties": {"instance": 1, "address": "1.1.1.1:47808"},
        },
        {
            "id": 200,
            "labels": ["bacnet_object"],
            "properties": {"object_type": "AnalogInput", "instance": 1},
        },
    ]
    edges = [
        {"id": 1, "source": 100, "target": 200, "label": "exposesObject"},
        {"id": 2, "source": 200, "target": 500, "label": "protocolBinding"},
    ]
    state = _SeleneForScrape(nodes=nodes, edges=edges)
    with _selene_factory(state)() as client:
        plan = load_scrape_plan(client)
    assert plan.bindings_by_device[1][0].bacnet_property == "present_value"


# ---------------------------------------------------------------------------
# BacnetScraper.scrape_once
# ---------------------------------------------------------------------------


def _plan(
    *,
    device_instance: int = 1,
    device_address: str = "10.0.0.1:47808",
    bindings: list[ScrapeBinding] | None = None,
) -> ScrapePlan:
    return ScrapePlan(
        devices={
            device_instance: DiscoveredDevice(
                device_instance=device_instance, address=device_address
            )
        },
        bindings_by_device={device_instance: bindings or []},
    )


def test_scrape_once_writes_successful_samples_to_ts_write():
    bindings = [
        ScrapeBinding(
            device_instance=1,
            device_address="10.0.0.1:47808",
            object_type="AnalogInput",
            object_instance=1,
            point_node_id=500,
        ),
        ScrapeBinding(
            device_instance=1,
            device_address="10.0.0.1:47808",
            object_type="BinaryOutput",
            object_instance=3,
            point_node_id=501,
        ),
    ]
    tx = _ScrapeTransport(
        results_by_device={
            1: [
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
            ]
        }
    )
    state = _SeleneForScrape()
    scraper = BacnetScraper(tx, _selene_factory(state))
    result = asyncio.run(scraper.scrape_once(_plan(bindings=bindings)))

    assert result.samples_written == 2
    assert result.read_errors == 0
    assert result.device_failures == 0

    # One ts_write call with both samples (analog → float, binary → 1.0).
    assert len(state.ts_write_calls) == 1
    samples = state.ts_write_calls[0]
    by_entity = {s["entity_id"]: s for s in samples}
    assert by_entity[500]["value"] == 72.5
    assert by_entity[501]["value"] == 1.0
    assert all(s["property"] == "present_value" for s in samples)


def test_scrape_once_counts_read_errors_and_keeps_going():
    """Some objects on a device can error — others still land."""
    bindings = [
        ScrapeBinding(
            device_instance=1,
            device_address="10.0.0.1:47808",
            object_type="AnalogInput",
            object_instance=1,
            point_node_id=500,
        ),
        ScrapeBinding(
            device_instance=1,
            device_address="10.0.0.1:47808",
            object_type="AnalogInput",
            object_instance=2,
            point_node_id=501,
        ),
    ]
    tx = _ScrapeTransport(
        results_by_device={
            1: [
                PropertyReadResult(
                    object_type="AnalogInput",
                    object_instance=1,
                    property="present_value",
                    value=21.3,
                ),
                PropertyReadResult(
                    object_type="AnalogInput",
                    object_instance=2,
                    property="present_value",
                    error="unknown-property",
                ),
            ]
        }
    )
    state = _SeleneForScrape()
    scraper = BacnetScraper(tx, _selene_factory(state))
    result = asyncio.run(scraper.scrape_once(_plan(bindings=bindings)))

    assert result.samples_written == 1
    assert result.read_errors == 1
    assert result.device_failures == 0


def test_scrape_once_device_failure_does_not_block_other_devices():
    """If device-2's RPM raises, device-1's samples still write."""
    dev1_bindings = [
        ScrapeBinding(
            device_instance=1,
            device_address="10.0.0.1:47808",
            object_type="AnalogInput",
            object_instance=1,
            point_node_id=500,
        ),
    ]
    dev2_bindings = [
        ScrapeBinding(
            device_instance=2,
            device_address="10.0.0.2:47808",
            object_type="AnalogInput",
            object_instance=1,
            point_node_id=600,
        ),
    ]
    plan = ScrapePlan(
        devices={
            1: DiscoveredDevice(device_instance=1, address="10.0.0.1:47808"),
            2: DiscoveredDevice(device_instance=2, address="10.0.0.2:47808"),
        },
        bindings_by_device={1: dev1_bindings, 2: dev2_bindings},
    )
    tx = _ScrapeTransport(
        results_by_device={
            1: [
                PropertyReadResult(
                    object_type="AnalogInput",
                    object_instance=1,
                    property="present_value",
                    value=55.0,
                ),
            ]
        },
        raises_for_device={2: BacnetTimeoutError("device 2 offline")},
    )
    state = _SeleneForScrape()
    scraper = BacnetScraper(tx, _selene_factory(state))
    result = asyncio.run(scraper.scrape_once(plan))

    assert result.samples_written == 1
    assert result.device_failures == 1
    # Device 1's sample landed — only entity_id 500 in ts_write.
    assert {s["entity_id"] for s in state.ts_write_calls[0]} == {500}


def test_scrape_once_drops_non_numeric_present_values():
    """A character-string present-value is dropped (can't timeseries it)."""
    bindings = [
        ScrapeBinding(
            device_instance=1,
            device_address="1.1.1.1:47808",
            object_type="CharacterstringValue",
            object_instance=7,
            point_node_id=500,
        ),
    ]
    tx = _ScrapeTransport(
        results_by_device={
            1: [
                PropertyReadResult(
                    object_type="CharacterstringValue",
                    object_instance=7,
                    property="present_value",
                    value="some string",
                ),
            ]
        }
    )
    state = _SeleneForScrape()
    scraper = BacnetScraper(tx, _selene_factory(state))
    result = asyncio.run(scraper.scrape_once(_plan(bindings=bindings)))

    assert result.samples_written == 0
    # Non-numeric isn't an error either — it's a supported BACnet
    # value shape we choose not to persist.
    assert result.read_errors == 0


def test_scrape_once_missing_device_counts_as_device_failure():
    """Plan with bindings but no matching DiscoveredDevice must not KeyError.

    Regression guard for the plan-construction edge case where
    ``bindings_by_device`` has an entry that ``devices`` doesn't cover
    (e.g. stale ScrapePlan reused after a device deletion).
    """
    dev1_bindings = [
        ScrapeBinding(
            device_instance=1,
            device_address="10.0.0.1:47808",
            object_type="AnalogInput",
            object_instance=1,
            point_node_id=500,
        ),
    ]
    orphan_bindings = [
        ScrapeBinding(
            device_instance=99,
            device_address="10.0.0.99:47808",
            object_type="AnalogInput",
            object_instance=1,
            point_node_id=999,
        ),
    ]
    plan = ScrapePlan(
        devices={1: DiscoveredDevice(device_instance=1, address="10.0.0.1:47808")},
        bindings_by_device={1: dev1_bindings, 99: orphan_bindings},
    )
    tx = _ScrapeTransport(
        results_by_device={
            1: [
                PropertyReadResult(
                    object_type="AnalogInput",
                    object_instance=1,
                    property="present_value",
                    value=10.0,
                )
            ]
        }
    )
    state = _SeleneForScrape()
    scraper = BacnetScraper(tx, _selene_factory(state))
    result = asyncio.run(scraper.scrape_once(plan))

    # Device 1's sample still lands; device 99 counts as a failure.
    assert result.samples_written == 1
    assert result.device_failures == 1


def test_scrape_once_returns_empty_result_when_plan_empty():
    scraper = BacnetScraper(_ScrapeTransport(), _selene_factory(_SeleneForScrape()))
    plan = ScrapePlan(devices={}, bindings_by_device={})
    result = asyncio.run(scraper.scrape_once(plan))
    assert result.samples_written == 0
    assert result.read_errors == 0
    assert result.device_failures == 0
