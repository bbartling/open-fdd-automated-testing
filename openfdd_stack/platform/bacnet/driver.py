"""BacnetDriver — orchestrates discovery → graph writes.

Top-level API that API handlers, CLI harnesses, and the future scraper
all talk to. Three public async methods for Slice 2.5a:

- :meth:`BacnetDriver.discover_devices` — Who-Is + I-Am collection.
  Writes ``:bacnet_network`` (once) and one ``:bacnet_device`` per
  responder. Returns the full list of devices so the caller can present
  them to the user.
- :meth:`BacnetDriver.discover_device_objects` — one device's object-list
  enumeration + optional property enrichment. Writes one
  ``:bacnet_object`` node per object, each linked to the device via
  ``exposesObject``. Returns the object list for the UI.
- :meth:`BacnetDriver.discover` — convenience: devices, then objects for
  each device. Only used by CLI harnesses or a "scan everything" UI
  action; the normal UX is the two separate calls above.

Transport is injected so tests use :class:`~openfdd_stack.platform.bacnet.transport.Transport`
implementations without ``rusty_bacnet`` installed. Production callers
use :class:`~openfdd_stack.platform.bacnet.bip.BipTransport`.

Graph writes use the synchronous :class:`SeleneClient` off the async
event loop via :func:`asyncio.to_thread` so the driver never blocks the
loop on HTTP I/O.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from openfdd_stack.platform.bacnet.graph import (
    ensure_bacnet_network,
    upsert_bacnet_device,
    upsert_bacnet_object,
)
from openfdd_stack.platform.bacnet.transport import (
    DiscoveredDevice,
    DiscoveredObject,
    Transport,
)
from openfdd_stack.platform.selene.client import SeleneClient

logger = logging.getLogger(__name__)


class BacnetDriver:
    """High-level BACnet driver over a pluggable transport.

    Caller provides the transport (already configured) and a factory
    returning a fresh ``SeleneClient`` for each discovery pass — the
    factory pattern keeps the driver agnostic to how Selene credentials
    are wired (env, settings, test injection).

    Example::

        async with BipTransport(interface="0.0.0.0") as tx:
            driver = BacnetDriver(tx, selene_client_factory)
            devices = await driver.discover_devices(timeout_ms=3000)
            for d in devices:
                await driver.discover_device_objects(d, enrich=True)
    """

    def __init__(
        self,
        transport: Transport,
        selene_client_factory: Callable[[], SeleneClient],
        *,
        network_name: str = "bacnet-default",
    ) -> None:
        self._transport = transport
        self._selene_factory = selene_client_factory
        self._network_name = network_name
        self._network_node_id: int | None = None

    async def discover_devices(
        self,
        *,
        timeout_ms: int = 3000,
        low_limit: int | None = None,
        high_limit: int | None = None,
        enrich: bool = True,
    ) -> list[DiscoveredDevice]:
        """Broadcast Who-Is, persist responders, return them.

        When ``enrich`` is true (default) each device gets a follow-up
        ``ReadPropertyMultiple`` to populate name/vendor/model/firmware
        before the graph write. Callers doing a fast scan (UI "quick
        scan") can pass ``enrich=False`` and re-run
        :meth:`discover_devices` with ``enrich=True`` later to fill in
        the metadata (re-runs are idempotent — same devices upsert in
        place keyed on instance number).
        """
        devices = await self._transport.discover_devices(
            timeout_ms=timeout_ms, low_limit=low_limit, high_limit=high_limit
        )
        if not devices:
            return []

        if enrich:
            # Enrich in parallel but don't let one flaky device block the
            # whole discovery — a single-device timeout returns the bare
            # (un-enriched) DiscoveredDevice so the user still sees it.
            devices = await asyncio.gather(
                *(self._enrich_safely(d) for d in devices),
            )

        await asyncio.to_thread(self._write_devices, devices)
        return list(devices)

    async def discover_device_objects(
        self,
        device: DiscoveredDevice,
        *,
        enrich: bool = True,
    ) -> list[DiscoveredObject]:
        """Enumerate one device's object-list, persist each object.

        When ``enrich`` is true (default) issues one
        ``ReadPropertyMultiple`` over the discovered objects to fill in
        name / description / units. This is the slow path — callers
        doing a quick listing can pass ``enrich=False``.
        """
        objects = await self._transport.read_object_list(device)
        if enrich and objects:
            try:
                objects = await self._transport.enrich_objects(device, objects)
            except Exception:  # noqa: BLE001 — keep partial results
                logger.warning(
                    "bacnet enrich_objects failed for device %d; "
                    "persisting un-enriched object list",
                    device.device_instance,
                    exc_info=True,
                )

        await asyncio.to_thread(self._write_objects, device, objects)
        return list(objects)

    async def discover(
        self,
        *,
        timeout_ms: int = 3000,
        low_limit: int | None = None,
        high_limit: int | None = None,
    ) -> dict[int, list[DiscoveredObject]]:
        """Convenience: devices + per-device object enumeration.

        Returns ``{device_instance: [DiscoveredObject, ...]}``. Only used
        by batch tooling; the normal UX runs :meth:`discover_devices`
        and :meth:`discover_device_objects` separately so the user
        controls traffic.
        """
        devices = await self.discover_devices(
            timeout_ms=timeout_ms, low_limit=low_limit, high_limit=high_limit
        )
        results: dict[int, list[DiscoveredObject]] = {}
        for device in devices:
            try:
                results[device.device_instance] = await self.discover_device_objects(
                    device
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "bacnet discover_device_objects failed for device %d",
                    device.device_instance,
                    exc_info=True,
                )
                results[device.device_instance] = []
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _enrich_safely(self, device: DiscoveredDevice) -> DiscoveredDevice:
        """Per-device enrichment with a guard so one failure doesn't
        poison the whole discover pass."""
        try:
            return await self._transport.read_device_properties(device)
        except Exception:  # noqa: BLE001
            logger.warning(
                "bacnet read_device_properties failed for device %d; "
                "persisting bare identity from Who-Is response",
                device.device_instance,
                exc_info=True,
            )
            return device

    def _write_devices(self, devices: list[DiscoveredDevice]) -> None:
        """Synchronous graph write; runs on a worker thread via to_thread."""
        with self._selene_factory() as client:
            network = ensure_bacnet_network(client, name=self._network_name)
            network_id = (
                network["id"]
                if network and isinstance(network.get("id"), int)
                else None
            )
            self._network_node_id = network_id
            for device in devices:
                upsert_bacnet_device(client, device, network_node_id=network_id)

    def _write_objects(
        self, device: DiscoveredDevice, objects: list[DiscoveredObject]
    ) -> None:
        """Synchronous graph write for one device's objects."""
        with self._selene_factory() as client:
            # Resolve the device's node id by re-upserting — cheaper than
            # a separate find call and covers the case where discovery
            # ran in a different process that never set ``_network_node_id``.
            device_node = upsert_bacnet_device(
                client, device, network_node_id=self._network_node_id
            )
            device_node_id = (
                device_node["id"]
                if device_node and isinstance(device_node.get("id"), int)
                else None
            )
            for obj in objects:
                upsert_bacnet_object(client, obj, device_node_id=device_node_id)
