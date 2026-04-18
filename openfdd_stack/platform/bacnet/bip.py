"""BACnet/IP transport, backed by rusty-bacnet.

Embeds ``rusty_bacnet.BACnetClient`` with ``transport="bip"``. Binds a
UDP socket on the host; the container running the driver therefore needs
``network_mode: host`` (Linux) or equivalent host networking. The BBMD
foreign-device registration path is wired through the client's config —
no extra glue here.

Translation layer notes:

- ``rusty_bacnet.DiscoveredDevice.object_identifier.instance`` →
  our ``DiscoveredDevice.device_instance``. rusty-bacnet keeps the
  ``ObjectIdentifier`` wrapper; we flatten to an int because consumers
  (API handlers, graph writer) shouldn't need to import ``rusty_bacnet``.
- ``Segmentation`` enum → the string repr. Schema pack stores it as a
  free-form string anyway.
- Per-device enrichment reads (device-name, vendor-name, model, firmware)
  go through ``read_property_multiple`` so one round-trip fills all four.

The rusty-bacnet import is *lazy*: the module imports fine on systems
without the Rust wheel installed (useful for CI that only runs the
MockTransport-backed tests). Attempting to instantiate ``BipTransport``
without rusty-bacnet present surfaces a typed
:class:`~openfdd_stack.platform.bacnet.errors.BacnetDriverError`.
"""

from __future__ import annotations

from typing import Any

from openfdd_stack.platform.bacnet.errors import (
    BacnetAbortedError,
    BacnetDecodeError,
    BacnetDriverError,
    BacnetProtocolError,
    BacnetRejectedError,
    BacnetTimeoutError,
)
from openfdd_stack.platform.bacnet.object_types import curie_for_object_type
from openfdd_stack.platform.bacnet.transport import (
    DiscoveredDevice,
    DiscoveredObject,
    Transport,
)

# BACnet property identifiers — kept as ints so we don't depend on
# rusty-bacnet's enum module-state at import time.
_PROP_OBJECT_LIST = 76
_PROP_OBJECT_NAME = 77
_PROP_DESCRIPTION = 28
_PROP_UNITS = 117
_PROP_VENDOR_NAME = 121
_PROP_MODEL_NAME = 70
_PROP_FIRMWARE_REVISION = 44

# Object-type 8 = Device. The Device object lives at instance == the
# device's own instance number.
_OBJECT_TYPE_DEVICE = 8


def _require_rusty_bacnet():
    """Import rusty-bacnet lazily; raise a typed driver error if missing.

    Keeps module import side-effect-free so tests that inject a
    ``MockTransport`` can run without the Rust wheel in the environment.
    """
    try:
        import rusty_bacnet  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — exercised in smoke / live runs only
        raise BacnetDriverError(
            "rusty-bacnet is not installed. Install with "
            "`pip install -e ~/Development/rusty-bacnet/crates/rusty-bacnet` "
            "for local dev, or `pip install rusty-bacnet` from PyPI."
        ) from exc
    return rusty_bacnet


def _translate_rusty_error(exc: Exception) -> Exception:
    """Map a ``rusty_bacnet.*`` exception to our typed hierarchy.

    Keeps caller code free from any ``rusty_bacnet`` imports. Unknown
    rusty-bacnet errors fall through as ``BacnetDriverError`` so nothing
    escapes the driver untyped.
    """
    rb = _require_rusty_bacnet()
    if isinstance(exc, rb.BacnetTimeoutError):
        return BacnetTimeoutError(str(exc))
    if isinstance(exc, rb.BacnetProtocolError):
        return BacnetProtocolError(
            str(exc),
            error_class=getattr(exc, "error_class", None),
            error_code=getattr(exc, "error_code", None),
        )
    if isinstance(exc, rb.BacnetRejectError):
        return BacnetRejectedError(str(exc), reason=getattr(exc, "reason", None))
    if isinstance(exc, rb.BacnetAbortError):
        return BacnetAbortedError(str(exc), reason=getattr(exc, "reason", None))
    if isinstance(exc, rb.BacnetError):
        return BacnetDriverError(str(exc))
    return exc  # non-BACnet exception — let it propagate untranslated


