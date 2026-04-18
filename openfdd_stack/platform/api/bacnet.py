"""BACnet API routes — backed by the in-process rusty-bacnet driver.

Greenfield rewrite for Phase 2.5c. The old JSON-RPC proxy (one route
per diy-bacnet-server method) is gone; these routes talk directly to
:class:`~openfdd_stack.platform.bacnet.BacnetDriver` /
:class:`~openfdd_stack.platform.bacnet.BipTransport`.

Endpoints (route paths preserved for frontend compatibility):

- ``GET  /bacnet/gateways`` — one entry describing the embedded driver
- ``POST /bacnet/server_hello`` — lightweight "driver configured" probe
- ``POST /bacnet/whois_range`` — Who-Is broadcast → devices in Selene
- ``POST /bacnet/point_discovery`` — enumerate one device's object-list
- ``POST /bacnet/point_discovery_to_graph`` — same, but also writes the
  objects as ``:bacnet_object`` nodes in Selene
- ``POST /bacnet/read_property`` — single property read
- ``POST /bacnet/read_multiple`` — batch read via RPM
- ``POST /bacnet/write_property`` — single property write with priority

Dropped from the prior surface (reinstate later if needed):

- ``/modbus_read_registers``: Modbus proxy; Modbus will get its own
  driver rather than riding in the BACnet routes.
- ``/supervisory_logic_checks``: diy-bacnet-specific RPC with no
  ASHRAE 135 mapping; not worth porting.
- ``/read_point_priority_array``: doable via
  ``read_property(property=priority-array)`` — fold into
  ``/read_property`` with a property_identifier parameter.
- ``/write_point``: CRUD-audited write wrapper; separate slice.

Transport lifecycle: each request opens and closes a fresh
``BipTransport`` (one BACnet/IP socket per request). The UDP socket
setup is fast on localhost and matches the original JSON-RPC
per-request shape. A long-lived connection pool can land in a later
optimization pass if latency shows up.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field, model_validator

from openfdd_stack.platform.bacnet import (
    BacnetDriver,
    BacnetError,
    BipTransport,
    DiscoveredDevice,
    PropertyRead,
    PropertyReadResult,
)
from openfdd_stack.platform.bacnet.errors import (
    BacnetDriverError,
    BacnetProtocolError,
)
from openfdd_stack.platform.config import get_platform_settings
from openfdd_stack.platform.selene import make_selene_client_from_settings

router = APIRouter(prefix="/bacnet", tags=["BACnet"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Driver factory — one place to construct the transport from settings.
# ---------------------------------------------------------------------------


def _make_bip_transport() -> BipTransport:
    """Build a ``BipTransport`` from platform settings.

    Defaults are ``0.0.0.0:47808`` (BACnet/IP standard), 255.255.255.255
    broadcast, 6-second APDU timeout. Override via ``OFDD_BACNET_*``
    env vars when the 2.5d config cleanup lands.
    """
    s = get_platform_settings()
    return BipTransport(
        interface=getattr(s, "bacnet_interface", None) or "0.0.0.0",
        port=int(getattr(s, "bacnet_port", None) or 47808),
        broadcast_address=getattr(s, "bacnet_broadcast_address", None)
        or "255.255.255.255",
        apdu_timeout_ms=int(getattr(s, "bacnet_apdu_timeout_ms", None) or 6000),
    )


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


def _error_body(exc: BacnetError, *, code: str = "BACNET_ERROR") -> dict[str, Any]:
    """Build the stack's uniform ``{code, message, details}`` error envelope.

    ``main._error_detail_from_http_exc`` reads these three keys and
    drops anything else, so BACnet-specific structured context
    (error_class / error_code / reject reason / abort reason) has to
    live under ``details`` to reach the client.
    """
    details: dict[str, Any] = {"error_type": type(exc).__name__}
    if isinstance(exc, BacnetProtocolError):
        if exc.error_class is not None:
            details["error_class"] = exc.error_class
        if exc.error_code is not None:
            details["error_code"] = exc.error_code
    reason = getattr(exc, "reason", None)
    if reason is not None:
        details["reason"] = reason
    return {
        "code": code,
        "message": str(exc),
        "details": details,
    }


# ---------------------------------------------------------------------------
# Object identifier parsing — compatibility with the legacy string form.
# ---------------------------------------------------------------------------


# Canonical long-form kebab identifiers accepted on input *and* emitted on
# responses. ``repr(ObjectType.X)`` in rusty-bacnet drops word-internal
# caps (``CHARACTERSTRING_VALUE`` → ``CharacterstringValue``), so the
# CamelCase values here match what the transport produces.
_CANONICAL_KEBAB_TO_OBJECT_TYPE: dict[str, str] = {
    "analog-input": "AnalogInput",
    "analog-output": "AnalogOutput",
    "analog-value": "AnalogValue",
    "binary-input": "BinaryInput",
    "binary-output": "BinaryOutput",
    "binary-value": "BinaryValue",
    "multi-state-input": "MultiStateInput",
    "multi-state-output": "MultiStateOutput",
    "multi-state-value": "MultiStateValue",
    "device": "Device",
    "file": "File",
    "schedule": "Schedule",
    "calendar": "Calendar",
    "trend-log": "TrendLog",
    "trend-log-multiple": "TrendLogMultiple",
    "notification-class": "NotificationClass",
    "structured-view": "StructuredView",
    "characterstring-value": "CharacterstringValue",
    "integer-value": "IntegerValue",
    "positive-integer-value": "PositiveIntegerValue",
    "large-analog-value": "LargeAnalogValue",
    "accumulator": "Accumulator",
    "pulse-converter": "PulseConverter",
    "network-port": "NetworkPort",
    "loop": "Loop",
    "program": "Program",
}

# Short-form aliases that the stack / tests / scripts have used
# historically (``ai,1`` / ``bo,3``). Accepted on input only — responses
# always emit the long form so the wire shape stays predictable.
_KEBAB_SHORT_ALIASES: dict[str, str] = {
    "ai": "AnalogInput",
    "ao": "AnalogOutput",
    "av": "AnalogValue",
    "bi": "BinaryInput",
    "bo": "BinaryOutput",
    "bv": "BinaryValue",
    "mi": "MultiStateInput",
    "mo": "MultiStateOutput",
    "mv": "MultiStateValue",
}

_KEBAB_TO_OBJECT_TYPE: dict[str, str] = {
    **_CANONICAL_KEBAB_TO_OBJECT_TYPE,
    **_KEBAB_SHORT_ALIASES,
}

# Inverse built from the canonical map only, so ``AnalogInput`` always
# renders as ``analog-input`` (never ``ai``) on response bodies.
_OBJECT_TYPE_TO_KEBAB: dict[str, str] = {
    v: k for k, v in _CANONICAL_KEBAB_TO_OBJECT_TYPE.items()
}


def _parse_object_identifier(oid: str) -> tuple[str, int]:
    """Parse ``"analog-input,1"`` (or ``"ai,1"``) → ``("AnalogInput", 1)``.

    Raises ``HTTPException(400)`` with structured detail on malformed
    input so the frontend sees a usable error instead of a 500
    backtrace.
    """
    if "," not in oid:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BACNET_INVALID",
                "message": f"invalid object_identifier: {oid!r}",
                "details": {"object_identifier": oid},
            },
        )
    kebab_type, _, instance_str = oid.partition(",")
    object_type = _KEBAB_TO_OBJECT_TYPE.get(kebab_type.strip().lower())
    if object_type is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BACNET_INVALID",
                "message": f"unknown object type: {kebab_type!r}",
                "details": {"object_type": kebab_type},
            },
        )
    try:
        instance = int(instance_str.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BACNET_INVALID",
                "message": f"invalid object instance: {instance_str!r}",
                "details": {"object_instance": instance_str},
            },
        ) from exc
    return object_type, instance


def _format_object_identifier(object_type: str, instance: int) -> str:
    """Inverse of :func:`_parse_object_identifier` for response bodies.

    Always emits the long canonical form (``"analog-input,1"``) even
    when the input used a short alias.
    """
    return f"{_OBJECT_TYPE_TO_KEBAB.get(object_type, object_type.lower())},{instance}"


def _normalize_property_name(name: str) -> str:
    """Accept legacy hyphenated property names (``"present-value"``) as
    well as underscore form (``"present_value"``).

    Keeps the rest of the repo working — ``platform/drivers/bacnet.py``
    and ``platform/data_model_ttl.py`` use the hyphenated form, and the
    frontend sends the hyphenated form from earlier API contracts.
    """
    return name.strip().lower().replace("-", "_")


# ---------------------------------------------------------------------------
# Request bodies (Swagger schema + examples)
# ---------------------------------------------------------------------------


class WhoIsRequestRange(BaseModel):
    """Instance range for BACnet Who-Is (0–4194303 per ASHRAE 135)."""

    start_instance: int = Field(0, ge=0, le=4194303)
    end_instance: int = Field(4194303, ge=0, le=4194303)


class WhoIsBody(BaseModel):
    request: WhoIsRequestRange | None = Field(
        default_factory=WhoIsRequestRange,
        description="Instance range for Who-Is. Omit for a full-range broadcast.",
    )
    timeout_ms: int = Field(
        3000,
        ge=500,
        le=30000,
        description="How long to wait for I-Am responses.",
    )


class DeviceInstanceBody(BaseModel):
    device_instance: int = Field(..., ge=0, le=4194303)


class PointDiscoveryBody(BaseModel):
    instance: DeviceInstanceBody
    enrich: bool = Field(
        True,
        description="Read object-name / description / units for each object (one RPM).",
    )


class PointDiscoveryToGraphBody(PointDiscoveryBody):
    """Same as :class:`PointDiscoveryBody`; separate class preserves the
    route's distinct Swagger summary + frontend-visible schema name."""


