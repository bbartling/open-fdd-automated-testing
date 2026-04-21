"""Fault state and definitions API for HA/Node-RED (binary_sensors)."""

from pathlib import Path

import psycopg2
from fastapi import APIRouter, Query

from openfdd_stack.platform.database import get_conn
from openfdd_stack.platform.api.schemas import FaultStateItem, FaultDefinitionItem
from openfdd_stack.platform.api.rules import _rules_dir_resolved

router = APIRouter(prefix="/faults", tags=["faults"])


@router.get(
    "/bacnet-devices",
    summary="List BACnet devices from data model (points + equipment)",
)
def list_bacnet_devices(
    site_id: str | None = Query(
        None, description="Filter by site UUID or name; omit for all"
    ),
):
    """
    CRUD/data-model driven: distinct BACnet devices from points (bacnet_device_id not null)
    joined to equipment and sites. For matrix table: one row per device with equipment_type
    for N/A logic (fault equipment_types vs device equipment_type).
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                conditions = ["p.bacnet_device_id IS NOT NULL"]
                params: list = []
                if site_id:
                    conditions.append("(s.id::text = %s OR s.name = %s)")
                    params.extend([site_id, site_id])
                cur.execute(
                    """
                    SELECT DISTINCT ON (s.id, p.bacnet_device_id)
                           s.id AS site_uuid, s.name AS site_name,
                           p.bacnet_device_id, p.equipment_id AS equipment_uuid,
                           e.name AS equipment_name, e.equipment_type
                    FROM points p
                    JOIN sites s ON s.id = p.site_id
                    LEFT JOIN equipment e ON e.id = p.equipment_id
                    WHERE """
                    + " AND ".join(conditions)
                    + """
                    ORDER BY s.id, p.bacnet_device_id, e.name NULLS LAST
                    """,
                    params,
                )
                rows = cur.fetchall()
        return [
            {
                "site_id": str(r["site_uuid"]),
                "site_name": r["site_name"],
                "bacnet_device_id": r["bacnet_device_id"],
                "equipment_id": (
                    str(r["equipment_uuid"]) if r["equipment_uuid"] else None
                ),
                "equipment_name": r["equipment_name"] or "—",
                "equipment_type": r["equipment_type"],
            }
            for r in rows
        ]
    except psycopg2.Error:
        return []


def _fault_state_table_exists(cur) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'fault_state'"
    )
    return cur.fetchone() is not None


@router.get("/active", response_model=list[FaultStateItem])
def list_active_faults(
    site_id: str | None = Query(None, description="Filter by site_id"),
    equipment_id: str | None = Query(None, description="Filter by equipment_id"),
):
    """
    List currently active fault states (for HA binary_sensors).
    Combine with GET /faults/definitions for labels.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if not _fault_state_table_exists(cur):
                    return []
                bacnet_subquery = """
                    (SELECT p.bacnet_device_id FROM points p
                     LEFT JOIN equipment e ON e.id = p.equipment_id
                     WHERE (
                            p.equipment_id::text = fs.equipment_id
                            OR e.name = fs.equipment_id
                           )
                       AND p.bacnet_device_id IS NOT NULL
                       AND (p.site_id::text = fs.site_id OR (SELECT s.name FROM sites s WHERE s.id = p.site_id) = fs.site_id)
                     LIMIT 1)
                """
                site_clause = (
                    "(fs.site_id = %s OR fs.site_id IN (SELECT name FROM sites WHERE id::text = %s))"
                )
                if equipment_id and site_id:
                    cur.execute(
                        f"""
                        SELECT fs.id::text, fs.site_id, fs.equipment_id, fs.fault_id, fs.active,
                               fs.last_changed_ts, fs.last_evaluated_ts, fs.context, {bacnet_subquery} AS bacnet_device_id
                        FROM fault_state fs
                        WHERE {site_clause} AND fs.equipment_id = %s AND fs.active = true
                        ORDER BY fs.site_id, fs.equipment_id, fs.fault_id
                        """,
                        (site_id, site_id, equipment_id),
                    )
                elif site_id:
                    cur.execute(
                        f"""
                        SELECT fs.id::text, fs.site_id, fs.equipment_id, fs.fault_id, fs.active,
                               fs.last_changed_ts, fs.last_evaluated_ts, fs.context, {bacnet_subquery} AS bacnet_device_id
                        FROM fault_state fs
                        WHERE {site_clause} AND fs.active = true
                        ORDER BY fs.site_id, fs.equipment_id, fs.fault_id
                        """,
                        (site_id, site_id),
                    )
                else:
                    cur.execute(f"""
                        SELECT fs.id::text, fs.site_id, fs.equipment_id, fs.fault_id, fs.active,
                               fs.last_changed_ts, fs.last_evaluated_ts, fs.context, {bacnet_subquery} AS bacnet_device_id
                        FROM fault_state fs
                        WHERE fs.active = true
                        ORDER BY fs.site_id, fs.equipment_id, fs.fault_id
                        """)
                rows = cur.fetchall()
        return [FaultStateItem.model_validate(dict(r)) for r in rows]
    except psycopg2.Error:
        return []


