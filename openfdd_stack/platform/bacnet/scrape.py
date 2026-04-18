"""BACnet scrape loop — reads present-values into SeleneDB timeseries.

The scraper is split into two halves so tests stay tight and the hot
path stays simple:

1. :func:`load_scrape_plan` — pulls the full ``(device, object, point)``
   binding set out of Selene via REST. Returns a
   :class:`ScrapePlan` grouped by device so a single
   ``ReadPropertyMultiple`` covers everything on a given device.
2. :class:`BacnetScraper` — takes a ``ScrapePlan`` and iterates it.
   For each device it calls ``transport.read_present_values`` and
   writes the successful values as timeseries samples via
   ``SeleneClient.ts_write``. Per-device failures are logged and do
   not poison the rest of the loop.

Timeseries anchoring: samples land with ``entity_id`` = the Selene
node id of the ``:point`` node. Property name on the timeseries
matches the ``protocolBinding.property`` (``"present_value"`` by
default) — if a site wires a different BACnet property through the
same binding later, it gets its own named timeseries on the point.

Design note: the scraper does *not* own a schedule. Callers drive it
— FastAPI endpoint for "scrape now", a future interval runner from
``drivers/`` for periodic scrape. Separation keeps the class unit-
testable with a single ``await scraper.scrape_once(plan)``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable

from openfdd_stack.platform.bacnet.graph import (
    BACNET_DEVICE_LABEL,
    BACNET_OBJECT_LABEL,
    EXPOSES_OBJECT_EDGE,
    PROTOCOL_BINDING_EDGE,
)
from openfdd_stack.platform.bacnet.transport import (
    DiscoveredDevice,
    PropertyRead,
    Transport,
)
from openfdd_stack.platform.selene.client import SeleneClient
from openfdd_stack.platform.selene.exceptions import SeleneError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plan types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScrapeBinding:
    """One ``(bacnet_object → point)`` mapping the scraper will read.

    Flattened from the ``:bacnet_device → :bacnet_object → :point``
    graph walk. ``point_node_id`` is Selene's internal numeric id (used
    as ``ts_write.entity_id``); ``bacnet_property`` is the property the
    scrape reads and also the timeseries property name on the point.
    """

    device_instance: int
    device_address: str
    object_type: str
    object_instance: int
    point_node_id: int
    bacnet_property: str = "present_value"


@dataclass(frozen=True)
class ScrapePlan:
    """What the scraper will do on one pass — bindings grouped by device.

    Grouping up front means ``BacnetScraper.scrape_once`` drives one
    ``ReadPropertyMultiple`` per device instead of re-grouping on every
    call. Pre-computing is cheap and makes call sites read naturally.
    """

    devices: dict[int, DiscoveredDevice]
    bindings_by_device: dict[int, list[ScrapeBinding]]

    @property
    def binding_count(self) -> int:
        return sum(len(b) for b in self.bindings_by_device.values())


@dataclass(frozen=True)
class ScrapeResult:
    """What one ``scrape_once`` pass did — lets callers surface progress.

    Reported counts:

    - ``samples_written`` — the number the server confirmed via
      ``ts_write``
    - ``read_errors`` — per-object errors (one device can have some
      points succeed and some fail)
    - ``device_failures`` — whole devices that raised on the RPM call
      (device offline, network partition, etc.)
    """

    samples_written: int
    read_errors: int
    device_failures: int


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------


def load_scrape_plan(client: SeleneClient) -> ScrapePlan:
    """Pull the full binding set out of Selene into an in-memory plan.

    Runs four REST reads:

    1. ``list_nodes(bacnet_device)`` — devices with addresses.
    2. ``list_nodes(bacnet_object)`` — objects with type/instance.
    3. ``list_edges(exposesObject)`` — links objects → their device.
    4. ``list_edges(protocolBinding)`` — links objects → points.

    Composes in Python. O(N) for N = devices + objects + bindings —
    acceptable for a scrape that already batches per-device and runs
    at minute-ish cadence. GQL-based traversal could cut the round
    trips but would make the unit tests harder to mock (Selene GQL
    semantics are a moving target in the current release).
    """
    devices_by_node_id: dict[int, DiscoveredDevice] = {}
    device_node_id_by_object: dict[int, int] = {}
    objects_by_node_id: dict[int, dict] = {}
    bindings: list[tuple[int, int, str]] = []  # (obj_node_id, point_node_id, property)

    # 1. devices
    for node in _all_nodes(client, BACNET_DEVICE_LABEL):
        props = node.get("properties") or {}
        instance = props.get("instance")
        address = props.get("address")
        if not isinstance(instance, int) or not isinstance(address, str):
            continue
        devices_by_node_id[node["id"]] = DiscoveredDevice(
            device_instance=instance,
            address=address,
            device_name=props.get("name"),
        )

    # 2. objects
    for node in _all_nodes(client, BACNET_OBJECT_LABEL):
        props = node.get("properties") or {}
        object_type = props.get("object_type")
        inst = props.get("instance")
        if not isinstance(object_type, str) or not isinstance(inst, int):
            continue
        objects_by_node_id[node["id"]] = {
            "object_type": object_type,
            "instance": inst,
        }

    # 3. device → object (exposesObject is device -> object)
    for edge in _all_edges(client, EXPOSES_OBJECT_EDGE):
        src = edge.get("source")
        tgt = edge.get("target")
        if isinstance(src, int) and isinstance(tgt, int):
            device_node_id_by_object[tgt] = src

    # 4. object → point (protocolBinding is object -> point)
    for edge in _all_edges(client, PROTOCOL_BINDING_EDGE):
        src = edge.get("source")
        tgt = edge.get("target")
        if not isinstance(src, int) or not isinstance(tgt, int):
            continue
        prop = (edge.get("properties") or {}).get("property", "present_value")
        bindings.append((src, tgt, str(prop)))

    bindings_by_device: dict[int, list[ScrapeBinding]] = {}
    devices_by_instance: dict[int, DiscoveredDevice] = {}
    for obj_id, point_id, prop in bindings:
        device_node_id = device_node_id_by_object.get(obj_id)
        if device_node_id is None:
            logger.debug(
                "bacnet scrape: object node=%d has no exposesObject edge; skipping",
                obj_id,
            )
            continue
        device = devices_by_node_id.get(device_node_id)
        obj = objects_by_node_id.get(obj_id)
        if device is None or obj is None:
            continue
        devices_by_instance[device.device_instance] = device
        bindings_by_device.setdefault(device.device_instance, []).append(
            ScrapeBinding(
                device_instance=device.device_instance,
                device_address=device.address,
                object_type=obj["object_type"],
                object_instance=obj["instance"],
                point_node_id=point_id,
                bacnet_property=prop,
            )
        )

    return ScrapePlan(
        devices=devices_by_instance,
        bindings_by_device=bindings_by_device,
    )


def _all_nodes(client: SeleneClient, label: str) -> list[dict]:
    """Paged ``list_nodes`` walk. Caps at 10k rows (same safety valve
    pattern as :mod:`openfdd_stack.platform.selene.graph_crud`)."""
    page_size = 100
    out: list[dict] = []
    offset = 0
    for _page in range(100):
        body = client.list_nodes(label=label, limit=page_size, offset=offset)
        nodes = body.get("nodes") or []
        out.extend(nodes)
        total = body.get("total")
        offset += len(nodes)
        if not nodes or len(nodes) < page_size:
            break
        if total is not None and offset >= total:
            break
    return out


def _all_edges(client: SeleneClient, label: str) -> list[dict]:
    """Paged ``list_edges`` walk. Same cap as :func:`_all_nodes`."""
    page_size = 100
    out: list[dict] = []
    offset = 0
    for _page in range(100):
        body = client.list_edges(label=label, limit=page_size, offset=offset)
        edges = body.get("edges") or []
        out.extend(edges)
        total = body.get("total")
        offset += len(edges)
        if not edges or len(edges) < page_size:
            break
        if total is not None and offset >= total:
            break
    return out


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class BacnetScraper:
    """Drive one scrape pass over a :class:`ScrapePlan`.

    Takes the transport (so a ``FakeTransport`` or ``BipTransport``
    both work) and a ``SeleneClient`` factory (so tests inject a
    MockTransport-backed client). Does *not* manage transport
    lifecycle — callers wrap ``async with transport:`` around the
    ``scrape_once`` call.
    """

    def __init__(
        self,
        transport: Transport,
        selene_client_factory: Callable[[], SeleneClient],
    ) -> None:
        self._transport = transport
        self._selene_factory = selene_client_factory

    async def scrape_once(self, plan: ScrapePlan) -> ScrapeResult:
        """Issue one RPM per device; write resulting samples to Selene.

        Devices are scraped in parallel via ``asyncio.gather`` so a
        slow device doesn't hold up the rest of the portfolio. A
        whole-device failure (transport raises) counts as
        ``device_failures`` — individual object errors count as
        ``read_errors`` but don't stop the device's other points.
        """
        if not plan.bindings_by_device:
            return ScrapeResult(0, 0, 0)

        # A binding entry with no matching device is a plan-construction
        # bug — treat it as a device failure and keep going so the rest
        # of the portfolio still scrapes. Indexing directly would KeyError
        # out of the gather() and abort the whole pass.
        device_failures = 0
        scrape_tasks = []
        for device_instance, bindings in plan.bindings_by_device.items():
            device = plan.devices.get(device_instance)
            if device is None:
                device_failures += 1
                logger.warning(
                    "bacnet scrape plan missing device for bindings "
                    "(device_instance=%d, bindings=%d)",
                    device_instance,
                    len(bindings),
                )
                continue
            scrape_tasks.append(self._scrape_one_device(device, bindings))

        per_device = await asyncio.gather(*scrape_tasks, return_exceptions=True)

        # Flatten samples + tally errors.
        all_samples: list[dict] = []
        total_read_errors = 0
        for entry in per_device:
            if isinstance(entry, BaseException):
                device_failures += 1
                logger.warning(
                    "bacnet scrape device failed",
                    exc_info=(type(entry), entry, entry.__traceback__),
                )
                continue
            samples, errors = entry
            all_samples.extend(samples)
            total_read_errors += errors

        written = 0
        if all_samples:
            written = await asyncio.to_thread(self._write_samples, all_samples)

        return ScrapeResult(
            samples_written=written,
            read_errors=total_read_errors,
            device_failures=device_failures,
        )

    async def _scrape_one_device(
        self, device: DiscoveredDevice, bindings: list[ScrapeBinding]
    ) -> tuple[list[dict], int]:
        """Read one device's point set, return ``(samples, read_errors)``."""
        reads = [
            PropertyRead(
                object_type=b.object_type,
                object_instance=b.object_instance,
                property=b.bacnet_property,
            )
            for b in bindings
        ]
        # Any exception propagates: ``gather(return_exceptions=True)`` in
        # ``scrape_once`` catches it and tallies it as a device failure.
        results = await self._transport.read_present_values(device, reads)

        now_nanos = time.time_ns()
        samples: list[dict] = []
        errors = 0
        # ``results`` is order-preserving per the Transport contract.
        for binding, result in zip(bindings, results):
            if result.error is not None or result.value is None:
                errors += 1
                logger.debug(
                    "bacnet scrape read error device=%d %s,%d property=%s: %s",
                    binding.device_instance,
                    binding.object_type,
                    binding.object_instance,
                    binding.bacnet_property,
                    result.error,
                )
                continue
            # Only numeric values land in timeseries; string / enum
            # values on analog present-values are very rare and would
            # confuse downstream consumers. Skip with a debug log.
            value = _coerce_numeric(result.value)
            if value is None:
                logger.debug(
                    "bacnet scrape non-numeric value dropped: device=%d "
                    "%s,%d property=%s value=%r",
                    binding.device_instance,
                    binding.object_type,
                    binding.object_instance,
                    binding.bacnet_property,
                    result.value,
                )
                continue
            samples.append(
                {
                    "entity_id": binding.point_node_id,
                    "property": binding.bacnet_property,
                    "timestamp_nanos": now_nanos,
                    "value": value,
                }
            )
        return samples, errors

    def _write_samples(self, samples: list[dict]) -> int:
        """Sync Selene write; runs on a worker thread via ``to_thread``."""
        try:
            with self._selene_factory() as client:
                return client.ts_write(samples)
        except SeleneError:
            logger.warning(
                "bacnet scrape ts_write failed (%d samples dropped)",
                len(samples),
                exc_info=True,
            )
            return 0


def _coerce_numeric(value: object) -> float | None:
    """Best-effort numeric coercion for present-value samples.

    rusty-bacnet hands us native types: bool / int / float / str /
    bytes. The first three become float samples; str and bytes are
    dropped (those are the multi-state / character-string edge cases
    a caller rarely timeseries-scrapes). This keeps the
    ``ts_write.value`` contract consistent with what downstream
    consumers (FDD loop, charts) expect.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None
