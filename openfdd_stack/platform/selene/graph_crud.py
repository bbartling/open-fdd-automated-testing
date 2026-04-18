"""SeleneDB graph CRUD sync helpers for sites / equipment / points.

During Phase 2+3 of the migration, Postgres stays primary (timeseries hypertables
still FK to sites/equipment/points). When ``OFDD_STORAGE_BACKEND=selene``, CRUD
routers call into this module after committing to Postgres so Selene carries a
parallel graph representation. Phase 4 removes the Postgres writes.

Nodes are keyed by ``external_id`` = ``str(db_uuid)``. No schema registration
required \u2014 Selene accepts unregistered labels and the upcoming common pack
will bring a formal schema later.

Sync failures log warnings but never raise into the CRUD response: the Postgres
write is authoritative, and a backfill job can reconcile later. This matches
the existing ``sync_ttl_to_file()`` best-effort pattern.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from openfdd_stack.platform.selene.client import SeleneClient
from openfdd_stack.platform.selene.exceptions import SeleneError
from openfdd_stack.platform.selene.naming import canonical_name

logger = logging.getLogger(__name__)

SITE_LABEL = "site"
EQUIPMENT_LABEL = "equipment"
POINT_LABEL = "point"
EXTERNAL_ID_PROP = "external_id"


_PAGE_SIZE = 100
# Safety valve: stop walking after this many pages even if server misreports total.
# 100 pages × 100 nodes = 10k nodes of a single label, well beyond any realistic
# building-portfolio size. A runaway loop here would block every CRUD response.
_MAX_PAGES = 100


def _find_by_external_id(
    client: SeleneClient, label: str, external_id: str
) -> dict[str, Any] | None:
    """Locate the single Selene node with this (label, external_id) across pages.

    ``list_nodes`` caps at 1000 per request (and we use 100 for responsiveness);
    a portfolio with more than 100 sites/equipment/points of one label would
    miss matches on later pages if we only hit page 1. Walks pages until the
    server-reported total is consumed, the page is short, or a safety cap
    (10k nodes) hits.
    """
    matches: list[dict[str, Any]] = []
    offset = 0
    for _page in range(_MAX_PAGES):
        body = client.list_nodes(label=label, limit=_PAGE_SIZE, offset=offset)
        nodes = body.get("nodes", []) or []
        matches.extend(
            n
            for n in nodes
            if (n.get("properties") or {}).get(EXTERNAL_ID_PROP) == external_id
        )
        total = body.get("total")
        offset += len(nodes)
        if not nodes or len(nodes) < _PAGE_SIZE:
            break
        if total is not None and offset >= total:
            break
    else:
        logger.warning(
            "_find_by_external_id hit page cap (%d pages) for %s=%s on :%s; "
            "some nodes may be beyond the walk.",
            _MAX_PAGES,
            EXTERNAL_ID_PROP,
            external_id,
            label,
        )
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning(
            "%d %s nodes found with %s=%s; operating on the first (id=%s).",
            len(matches),
            label,
            EXTERNAL_ID_PROP,
            external_id,
            matches[0].get("id"),
        )
    return matches[0]


def _upsert_by_external_id(
    client: SeleneClient,
    label: str,
    external_id: str,
    properties: dict[str, Any],
    *,
    op_name: str,
) -> dict[str, Any] | None:
    """Shared upsert primitive used by site/equipment/point sync helpers.

    The helper owns the ``external_id`` invariant: it writes ``external_id``
    onto ``properties`` before sending so callers can't silently drift a
    node's key away from the value used to locate it. Stale keys (present on
    the existing node but not in ``properties``) are removed so the graph
    doesn't accumulate stale fields after a rename.

    On any Selene error, logs a warning with ``op_name`` + ``external_id`` +
    full traceback and returns ``None`` \u2014 the caller has already committed
    to Postgres.
    """
    # Enforce the single-key invariant at the persistence boundary so caller
    # mistakes can't create orphans. Mutates the dict in place \u2014 call sites
    # build fresh property dicts per mutation, so this is safe.
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
            "%s failed for %s=%s on :%s; Postgres write remains authoritative, "
            "backfill can reconcile later.",
            op_name,
            EXTERNAL_ID_PROP,
            external_id,
            label,
            exc_info=True,
        )
        return None


def _delete_by_external_id(
    client: SeleneClient, label: str, external_id: str, *, op_name: str
) -> bool:
    """Shared delete primitive. See :func:`_upsert_by_external_id`."""
    try:
        existing = _find_by_external_id(client, label, external_id)
        if existing is None:
            return False
        client.delete_node(existing["id"])
        return True
    except SeleneError:
        logger.warning(
            "%s failed for %s=%s on :%s; Postgres deletion stands. Orphan "
            "Selene node will need manual cleanup or backfill.",
            op_name,
            EXTERNAL_ID_PROP,
            external_id,
            label,
            exc_info=True,
        )
        return False


def _canonical_name_pair(raw: Any) -> tuple[str, str | None]:
    """Return ``(canonical, display_or_None)`` for an instance name.

    Every CRUD write produces a canonical ``name`` per the
    selenepack-smartbuildings convention (lowercase-kebab ASCII, ``/``
    paths). The BAS-native label lives in ``display_name`` \u2014 populated
    only when it actually differs from the canonical form so we don't
    store redundant info (``"ahu-1"`` / ``"ahu-1"``).
    """
    raw_str = "" if raw is None else str(raw).strip()
    canonical = canonical_name(raw_str)
    display = raw_str if raw_str and raw_str != canonical else None
    return canonical, display


def _flatten_metadata(metadata: Any) -> str | None:
    """Serialize a metadata field to a string for Selene's flat property model.

    Preserves JSON containers \u2014 including an explicitly empty ``{}`` or ``[]``
    \u2014 so callers can distinguish "absent metadata" (``None`` \u2192 property not
    written) from "explicit empty JSON value" (written as ``"{}"``). Postgres
    defaults to ``{}`` for the ``metadata`` jsonb column; the Selene-2.3a
    behaviour wrote that as ``metadata_json="{}"`` and we preserve it.
    """
    if metadata is None:
        return None
    if isinstance(metadata, str):
        return metadata or None
    if isinstance(metadata, (dict, list)):
        return json.dumps(metadata)
    return str(metadata)


# ---------------------------------------------------------------------------
# sites
# ---------------------------------------------------------------------------


def _site_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Postgres sites row to the Selene node property shape."""
    metadata = _flatten_metadata(row.get("metadata"))
    canonical, display = _canonical_name_pair(row.get("name"))
    props: dict[str, Any] = {
        EXTERNAL_ID_PROP: str(row["id"]),
        "name": canonical,
    }
    if display:
        props["display_name"] = display
    if row.get("description"):
        props["description"] = row["description"]
    if metadata:
        props["metadata_json"] = metadata
    return props