@router.get("/state", response_model=list[FaultStateItem])
def list_fault_state(
    site_id: str | None = Query(None),
    equipment_id: str | None = Query(
        None, description="Filter by equipment_id (optional with site_id)"
    ),
):
    """List all fault state rows (active and cleared). Use for full state snapshot."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                if not _fault_state_table_exists(cur):
                    return []
                bacnet_subquery = """
                    (SELECT p.bacnet_device_id FROM points p
                     LEFT JOIN equipment e ON e.id = p.equipment_id
                     WHERE (
                            p.equipment_id::text = fs.equipment_id
                            OR e.name = fs.equipment_id
                           )
                       AND p.bacnet_device_id IS NOT NULL
                       AND (p.site_id::text = fs.site_id OR (SELECT s.name FROM sites s WHERE s.id = p.site_id) = fs.site_id)
                     LIMIT 1)
                """
                site_clause = (
                    "(fs.site_id = %s OR fs.site_id IN (SELECT name FROM sites WHERE id::text = %s))"
                )
                if equipment_id and site_id:
                    cur.execute(
                        f"""
                        SELECT fs.id::text, fs.site_id, fs.equipment_id, fs.fault_id, fs.active,
                               fs.last_changed_ts, fs.last_evaluated_ts, fs.context, {bacnet_subquery} AS bacnet_device_id
                        FROM fault_state fs
                        WHERE {site_clause} AND fs.equipment_id = %s
                        ORDER BY fs.fault_id
                        """,
                        (site_id, site_id, equipment_id),
                    )
                elif site_id:
                    cur.execute(
                        f"""
                        SELECT fs.id::text, fs.site_id, fs.equipment_id, fs.fault_id, fs.active,
                               fs.last_changed_ts, fs.last_evaluated_ts, fs.context, {bacnet_subquery} AS bacnet_device_id
                        FROM fault_state fs
                        WHERE {site_clause}
                        ORDER BY fs.equipment_id, fs.fault_id
                        """,
                        (site_id, site_id),
                    )
                else:
                    cur.execute(f"""
                        SELECT fs.id::text, fs.site_id, fs.equipment_id, fs.fault_id, fs.active,
                               fs.last_changed_ts, fs.last_evaluated_ts, fs.context, {bacnet_subquery} AS bacnet_device_id
                        FROM fault_state fs
                        ORDER BY fs.site_id, fs.equipment_id, fs.fault_id
                        """)
                rows = cur.fetchall()
        return [FaultStateItem.model_validate(dict(r)) for r in rows]
    except psycopg2.Error:
        return []


@router.get("/definitions", response_model=list[FaultDefinitionItem])
def list_fault_definitions():
    """List fault definitions (fault_id, name, severity, category) for HA entity labels."""
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT fault_id, name, description, severity, category, equipment_types
                    FROM fault_definitions
                    ORDER BY category, fault_id
                    """)
                rows = cur.fetchall()
        out = []
        for r in rows:
            out.append(
                FaultDefinitionItem(
                    fault_id=r["fault_id"],
                    name=r["name"],
                    description=r.get("description"),
                    severity=r.get("severity") or "warning",
                    category=r.get("category") or "general",
                    equipment_types=r.get("equipment_types"),
                )
            )
        return out
    except psycopg2.Error:
        return []


def _normalize_brick_name(v: str | None) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    if ":" in s:
        s = s.split(":")[-1]
    return s


def _fault_id_from_rule(rule: dict) -> str:
    name = str(rule.get("name") or "rule").strip()
    flag = str(rule.get("flag") or "").strip()
    return flag or f"{name}_flag"


