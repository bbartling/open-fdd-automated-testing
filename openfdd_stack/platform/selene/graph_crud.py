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

logger = logging.getLogger(__name__)

SITE_LABEL = "site"
EQUIPMENT_LABEL = "equipment"
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

    ``properties`` must already include ``external_id`` under
    :data:`EXTERNAL_ID_PROP`. Stale keys (present on the existing node but not
    in ``properties``) are removed so the graph doesn't accumulate stale fields
    after a rename. On any Selene error, logs a warning with ``op_name`` +
    ``external_id`` + full traceback and returns ``None`` \u2014 the caller has
    already committed to Postgres.
    """
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


def _flatten_metadata(metadata: Any) -> str | None:
    """Serialize a JSON-able metadata field to a string for Selene's flat property model."""
    if metadata is None:
        return None
    if isinstance(metadata, str):
        return metadata or None
    if isinstance(metadata, (dict, list)):
        if not metadata:
            return None
        return json.dumps(metadata)
    return str(metadata)


# ---------------------------------------------------------------------------
# sites
# ---------------------------------------------------------------------------


def _site_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Postgres sites row to the Selene node property shape."""
    metadata = _flatten_metadata(row.get("metadata"))
    props: dict[str, Any] = {
        EXTERNAL_ID_PROP: str(row["id"]),
        "name": row.get("name") or "",
    }
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
    props: dict[str, Any] = {
        EXTERNAL_ID_PROP: str(row["id"]),
        "name": row.get("name") or "",
    }
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