def _property_value_to_python(pv: Any) -> Any:
    """Unwrap a rusty-bacnet ``PropertyValue`` to a plain Python scalar.

    rusty-bacnet already exposes a ``.value`` attribute that returns a
    native type (int / float / str / bytes / bool) — this wrapper mainly
    exists to raise a typed :class:`BacnetDecodeError` when we get
    something we didn't expect (e.g. a constructed type we don't yet
    handle in the graph writer).
    """
    if pv is None:
        return None
    try:
        return pv.value
    except Exception as exc:  # noqa: BLE001
        raise BacnetDecodeError(
            f"could not decode PropertyValue (tag={getattr(pv, 'tag', '?')})",
            raw=pv,
        ) from exc


class BipTransport(Transport):
    """BACnet/IP transport using rusty-bacnet ``transport="bip"``.

    Config is passed straight through to ``BACnetClient``; see the
    rusty-bacnet Python API docs for the full set. Defaults match
    ASHRAE 135 BACnet/IP recommendations (port 0xBAC0 / 47808,
    broadcast 255.255.255.255, 6-second APDU timeout).

    Example::

        async with BipTransport(interface="0.0.0.0") as tx:
            devices = await tx.discover_devices(timeout_ms=3000)
    """

    def __init__(
        self,
        *,
        interface: str = "0.0.0.0",
        port: int = 47808,
        broadcast_address: str = "255.255.255.255",
        apdu_timeout_ms: int = 6000,
    ) -> None:
        self._interface = interface
        self._port = port
        self._broadcast_address = broadcast_address
        self._apdu_timeout_ms = apdu_timeout_ms
        self._client: Any | None = None

    async def connect(self) -> None:
        """Instantiate and enter the underlying ``BACnetClient``."""
        if self._client is not None:
            return
        rb = _require_rusty_bacnet()
        client = rb.BACnetClient(
            interface=self._interface,
            port=self._port,
            broadcast_address=self._broadcast_address,
            apdu_timeout_ms=self._apdu_timeout_ms,
            transport="bip",
        )
        # rusty-bacnet's client is itself an async context manager; we
        # enter it explicitly rather than nest ``async with`` so the
        # lifecycle matches ours (connect/close).
        try:
            await client.__aenter__()
        except Exception as exc:  # noqa: BLE001
            raise _translate_rusty_error(exc) from exc
        self._client = client

    async def close(self) -> None:
        """Exit the underlying client; idempotent."""
        client = self._client
        if client is None:
            return
        self._client = None
        try:
            await client.__aexit__(None, None, None)
        except Exception as exc:  # noqa: BLE001
            raise _translate_rusty_error(exc) from exc

    def _ensure_client(self) -> Any:
        if self._client is None:
            raise BacnetDriverError(
                "BipTransport used before connect() — wrap in `async with` or call connect() first."
            )
        return self._client

    async def discover_devices(
        self,
        *,
        timeout_ms: int = 3000,
        low_limit: int | None = None,
        high_limit: int | None = None,
    ) -> list[DiscoveredDevice]:
        """Broadcast Who-Is, return the I-Am responses collected over ``timeout_ms``."""
        client = self._ensure_client()
        try:
            rusty_devices = await client.discover(
                timeout_ms=timeout_ms,
                low_limit=low_limit,
                high_limit=high_limit,
            )
        except Exception as exc:  # noqa: BLE001
            raise _translate_rusty_error(exc) from exc
        return [_discovered_from_rusty(d) for d in rusty_devices]

    async def read_device_properties(
        self, device: DiscoveredDevice
    ) -> DiscoveredDevice:
        """Populate device-name / vendor-name / model / firmware via RPM.

        One ReadPropertyMultiple request against the device's Device
        object returns all four properties. Any property the device
        doesn't expose is silently dropped — partial enrichment is OK.
        """
        rb = _require_rusty_bacnet()
        client = self._ensure_client()
        oid = rb.ObjectIdentifier(rb.ObjectType.DEVICE, device.device_instance)
        specs = [
            (
                oid,
                [
                    (rb.PropertyIdentifier.from_raw(_PROP_OBJECT_NAME), None),
                    (rb.PropertyIdentifier.from_raw(_PROP_VENDOR_NAME), None),
                    (rb.PropertyIdentifier.from_raw(_PROP_MODEL_NAME), None),
                    (rb.PropertyIdentifier.from_raw(_PROP_FIRMWARE_REVISION), None),
                ],
            ),
        ]
        try:
            results = await client.read_property_multiple(device.address, specs)
        except Exception as exc:  # noqa: BLE001
            raise _translate_rusty_error(exc) from exc

        props = _extract_properties(results)
        return DiscoveredDevice(
            device_instance=device.device_instance,
            address=device.address,
            mac_address=device.mac_address,
            max_apdu_length=device.max_apdu_length,
            segmentation_supported=device.segmentation_supported,
            vendor_id=device.vendor_id,
            device_name=props.get(_PROP_OBJECT_NAME),
            vendor_name=props.get(_PROP_VENDOR_NAME),
            model_name=props.get(_PROP_MODEL_NAME),
            firmware_revision=props.get(_PROP_FIRMWARE_REVISION),
        )

    async def read_object_list(
        self, device: DiscoveredDevice
    ) -> list[DiscoveredObject]:
        """Read property 76 (object-list) on the Device object."""
        rb = _require_rusty_bacnet()
        client = self._ensure_client()
        oid = rb.ObjectIdentifier(rb.ObjectType.DEVICE, device.device_instance)
        pid = rb.PropertyIdentifier.from_raw(_PROP_OBJECT_LIST)
        try:
            value = await client.read_property(device.address, oid, pid)
        except Exception as exc:  # noqa: BLE001
            raise _translate_rusty_error(exc) from exc

        entries = _property_value_to_python(value)
        if not isinstance(entries, list):
            raise BacnetDecodeError(
                f"object-list response was not a list: {entries!r}", raw=entries
            )
        return [
            _object_from_oid_entry(entry, device_instance=device.device_instance)
            for entry in entries
        ]

    async def enrich_objects(
        self,
        device: DiscoveredDevice,
        objects: list[DiscoveredObject],
    ) -> list[DiscoveredObject]:
        """Bulk-read name / description / units for each object via RPM.

        Units are only meaningful on analog objects; the read is still
        issued on every object for simplicity — the device will return
        a per-property error for non-applicable entries and we drop
        them silently.
        """
        if not objects:
            return []
        rb = _require_rusty_bacnet()
        client = self._ensure_client()
        specs = []
        for obj in objects:
            try:
                rusty_type = _rusty_object_type(obj.object_type)
            except ValueError:
                continue
            oid = rb.ObjectIdentifier(rusty_type, obj.object_instance)
            specs.append(
                (
                    oid,
                    [
                        (rb.PropertyIdentifier.from_raw(_PROP_OBJECT_NAME), None),
                        (rb.PropertyIdentifier.from_raw(_PROP_DESCRIPTION), None),
                        (rb.PropertyIdentifier.from_raw(_PROP_UNITS), None),
                    ],
                )
            )
        if not specs:
            return list(objects)
        try:
            results = await client.read_property_multiple(device.address, specs)
        except Exception as exc:  # noqa: BLE001
            raise _translate_rusty_error(exc) from exc

        by_oid = _results_by_object_identifier(results)
        enriched: list[DiscoveredObject] = []
        for obj in objects:
            key = (obj.object_type, obj.object_instance)
            props = by_oid.get(key, {})
            enriched.append(
                DiscoveredObject(
                    device_instance=obj.device_instance,
                    object_type=obj.object_type,
                    object_instance=obj.object_instance,
                    concept_curie=obj.concept_curie,
                    object_name=props.get(_PROP_OBJECT_NAME) or obj.object_name,
                    description=props.get(_PROP_DESCRIPTION) or obj.description,
                    units=props.get(_PROP_UNITS) or obj.units,
                )
            )
        return enriched