@router.get(
    "/bacnet-device-faults",
    summary="Configured + active faults for each BACnet device",
)
def list_bacnet_device_faults(
    site_id: str | None = Query(
        None, description="Filter by site UUID or name; omit for all"
    ),
):
    """
    Derive fault applicability per BACnet device from modeled points + rule YAML.

    Uses points' brick_type/fdd_input/external_id and rules inputs.*.brick to
    return a deterministic mapping the frontend can render without re-implementing
    rule matching logic.
    """
    from open_fdd.engine.runner import load_rules_from_dir

    conditions = ["p.bacnet_device_id IS NOT NULL"]
    params: list[str] = []
    if site_id:
        conditions.append("(s.id::text = %s OR s.name = %s)")
        params.extend([site_id, site_id])

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id::text AS point_id, p.site_id::text AS site_uuid, s.name AS site_name,
                       p.bacnet_device_id, p.equipment_id::text AS equipment_id, e.name AS equipment_name,
                       e.equipment_type, p.external_id, p.fdd_input, p.brick_type,
                       p.object_identifier, p.object_name
                FROM points p
                JOIN sites s ON s.id = p.site_id
                LEFT JOIN equipment e ON e.id = p.equipment_id
                WHERE """
                + " AND ".join(conditions),
                params,
            )
            point_rows = cur.fetchall()

            if _fault_state_table_exists(cur):
                cur.execute(
                    """
                    SELECT fs.site_id, fs.equipment_id, fs.fault_id, fs.active
                    FROM fault_state fs
                    """
                )
                state_rows = cur.fetchall()
            else:
                state_rows = []

    rules_path = _rules_dir_resolved()
    rules = load_rules_from_dir(Path(rules_path)) if Path(rules_path).exists() else []

    devices: dict[tuple[str, str], dict] = {}
    site_alias_to_uuid: dict[str, str] = {}
    for r in point_rows:
        key = (r["site_uuid"], str(r["bacnet_device_id"]))
        site_uuid = str(r["site_uuid"])
        site_name = str(r["site_name"] or "").strip()
        site_alias_to_uuid[site_uuid] = site_uuid
        if site_name:
            site_alias_to_uuid[site_name] = site_uuid
        if key not in devices:
            devices[key] = {
                "site_id": site_uuid,
                "site_name": site_name or r["site_name"],
                "bacnet_device_id": str(r["bacnet_device_id"]),
                "equipment_ids": set(),
                "equipment_names": set(),
                "equipment_types": set(),
                "points": [],
            }
        d = devices[key]
        if r.get("equipment_id"):
            d["equipment_ids"].add(str(r["equipment_id"]))
        if r.get("equipment_name"):
            d["equipment_names"].add(str(r["equipment_name"]))
        if r.get("equipment_type"):
            d["equipment_types"].add(str(r["equipment_type"]))
        d["points"].append(
            {
                "point_id": r.get("point_id"),
                "external_id": r.get("external_id"),
                "fdd_input": r.get("fdd_input"),
                "brick_type": _normalize_brick_name(r.get("brick_type")),
                "object_identifier": r.get("object_identifier"),
                "object_name": r.get("object_name"),
            }
        )

    # Map (site_id text or site name, equipment_id/equipment_name) -> bacnet_device_id
    # from points, so we do not depend on fault_state having a bacnet_device_id column.
    equip_site_to_device: dict[tuple[str, str], str] = {}
    for r in point_rows:
        eqid = str(r.get("equipment_id") or "").strip()
        eqname = str(r.get("equipment_name") or "").strip()
        did = str(r.get("bacnet_device_id") or "").strip()
        site_uuid = str(r.get("site_uuid") or "").strip()
        site_name = str(r.get("site_name") or "").strip()
        if not did:
            continue
        aliases = [a for a in (eqid, eqname) if a]
        for alias in aliases:
            equip_site_to_device[(site_uuid, alias)] = did
            if site_name:
                equip_site_to_device[(site_name, alias)] = did

    active_by_device: dict[tuple[str, str], set[str]] = {}
    for s in state_rows:
        if not s.get("active"):
            continue
        fid = str(s.get("fault_id") or "").strip()
        if not fid:
            continue
        sid = str(s.get("site_id") or "").strip()
        eqid = str(s.get("equipment_id") or "").strip()
        did = equip_site_to_device.get((sid, eqid), "")
        if not did:
            continue
        canonical_sid = site_alias_to_uuid.get(sid, sid)
        key = (canonical_sid, did)
        active_by_device.setdefault(key, set()).add(fid)

    out = []
    for key, dev in devices.items():
        applicable: set[str] = set()
        matched_points_by_fault: dict[str, list[dict]] = {}
        point_bricks = {
            _normalize_brick_name(p.get("brick_type"))
            for p in dev["points"]
            if _normalize_brick_name(p.get("brick_type"))
        }
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            fault_id = _fault_id_from_rule(rule)
            if not fault_id:
                continue
            eq_types = rule.get("equipment_types") or rule.get("equipment_type")
            if eq_types:
                allowed = (
                    set(eq_types) if isinstance(eq_types, list) else {str(eq_types)}
                )
                if allowed and not (set(dev["equipment_types"]) & allowed):
                    continue
            inputs = rule.get("inputs") if isinstance(rule.get("inputs"), dict) else {}
            required_bricks = {
                _normalize_brick_name(v.get("brick"))
                for v in inputs.values()
                if isinstance(v, dict) and _normalize_brick_name(v.get("brick"))
            }
            if not required_bricks:
                applicable.add(fault_id)
                continue
            if point_bricks & required_bricks:
                applicable.add(fault_id)
                matched_points_by_fault[fault_id] = [
                    p
                    for p in dev["points"]
                    if _normalize_brick_name(p.get("brick_type")) in required_bricks
                ][:20]

        out.append(
            {
                "site_id": dev["site_id"],
                "site_name": dev["site_name"],
                "bacnet_device_id": dev["bacnet_device_id"],
                "equipment_ids": sorted(dev["equipment_ids"]),
                "equipment_names": sorted(dev["equipment_names"]),
                "applicable_fault_ids": sorted(applicable),
                "active_fault_ids": sorted(active_by_device.get(key, set())),
                "matched_points_by_fault": matched_points_by_fault,
            }
        )
    return out
