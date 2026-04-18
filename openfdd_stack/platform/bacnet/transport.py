"""Transport abstraction — the seam between the driver and the wire.

Two transports are planned:

- :class:`~openfdd_stack.platform.bacnet.bip.BipTransport` (this slice,
  2.5a): BACnet/IP via rusty-bacnet's UDP/47808 client. Binds locally;
  container runs ``network_mode: host``.
- ``ScTransport`` (slice 2.5d): BACnet/SC via rusty-bacnet's WebSocket
  client to an SC hub. No UDP binding; container stays on the Docker
  bridge.

Both transports expose the same :class:`Transport` interface so
``BacnetDriver``, discovery, and (future) scrape code stay transport
agnostic. When SC lands, only :mod:`bip` has a sibling; everything else
is untouched.

Types defined here are deliberately minimal (``DiscoveredDevice`` /
``DiscoveredObject`` as frozen dataclasses) so consumers don't import
``rusty_bacnet.*`` directly — the driver module is the only place that
touches the Rust library.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DiscoveredDevice:
    """One device returned from Who-Is / I-Am broadcast.

    Captures the BACnet-identity attributes the driver's graph writer
    needs to upsert a ``:bacnet_device`` node. Readable fields (vendor
    name, model, firmware) are filled by a follow-up per-device property
    read — not by the initial broadcast.
    """

    device_instance: int
    address: str
    """Source address in ``"ip:port"`` form, e.g. ``"192.168.1.100:47808"``."""

    mac_address: bytes | None = None
    max_apdu_length: int | None = None
    segmentation_supported: str | None = None
    vendor_id: int | None = None

    # Populated by follow-up reads in :meth:`Transport.read_device_properties`.
    device_name: str | None = None
    vendor_name: str | None = None
    model_name: str | None = None
    firmware_revision: str | None = None


@dataclass(frozen=True)
class PropertyRead:
    """One ``(object, property)`` read request for the scrape batch.

    The scraper builds one per ``:protocolBinding`` edge in Selene and
    hands the list to :meth:`Transport.read_present_values`. The
    ``property`` field is a BACnet property name string
    (``"present_value"`` by default); transports translate to the
    underlying integer identifier.
    """

    object_type: str
    object_instance: int
    property: str = "present_value"


@dataclass(frozen=True)
class PropertyReadResult:
    """Outcome of one :class:`PropertyRead` in a batch scrape.

    Either ``value`` is set and ``error`` is ``None`` (success), or
    ``error`` carries a short string describing what failed on this
    specific entry — the batch as a whole didn't fail, just this one.
    That shape matches rusty-bacnet's per-object RPM result, and lets
    the scrape loop persist what worked while logging what didn't.
    """

    object_type: str
    object_instance: int
    property: str
    # ``bytes`` is included because octet-string / bit-string properties
    # decode to raw bytes via rusty-bacnet; the scraper currently drops
    # them but the transport contract still has to surface them honestly.
    value: float | int | bool | str | bytes | None = None
    error: str | None = None


@dataclass(frozen=True)
class DiscoveredObject:
    """One object enumerated from a device's ``object-list`` property.

    ``object_type`` is the rusty-bacnet ``ObjectType`` repr (e.g.
    ``"AnalogInput"``); ``concept_curie`` is the Mnemosyne alignment
    (``"mnemo:BacnetAnalogInput"``) — callers write it onto the
    ``:bacnet_object`` node so graph queries can traverse Mnemosyne's
    equivalentTo edges into Brick / 223P.
    """

    device_instance: int
    object_type: str
    object_instance: int
    concept_curie: str

    object_name: str | None = None
    description: str | None = None
    units: str | None = None


class Transport(ABC):
    """Async BACnet transport — lifecycle + discovery + property reads.

    Lifecycle mirrors rusty-bacnet's ``async with BACnetClient(...)``:
    subclasses implement ``connect()`` / ``close()`` and the driver uses
    ``async with transport:`` context-manager syntax via the concrete
    methods below. Keeping our own protocol (instead of inheriting from
    ``BACnetClient`` directly) means tests can use a lightweight
    ``MockTransport`` without a Rust build in the test environment.
    """

    async def __aenter__(self) -> Transport:
        await self.connect()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()

    @abstractmethod
    async def connect(self) -> None:
        """Open sockets / establish SC session. Idempotent if possible."""

    @abstractmethod
    async def close(self) -> None:
        """Tear down sockets / SC session. Safe to call when not connected."""

    @abstractmethod
    async def discover_devices(
        self,
        *,
        timeout_ms: int = 3000,
        low_limit: int | None = None,
        high_limit: int | None = None,
    ) -> list[DiscoveredDevice]:
        """Broadcast Who-Is, collect I-Am responses, return what came back.

        ``low_limit`` / ``high_limit`` scope the Who-Is to a device-instance
        range (per ASHRAE 135 Clause 13.2) so large networks don't flood.
        """

    @abstractmethod
    async def read_device_properties(
        self, device: DiscoveredDevice
    ) -> DiscoveredDevice:
        """Fill in device-name / vendor-name / model / firmware via
        ``ReadPropertyMultiple`` against the Device object.

        Returns a new ``DiscoveredDevice`` (dataclasses are frozen) —
        callers replace the original when storing the result.
        """

    @abstractmethod
    async def read_object_list(
        self, device: DiscoveredDevice
    ) -> list[DiscoveredObject]:
        """Enumerate a device's object-list property and return one
        :class:`DiscoveredObject` per entry.

        Each entry carries ``object_type`` + ``object_instance``; the
        Mnemosyne ``concept_curie`` is mapped by
        :func:`object_types.curie_for_object_type`. Does *not* read
        per-object names / descriptions — that's a separate, optional
        enrichment pass so the caller chooses the latency / traffic
        tradeoff.
        """

    @abstractmethod
    async def enrich_objects(
        self,
        device: DiscoveredDevice,
        objects: list[DiscoveredObject],
    ) -> list[DiscoveredObject]:
        """Read object-name / description / units for each object via RPM.

        Batched per-device so one RPM serves many objects. Returns a new
        list (entries are frozen). Errors on individual objects are
        swallowed — the caller gets whatever came back; partial results
        are expected on mixed-capability devices.
        """

    @abstractmethod
    async def read_present_values(
        self,
        device: DiscoveredDevice,
        reads: list[PropertyRead],
    ) -> list[PropertyReadResult]:
        """Batch-read one property per object (scrape hot path).

        Issued as a single ``ReadPropertyMultiple`` so one device round
        trip covers its whole point set. Returns one
        :class:`PropertyReadResult` per input entry, preserving order —
        callers zip results back to their point bindings and know which
        samples to drop (``error is not None``) and which to write.
        """

    @abstractmethod
    async def write_property(
        self,
        device: DiscoveredDevice,
        object_type: str,
        object_instance: int,
        property_name: str,
        value: float | int | bool | str | None,
        *,
        priority: int | None = None,
    ) -> None:
        """Write a single property on a remote object.

        ``value`` is a Python scalar — transports translate to the
        matching BACnet PropertyValue variant (real / unsigned /
        boolean / …) using ``object_type`` + ``property_name`` to pick
        the right tag. Pass ``None`` to write NULL (relinquishes a
        commandable slot). ``priority`` is the BACnet priority slot
        (1-16); ``None`` writes without priority (some objects) or
        to the default slot.

        Raises :class:`BacnetError` subclasses on protocol failure —
        unlike the batch read path, a single-write failure is fatal
        for the call (the API handler surfaces it to the user).
        """