# ---------------------------------------------------------------------------
# Translation helpers — all operate on rusty-bacnet values, kept module-local
# so the public surface stays clean.
# ---------------------------------------------------------------------------


def _discovered_from_rusty(rusty: Any) -> DiscoveredDevice:
    """Flatten a ``rusty_bacnet.DiscoveredDevice`` to our dataclass."""
    oid = rusty.object_identifier
    # rusty-bacnet exposes the source address as bytes on DiscoveredDevice;
    # the graph uses "ip:port" strings everywhere, so synthesise that here
    # using the default BACnet/IP port when the source doesn't carry one.
    address = _format_source_address(
        getattr(rusty, "source_address", None), default_port=47808
    )
    return DiscoveredDevice(
        device_instance=oid.instance,
        address=address,
        mac_address=rusty.mac_address,
        max_apdu_length=rusty.max_apdu_length,
        segmentation_supported=repr(rusty.segmentation_supported),
        vendor_id=rusty.vendor_id,
    )


def _format_source_address(src: bytes | None, *, default_port: int) -> str:
    """Render a BACnet source-address as ``"ip:port"``.

    BACnet/IP packs the sender's IP+port into 6 bytes (4 IP + 2 port).
    When the source address is missing (sometimes the case for routed
    traffic), we fall back to ``"unknown"`` — the caller can enrich
    later via ``ReadProperty(device.address_binding)``.
    """
    if not src or len(src) < 6:
        return "unknown"
    ip = ".".join(str(b) for b in src[:4])
    port = (src[4] << 8) | src[5]
    return f"{ip}:{port or default_port}"