def _unwrap_request_wrapper(data: Any) -> Any:
    """Accept the legacy ``{"request": {...}}`` envelope as-is.

    The prior JSON-RPC proxy required payloads wrapped in a ``request``
    field (``{"request": {"device_instance": ..., ...}}``). The flat
    form (``{"device_instance": ..., ...}``) is the new canonical
    shape, but unwrapping lets frontend / scripts keep sending either
    while the migration lands.
    """
    if (
        isinstance(data, dict)
        and "request" in data
        and isinstance(data["request"], dict)
    ):
        return data["request"]
    return data


class ReadPropertyBody(BaseModel):
    device_instance: int = Field(..., ge=0, le=4194303)
    object_identifier: str = Field(..., description="e.g. ``analog-input,1``")
    property_identifier: str = Field(
        "present_value",
        description=(
            "BACnet property. Hyphenated (``present-value``) and underscored "
            "(``present_value``) forms both accepted."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        return _unwrap_request_wrapper(data)


class ReadMultipleItem(BaseModel):
    object_identifier: str
    property_identifier: str = "present_value"


class ReadMultipleBody(BaseModel):
    device_instance: int = Field(..., ge=0, le=4194303)
    requests: list[ReadMultipleItem]

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        return _unwrap_request_wrapper(data)


class WritePropertyBody(BaseModel):
    device_instance: int = Field(..., ge=0, le=4194303)
    object_identifier: str = Field(..., description="e.g. ``analog-output,1``")
    property_identifier: str = Field("present_value")
    value: float | int | bool | str | None = Field(
        ...,
        description="Scalar value; ``null`` relinquishes the priority slot.",
    )
    priority: int = Field(
        ...,
        ge=1,
        le=16,
        description="BACnet priority slot (1–16). Required for every write/release.",
    )

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        return _unwrap_request_wrapper(data)


# ---------------------------------------------------------------------------
# Gateway listing / health
# ---------------------------------------------------------------------------


@router.get(
    "/gateways",
    summary="List configured BACnet gateways",
    response_description="One entry describing the embedded driver.",
)
def bacnet_gateways() -> list[dict[str, Any]]:
    """Return the gateway list.

    After the rusty-bacnet migration there is always exactly one
    gateway — the driver embedded in this process. Multi-site
    deployments will reintroduce this as ``:bacnet_network`` nodes
    in SeleneDB (one per site), but for now the API contract stays
    stable for the frontend.
    """
    s = get_platform_settings()
    return [
        {
            "id": "default",
            "url": "embedded://rusty-bacnet",
            "interface": getattr(s, "bacnet_interface", None) or "0.0.0.0",
            "port": int(getattr(s, "bacnet_port", None) or 47808),
            "description": "Embedded rusty-bacnet driver (BACnet/IP)",
        }
    ]


@router.post("/server_hello", summary="BACnet driver health")
def bacnet_server_hello(_body: dict = Body(default={})) -> dict[str, Any]:
    """Return driver configuration (no actual BACnet traffic).

    The prior implementation round-tripped to diy-bacnet-server to
    prove network reachability; the new driver is in-process so
    "reachable" is tautological. This endpoint is still fast enough
    to use as the frontend's status-dot ping — it returns the
    resolved driver config so the UI can show where it's bound.
    """
    s = get_platform_settings()
    return {
        "ok": True,
        "driver": "rusty-bacnet",
        "transport": "bip",
        "interface": getattr(s, "bacnet_interface", None) or "0.0.0.0",
        "port": int(getattr(s, "bacnet_port", None) or 47808),
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@router.post("/whois_range", summary="Who-Is broadcast, returns devices")
async def bacnet_whois_range(body: Annotated[WhoIsBody, Body()]):
    """Broadcast Who-Is over the configured range; return discovered devices.

    Devices are upserted into Selene as ``:bacnet_device`` nodes
    (same writer :func:`BacnetDriver.discover_devices` uses) and then
    returned to the caller.
    """
    try:
        async with _make_bip_transport() as tx:
            driver = BacnetDriver(tx, make_selene_client_from_settings)
            req = body.request or WhoIsRequestRange()
            devices = await driver.discover_devices(
                timeout_ms=body.timeout_ms,
                low_limit=req.start_instance if req.start_instance > 0 else None,
                high_limit=req.end_instance if req.end_instance < 4194303 else None,
            )
    except BacnetError as exc:
        raise HTTPException(status_code=502, detail=_error_body(exc)) from exc

    return {
        "ok": True,
        "devices": [_device_to_dict(d) for d in devices],
        "count": len(devices),
    }


@router.post("/point_discovery", summary="Enumerate one device's object-list")
async def bacnet_point_discovery(body: Annotated[PointDiscoveryBody, Body()]):
    """Read a device's ``object-list`` property and return the objects.

    Does not persist anything — callers who want the objects in the
    graph use :meth:`point_discovery_to_graph`.
    """
    device = DiscoveredDevice(
        device_instance=body.instance.device_instance,
        address="",  # fetched from prior Who-Is; handled in driver
    )
    try:
        async with _make_bip_transport() as tx:
            # Resolve device address via a directed Who-Is. Keeps this
            # endpoint usable when the prior /whois_range results aren't
            # in Selene yet (e.g. one-off UI probe).
            resolved = await _resolve_device(tx, body.instance.device_instance)
            objects = await tx.read_object_list(resolved)
            if body.enrich and objects:
                objects = await tx.enrich_objects(resolved, objects)
    except BacnetError as exc:
        raise HTTPException(status_code=502, detail=_error_body(exc)) from exc

    return {
        "ok": True,
        "device_instance": resolved.device_instance,
        "device_address": resolved.address,
        "objects": [_object_to_dict(o) for o in objects],
        "count": len(objects),
    }


@router.post(
    "/point_discovery_to_graph",
    summary="Enumerate objects and persist as :bacnet_object nodes",
)
async def bacnet_point_discovery_to_graph(
    body: Annotated[PointDiscoveryToGraphBody, Body()],
):
    """Same as :meth:`point_discovery`, but persists the objects.

    One ``:bacnet_object`` node is upserted per enumerated object,
    each linked to the parent ``:bacnet_device`` via ``exposesObject``.
    Idempotent across repeat calls (keyed on device + object-type +
    instance).
    """
    try:
        async with _make_bip_transport() as tx:
            driver = BacnetDriver(tx, make_selene_client_from_settings)
            resolved = await _resolve_device(tx, body.instance.device_instance)
            objects = await driver.discover_device_objects(resolved, enrich=body.enrich)
    except BacnetError as exc:
        raise HTTPException(status_code=502, detail=_error_body(exc)) from exc

    return {
        "ok": True,
        "device_instance": resolved.device_instance,
        "device_address": resolved.address,
        "objects": [_object_to_dict(o) for o in objects],
        "count": len(objects),
    }


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


@router.post("/read_property", summary="Read one property from one object")
async def bacnet_read_property(body: Annotated[ReadPropertyBody, Body()]):
    """Single-object, single-property read.

    Internally issues an RPM with one entry (matches the behaviour of
    :meth:`read_multiple` for consistency — every read is an RPM
    under the hood).
    """
    object_type, object_instance = _parse_object_identifier(body.object_identifier)
    reads = [
        PropertyRead(
            object_type=object_type,
            object_instance=object_instance,
            property=_normalize_property_name(body.property_identifier),
        )
    ]
    result = await _read_once(body.device_instance, reads)
    return {
        "ok": True,
        "device_instance": body.device_instance,
        "result": _read_result_to_dict(result[0]),
    }


@router.post("/read_multiple", summary="Batch read via ReadPropertyMultiple")
async def bacnet_read_multiple(body: Annotated[ReadMultipleBody, Body()]):
    """Batch property read — one RPM round-trip for the whole list."""
    reads: list[PropertyRead] = []
    for item in body.requests:
        object_type, object_instance = _parse_object_identifier(item.object_identifier)
        reads.append(
            PropertyRead(
                object_type=object_type,
                object_instance=object_instance,
                property=_normalize_property_name(item.property_identifier),
            )
        )
    results = await _read_once(body.device_instance, reads)
    return {
        "ok": True,
        "device_instance": body.device_instance,
        "results": [_read_result_to_dict(r) for r in results],
        "count": len(results),
    }


@router.post("/write_property", summary="Write one property at a given priority")
async def bacnet_write_property(body: Annotated[WritePropertyBody, Body()]):
    """Single-property write with required priority slot.

    Priority is mandatory (1-16) — every write is a commandable
    write or an explicit relinquish. Pass ``value=null`` to
    relinquish the slot.
    """
    object_type, object_instance = _parse_object_identifier(body.object_identifier)
    property_name = _normalize_property_name(body.property_identifier)
    try:
        async with _make_bip_transport() as tx:
            resolved = await _resolve_device(tx, body.device_instance)
            await tx.write_property(
                resolved,
                object_type,
                object_instance,
                property_name,
                body.value,
                priority=body.priority,
            )
    except BacnetDriverError as exc:
        # Validation-class failure → 400 so the frontend can render
        # "fix your input" instead of "talk to your network admin".
        raise HTTPException(
            status_code=400, detail=_error_body(exc, code="BACNET_INVALID")
        ) from exc
    except BacnetError as exc:
        raise HTTPException(status_code=502, detail=_error_body(exc)) from exc

    return {
        "ok": True,
        "device_instance": body.device_instance,
        "object_identifier": body.object_identifier,
        "property_identifier": body.property_identifier,
        "value": body.value,
        "priority": body.priority,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _resolve_device(tx: BipTransport, device_instance: int) -> DiscoveredDevice:
    """Get a :class:`DiscoveredDevice` for a numeric instance.

    The REST API takes ``device_instance`` but the transport methods
    want the full device (address included) — so we issue a directed
    Who-Is for the single instance and wait briefly for the I-Am.
    Raises :class:`HTTPException(404)` if the device doesn't respond.
    """
    devices = await tx.discover_devices(
        timeout_ms=3000,
        low_limit=device_instance,
        high_limit=device_instance,
    )
    if not devices:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "DEVICE_NOT_FOUND",
                "message": f"BACnet device {device_instance} did not respond to Who-Is",
                "details": {"device_instance": device_instance},
            },
        )
    return devices[0]


async def _read_once(
    device_instance: int, reads: list[PropertyRead]
) -> list[PropertyReadResult]:
    """One RPM round-trip against a resolved device."""
    try:
        async with _make_bip_transport() as tx:
            resolved = await _resolve_device(tx, device_instance)
            return await tx.read_present_values(resolved, reads)
    except BacnetError as exc:
        raise HTTPException(status_code=502, detail=_error_body(exc)) from exc


def _device_to_dict(d: DiscoveredDevice) -> dict[str, Any]:
    return {
        "device_instance": d.device_instance,
        "address": d.address,
        "device_name": d.device_name,
        "vendor_id": d.vendor_id,
        "vendor_name": d.vendor_name,
        "model_name": d.model_name,
        "firmware_revision": d.firmware_revision,
    }


def _object_to_dict(o: Any) -> dict[str, Any]:
    """Serialise a :class:`DiscoveredObject` to the wire."""
    return {
        "object_identifier": _format_object_identifier(
            o.object_type, o.object_instance
        ),
        "object_type": o.object_type,
        "object_instance": o.object_instance,
        "concept_curie": o.concept_curie,
        "object_name": o.object_name,
        "description": o.description,
        "units": o.units,
    }


def _read_result_to_dict(r: PropertyReadResult) -> dict[str, Any]:
    return {
        "object_identifier": _format_object_identifier(
            r.object_type, r.object_instance
        ),
        "property_identifier": r.property,
        "value": r.value,
        "error": r.error,
    }