def upsert_site(client: SeleneClient, row: dict[str, Any]) -> dict[str, Any] | None:
    """Upsert a ``:site`` node mirroring a Postgres sites row."""
    external_id = str(row["id"])
    return _upsert_by_external_id(
        client,
        SITE_LABEL,
        external_id,
        _site_properties(row),
        op_name="selene upsert_site",
    )


def delete_site(client: SeleneClient, site_id: UUID | str) -> bool:
    """Delete the ``:site`` node mirroring a Postgres sites row."""
    return _delete_by_external_id(
        client,
        SITE_LABEL,
        str(site_id),
        op_name="selene delete_site",
    )


# ---------------------------------------------------------------------------
# equipment
# ---------------------------------------------------------------------------


def _equipment_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Postgres equipment row to the Selene node property shape.

    ``site_id`` is persisted as a ``site_external_id`` property (pointing at
    the parent site's ``external_id``). Phase 2.3d / later cleanup will promote
    this to a proper ``(:site)-[:contains]->(:equipment)`` graph edge, but a
    property keeps this slice focused on node-level parity.
    """
    metadata = _flatten_metadata(row.get("metadata"))
    canonical, display = _canonical_name_pair(row.get("name"))
    props: dict[str, Any] = {
        EXTERNAL_ID_PROP: str(row["id"]),
        "name": canonical,
    }
    if display:
        props["display_name"] = display
    if row.get("site_id"):
        props["site_external_id"] = str(row["site_id"])
    if row.get("description"):
        props["description"] = row["description"]
    if row.get("equipment_type"):
        props["equipment_type"] = row["equipment_type"]
    if row.get("feeds_equipment_id"):
        props["feeds_external_id"] = str(row["feeds_equipment_id"])
    if row.get("fed_by_equipment_id"):
        props["fed_by_external_id"] = str(row["fed_by_equipment_id"])
    if metadata:
        props["metadata_json"] = metadata
    return props


def upsert_equipment(
    client: SeleneClient, row: dict[str, Any]
) -> dict[str, Any] | None:
    """Upsert an ``:equipment`` node mirroring a Postgres equipment row."""
    external_id = str(row["id"])
    return _upsert_by_external_id(
        client,
        EQUIPMENT_LABEL,
        external_id,
        _equipment_properties(row),
        op_name="selene upsert_equipment",
    )


def delete_equipment(client: SeleneClient, equipment_id: UUID | str) -> bool:
    """Delete the ``:equipment`` node mirroring a Postgres equipment row."""
    return _delete_by_external_id(
        client,
        EQUIPMENT_LABEL,
        str(equipment_id),
        op_name="selene delete_equipment",
    )


# ---------------------------------------------------------------------------
# points
# ---------------------------------------------------------------------------


def _point_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Postgres points row to the Selene node property shape.

    Note the two-``external_id`` naming conflict: the Postgres ``points.id``
    (UUID primary key) becomes the Selene ``external_id`` keying property
    (consistent with sites/equipment). The Postgres ``points.external_id``
    column carries the BAS-native point handle (``"AHU_SA_Temp"``), which
    becomes the Selene ``name`` (canonicalised) + ``display_name`` pair.

    ``concept_curie`` is intentionally not populated here \u2014 Decision D5
    defers Mnemosyne resolution to Phase 2.2 when the brick_ttl_resolver
    rewrite lands. ``brick_type`` persists as a property so downstream
    consumers (the FDD loop, the /data-model export) stay aligned until
    that resolution path comes online.
    """
    modbus = _flatten_metadata(row.get("modbus_config"))
    canonical, display = _canonical_name_pair(row.get("external_id"))
    props: dict[str, Any] = {
        EXTERNAL_ID_PROP: str(row["id"]),
        "name": canonical,
    }
    if display:
        props["display_name"] = display
    if row.get("site_id"):
        props["site_external_id"] = str(row["site_id"])
    if row.get("equipment_id"):
        props["equipment_external_id"] = str(row["equipment_id"])
    if row.get("brick_type"):
        props["brick_type"] = row["brick_type"]
    if row.get("fdd_input"):
        props["fdd_input"] = row["fdd_input"]
    if row.get("unit"):
        props["unit"] = row["unit"]
    if row.get("description"):
        props["description"] = row["description"]
    if row.get("object_identifier"):
        props["object_identifier"] = row["object_identifier"]
    if row.get("object_name"):
        props["object_name"] = row["object_name"]
    if row.get("bacnet_device_id"):
        props["bacnet_device_id"] = row["bacnet_device_id"]
    # polling is a bool with a True default; write it unconditionally so the
    # node reflects the current value rather than inheriting an old one on rename.
    if "polling" in row and row["polling"] is not None:
        props["polling"] = bool(row["polling"])
    if modbus:
        props["modbus_config_json"] = modbus
    return props


def upsert_point(client: SeleneClient, row: dict[str, Any]) -> dict[str, Any] | None:
    """Upsert a ``:point`` node mirroring a Postgres points row."""
    external_id = str(row["id"])
    return _upsert_by_external_id(
        client,
        POINT_LABEL,
        external_id,
        _point_properties(row),
        op_name="selene upsert_point",
    )


def delete_point(client: SeleneClient, point_id: UUID | str) -> bool:
    """Delete the ``:point`` node mirroring a Postgres points row."""
    return _delete_by_external_id(
        client,
        POINT_LABEL,
        str(point_id),
        op_name="selene delete_point",
    )