def _extract_properties(rpm_result: Any) -> dict[int, Any]:
    """Pull a ``{property_id_int: python_value}`` dict out of an RPM result.

    rusty-bacnet's RPM return shape is a nested structure keyed by
    ObjectIdentifier → list of (property_id, value, error). We collapse
    the first (and, for our use, only) object's entries into a flat dict.
    Error entries are dropped silently — the caller treats absent keys
    as "device doesn't expose this property."
    """
    if rpm_result is None:
        return {}
    out: dict[int, Any] = {}
    entries = _flatten_rpm(rpm_result)
    for entry in entries:
        pid = entry.get("property_id")
        if not isinstance(pid, int):
            pid_obj = entry.get("property")
            pid = int(pid_obj.to_raw()) if pid_obj is not None else None
        value = entry.get("value")
        error = entry.get("error")
        if pid is None or error is not None or value is None:
            continue
        try:
            out[pid] = _property_value_to_python(value)
        except BacnetDecodeError:
            # Skip un-decodable entries — caller gets a partial result.
            continue
    return out


def _flatten_rpm(rpm_result: Any) -> list[dict[str, Any]]:
    """Flatten rusty-bacnet's nested RPM dict to a single list of entries.

    The rusty-bacnet shape is not rigidly specified (``Any`` in the
    stub); we defensively accept several plausible shapes so a minor
    library update doesn't break discovery. Each returned dict should
    have at least ``property_id`` / ``value`` / ``error`` keys.
    """
    if isinstance(rpm_result, list):
        # Top-level list of per-object results.
        entries: list[dict[str, Any]] = []
        for obj_result in rpm_result:
            results = (
                obj_result.get("results") if isinstance(obj_result, dict) else None
            )
            if isinstance(results, list):
                entries.extend(r for r in results if isinstance(r, dict))
        return entries
    if isinstance(rpm_result, dict):
        results = rpm_result.get("results")
        if isinstance(results, list):
            return [r for r in results if isinstance(r, dict)]
    return []


