"""Selene graph writers for discovered BACnet state.

Discovered devices and objects land in SeleneDB as
``:bacnet_device`` / ``:bacnet_object`` nodes per the
``bacnet-driver`` schema pack
(``config/schema_packs/bacnet-driver.json``). One optional
``:bacnet_network`` node anchors the device set so graph queries like
"everything on this network" work naturally.

Keying convention (stable, human-readable so the external_id doubles
as a debugging label):

- :bacnet_network   external_id ``bacnet:net:{name}``
- :bacnet_device    external_id ``bacnet:device:{instance}``
- :bacnet_object    external_id ``bacnet:obj:{device_instance}:{object_type}:{object_instance}``

Same best-effort posture as the rest of the Selene sync helpers: errors
log with traceback and return ``None`` / ``False``; the caller decides
whether to surface the failure. These writers are *synchronous*
(SeleneClient is sync); async callers wrap the whole discover-and-write
pipeline in ``asyncio.to_thread`` once, not per-call.
"""

from __future__ import annotations

import logging
from typing import Any

from openfdd_stack.platform.bacnet.transport import (
    DiscoveredDevice,
    DiscoveredObject,
)
from openfdd_stack.platform.selene.client import SeleneClient
from openfdd_stack.platform.selene.exceptions import SeleneError

logger = logging.getLogger(__name__)


BACNET_NETWORK_LABEL = "bacnet_network"
BACNET_DEVICE_LABEL = "bacnet_device"
BACNET_OBJECT_LABEL = "bacnet_object"

HAS_DEVICE_EDGE = "hasDevice"
EXPOSES_OBJECT_EDGE = "exposesObject"

EXTERNAL_ID_PROP = "external_id"

_PAGE_SIZE = 100
_MAX_PAGES = 100


# ---------------------------------------------------------------------------
# Keying
# ---------------------------------------------------------------------------


def network_external_id(name: str) -> str:
    return f"bacnet:net:{name}"


def device_external_id(device_instance: int) -> str:
    return f"bacnet:device:{device_instance}"


def object_external_id(
    *, device_instance: int, object_type: str, object_instance: int
) -> str:
    return f"bacnet:obj:{device_instance}:{object_type}:{object_instance}"


# ---------------------------------------------------------------------------
# Internal helpers — paged external_id lookup + upsert primitive
# ---------------------------------------------------------------------------


def _find_by_external_id(
    client: SeleneClient, label: str, external_id: str
) -> dict[str, Any] | None:
    """Locate a single ``(label, external_id)`` match across pages."""
    offset = 0
    for _page in range(_MAX_PAGES):
        body = client.list_nodes(label=label, limit=_PAGE_SIZE, offset=offset)
        nodes = body.get("nodes", []) or []
        for node in nodes:
            if (node.get("properties") or {}).get(EXTERNAL_ID_PROP) == external_id:
                return node
        total = body.get("total")
        offset += len(nodes)
        if not nodes or len(nodes) < _PAGE_SIZE:
            return None
        if total is not None and offset >= total:
            return None
    logger.warning(
        "_find_by_external_id hit page cap for %s=%s on :%s",
        EXTERNAL_ID_PROP,
        external_id,
        label,
    )
    return None


def _upsert_node(
    client: SeleneClient,
    label: str,
    external_id: str,
    properties: dict[str, Any],
    *,
    op_name: str,
) -> dict[str, Any] | None:
    """Create-or-update a node keyed by ``external_id``.

    Stale properties (present on the stored node, absent from
    ``properties``) are removed so a renamed device doesn't carry a
    ghost of its old name forever.
    """
    properties[EXTERNAL_ID_PROP] = external_id
    try:
        existing = _find_by_external_id(client, label, external_id)
        if existing is None:
            return client.create_node([label], properties)
        existing_props = set((existing.get("properties") or {}).keys())
        incoming_props = set(properties.keys())
        remove = sorted(existing_props - incoming_props)
        return client.modify_node(
            existing["id"],
            set_properties=properties,
            remove_properties=remove or None,
        )
    except SeleneError:
        logger.warning(
            "%s failed for %s=%s on :%s",
            op_name,
            EXTERNAL_ID_PROP,
            external_id,
            label,
            exc_info=True,
        )
        return None


