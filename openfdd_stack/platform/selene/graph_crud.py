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


def _site_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Postgres sites row to the Selene node property shape.

    ``metadata`` is a JSON-able dict in Postgres; SeleneDB stores scalar
    properties, so we serialize nested shapes as a JSON string (matching the
    existing HTTP-API convention for nested JSON).
    """
    metadata = row.get("metadata") or {}
    if isinstance(metadata, (dict, list)):
        metadata = json.dumps(metadata)
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
    """Upsert a ``:site`` node mirroring a Postgres sites row.

    Returns the resulting node payload, or ``None`` when the sync was skipped
    due to a Selene error. CRUD callers never surface the failure; it is
    logged with enough context for a reconciliation job to redo it later.
    """
    external_id = str(row["id"])
    props = _site_properties(row)
    try:
        existing = _find_by_external_id(client, SITE_LABEL, external_id)
        if existing is None:
            return client.create_node([SITE_LABEL], props)
        existing_props = set((existing.get("properties") or {}).keys())
        incoming_props = set(props.keys())
        remove = sorted(existing_props - incoming_props)
        return client.modify_node(
            existing["id"],
            set_properties=props,
            remove_properties=remove or None,
        )
    except SeleneError as exc:
        logger.warning(
            "selene upsert_site failed for %s (%s); Postgres write remains "
            "authoritative. Backfill can reconcile later.",
            external_id,
            exc,
        )
        return None


def delete_site(client: SeleneClient, site_id: UUID | str) -> bool:
    """Delete the ``:site`` node mirroring a Postgres sites row.

    Returns True when a node was deleted, False when none existed or the sync
    could not complete. Does not raise; see the module docstring on failure
    semantics.
    """
    external_id = str(site_id)
    try:
        existing = _find_by_external_id(client, SITE_LABEL, external_id)
        if existing is None:
            return False
        client.delete_node(existing["id"])
        return True
    except SeleneError as exc:
        logger.warning(
            "selene delete_site failed for %s (%s); Postgres deletion stands. "
            "Orphan Selene node will need manual cleanup or backfill.",
            external_id,
            exc,
        )
        return False