def _results_by_object_identifier(
    rpm_result: Any,
) -> dict[tuple[str, int], dict[int, Any]]:
    """Group a multi-object RPM result by ``(object_type_repr, instance)``.

    Used by :meth:`BipTransport.enrich_objects` where one RPM covers
    many objects and the caller needs to reassociate properties back
    to the right object.
    """
    if not isinstance(rpm_result, list):
        return {}
    out: dict[tuple[str, int], dict[int, Any]] = {}
    for obj_result in rpm_result:
        if not isinstance(obj_result, dict):
            continue
        oid = obj_result.get("object_id") or obj_result.get("object_identifier")
        if oid is None:
            continue
        try:
            otype = repr(oid.object_type)
            inst = int(oid.instance)
        except AttributeError:
            continue
        props: dict[int, Any] = {}
        for r in obj_result.get("results") or []:
            if not isinstance(r, dict):
                continue
            pid = r.get("property_id")
            if not isinstance(pid, int):
                pid_obj = r.get("property")
                pid = int(pid_obj.to_raw()) if pid_obj is not None else None
            value = r.get("value")
            error = r.get("error")
            if pid is None or error is not None or value is None:
                continue
            try:
                props[pid] = _property_value_to_python(value)
            except BacnetDecodeError:
                continue
        out[(otype, inst)] = props
    return out


def _object_from_oid_entry(entry: Any, *, device_instance: int) -> DiscoveredObject:
    """Convert one object-list entry (ObjectIdentifier) into DiscoveredObject.

    rusty-bacnet returns the object-list as a list of ``ObjectIdentifier``
    values — no per-object names yet, that's what :meth:`enrich_objects`
    is for.
    """
    otype = entry.object_type
    raw_type = otype.to_raw()
    return DiscoveredObject(
        device_instance=device_instance,
        object_type=repr(otype),
        object_instance=int(entry.instance),
        concept_curie=curie_for_object_type(raw_type),
    )


# Cached ``{repr: ObjectType}`` so ``enrich_objects`` doesn't re-scan
# ``dir(ObjectType)`` once per object on large device scans. Populated lazily
# after rusty-bacnet is confirmed importable so module import stays side-effect
# free.
_OBJECT_TYPE_BY_REPR: dict[str, Any] | None = None


def _rusty_object_type_map() -> dict[str, Any]:
    """Return the cached ``{repr(ObjectType): ObjectType}`` table, building
    it on first call."""
    global _OBJECT_TYPE_BY_REPR
    if _OBJECT_TYPE_BY_REPR is not None:
        return _OBJECT_TYPE_BY_REPR
    rb = _require_rusty_bacnet()
    mapping: dict[str, Any] = {}
    for attr in dir(rb.ObjectType):
        if attr.startswith("_"):
            continue
        candidate = getattr(rb.ObjectType, attr, None)
        if candidate is None:
            continue
        try:
            mapping[repr(candidate)] = candidate
        except Exception:  # noqa: BLE001 — skip attrs that aren't ObjectType instances
            continue
    _OBJECT_TYPE_BY_REPR = mapping
    return mapping


def _rusty_object_type(repr_str: str) -> Any:
    """Look up a ``rusty_bacnet.ObjectType`` by its ``__repr__`` string.

    Used by :meth:`BipTransport.enrich_objects` — we store the repr
    (``"AnalogInput"``) on :class:`DiscoveredObject`, and need to reconstruct
    the enum value to build the RPM request. O(1) lookup via the cached
    table built by :func:`_rusty_object_type_map`.
    """
    try:
        return _rusty_object_type_map()[repr_str]
    except KeyError:
        raise ValueError(f"unknown BACnet ObjectType repr: {repr_str!r}") from None