def _ensure_edge(
    client: SeleneClient,
    *,
    source_id: int,
    target_id: int,
    label: str,
    op_name: str,
) -> None:
    """Idempotent edge creation via client-side check + create.

    ``SeleneClient.create_edge`` is a straight POST — it does **not**
    dedupe, so repeat discoveries would otherwise accumulate duplicate
    ``hasDevice`` / ``exposesObject`` edges. Match the existing
    pattern in :mod:`openfdd_stack.platform.selene.graph_crud`
    (``_reconcile_single_edge``): list the source node's edges, skip
    the create when one already matches ``(target, label)``. Failures
    are best-effort — logged, not raised.
    """
    try:
        existing = client.get_node_edges(source_id) or {}
        for edge in existing.get("edges", []) or []:
            if (
                edge.get("source") == source_id
                and edge.get("target") == target_id
                and edge.get("label") == label
            ):
                return
        client.create_edge(source_id, target_id, label)
    except SeleneError:
        logger.warning(
            "%s failed to upsert edge %s -[:%s]-> %s",
            op_name,
            source_id,
            label,
            target_id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Public writers
# ---------------------------------------------------------------------------


def ensure_bacnet_network(
    client: SeleneClient,
    *,
    name: str = "bacnet-default",
    broadcast_address: str | None = None,
    port: int = 47808,
    transport: str = "bip",
) -> dict[str, Any] | None:
    """Upsert a ``:bacnet_network`` node; returns the stored node or ``None``.

    One network per driver instance is the common case — a site has one
    BACnet/IP broadcast domain. Multi-gateway deployments call this
    once per gateway with distinct names.
    """
    props: dict[str, Any] = {
        "name": name,
        "network_type": "bacnet",
        "port": port,
        "transport": transport,
    }
    if broadcast_address:
        props["broadcast_address"] = broadcast_address
    return _upsert_node(
        client,
        BACNET_NETWORK_LABEL,
        network_external_id(name),
        props,
        op_name="bacnet ensure_bacnet_network",
    )


def upsert_bacnet_device(
    client: SeleneClient,
    device: DiscoveredDevice,
    *,
    network_node_id: int | None = None,
) -> dict[str, Any] | None:
    """Upsert a ``:bacnet_device`` node and (optionally) link it to a network.

    ``device.device_name`` populates the required ``name`` field; when
    missing (pre-enrichment), a placeholder ``"BACnet Device {instance}"``
    keeps the schema's ``name: string!`` satisfied and gives the UI
    something to render before the follow-up read lands.
    """
    name = device.device_name or f"BACnet Device {device.device_instance}"
    props: dict[str, Any] = {
        "name": name,
        "instance": device.device_instance,
        "address": device.address,
    }
    if device.mac_address is not None:
        props["mac_address"] = device.mac_address.hex()
    if device.max_apdu_length is not None:
        props["max_apdu"] = device.max_apdu_length
    if device.segmentation_supported:
        props["segmentation"] = device.segmentation_supported
    if device.vendor_id is not None:
        props["vendor_id"] = device.vendor_id
    if device.vendor_name:
        props["vendor_name"] = device.vendor_name
    if device.model_name:
        props["model_name"] = device.model_name
    if device.firmware_revision:
        props["firmware_rev"] = device.firmware_revision

    node = _upsert_node(
        client,
        BACNET_DEVICE_LABEL,
        device_external_id(device.device_instance),
        props,
        op_name="bacnet upsert_bacnet_device",
    )
    if node is None:
        return None
    if network_node_id is not None and isinstance(node.get("id"), int):
        _ensure_edge(
            client,
            source_id=network_node_id,
            target_id=node["id"],
            label=HAS_DEVICE_EDGE,
            op_name="bacnet upsert_bacnet_device",
        )
    return node


def upsert_bacnet_object(
    client: SeleneClient,
    obj: DiscoveredObject,
    *,
    device_node_id: int | None = None,
) -> dict[str, Any] | None:
    """Upsert a ``:bacnet_object`` node and (optionally) link to its device.

    ``concept_curie`` is the schema-required Mnemosyne alignment — the
    caller resolves it via :func:`object_types.curie_for_object_type`
    and we just persist it. Missing ``object_name`` (pre-enrichment)
    gets a placeholder so the required string field isn't empty.
    """
    object_name = obj.object_name or f"{obj.object_type} {obj.object_instance}"
    props: dict[str, Any] = {
        "concept_curie": obj.concept_curie,
        "instance": obj.object_instance,
        "object_name": object_name,
        "object_type": obj.object_type,
    }
    if obj.description:
        props["description"] = obj.description
    if obj.units:
        props["units"] = obj.units

    node = _upsert_node(
        client,
        BACNET_OBJECT_LABEL,
        object_external_id(
            device_instance=obj.device_instance,
            object_type=obj.object_type,
            object_instance=obj.object_instance,
        ),
        props,
        op_name="bacnet upsert_bacnet_object",
    )
    if node is None:
        return None
    if device_node_id is not None and isinstance(node.get("id"), int):
        _ensure_edge(
            client,
            source_id=device_node_id,
            target_id=node["id"],
            label=EXPOSES_OBJECT_EDGE,
            op_name="bacnet upsert_bacnet_object",
        )
    return node
