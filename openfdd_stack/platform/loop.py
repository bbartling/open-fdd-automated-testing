"""
Continuous FDD loop: periodic rule runs with hot-reload.

Every run (default every 3 hours): loads rules from YAML (rule edits apply immediately),
pulls last N days of data into pandas, runs all rules, writes fault_results.
Operators tune rules in YAML, spot-check in Grafana, no restart needed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from open_fdd.engine.column_map_resolver import ColumnMapResolver

_log = logging.getLogger(__name__)

import pandas as pd
from psycopg2.extras import Json, execute_values

from openfdd_stack.platform.config import get_platform_settings
from openfdd_stack.platform.database import get_conn
from openfdd_stack.platform.graph_model import get_ttl_path_resolved
from openfdd_stack.platform.site_resolver import resolve_site_uuid
from open_fdd.schema import FDDResult


def _fdd_runner_run_kwargs(
    settings: object,
    *,
    strict: bool,
    column_map: dict[str, str],
) -> dict:
    """
    Keyword arguments for ``RuleRunner.run`` aligned with installed open-fdd.

    open-fdd 2.3+ adds ``input_validation`` and Pydantic-backed param coercion; older
    wheels only support ``skip_missing_columns``.
    """
    kw: dict = {
        "timestamp_col": "timestamp",
        "rolling_window": getattr(settings, "rolling_window", None),
        "column_map": column_map,
        "params": {"units": "imperial"},
    }
    try:
        import importlib.metadata as im

        parts = im.version("open-fdd").split(".")
        mm = (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        new_api = mm >= (2, 3)
    except Exception:
        new_api = False
    if strict:
        kw["skip_missing_columns"] = False
        if new_api:
            kw["input_validation"] = "strict"
    else:
        kw["skip_missing_columns"] = True
        if new_api:
            kw["input_validation"] = "off"
    return kw


def load_timeseries_for_site(
    site_id: str,
    start_ts: datetime,
    end_ts: datetime,
    column_map: dict[str, str],
) -> Optional[pd.DataFrame]:
    """
    Load all timeseries_readings for a site into a DataFrame (BACnet + weather).
    Columns = external_id; column_map applied for Brick resolution.
    """
    site_uuid = resolve_site_uuid(site_id, create_if_empty=False)
    if site_uuid is None:
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.external_id
                FROM points p
                WHERE p.site_id = %s
                ORDER BY p.external_id
                """,
                (str(site_uuid),),
            )
            rows = cur.fetchall()
    if not rows:
        return None

    point_ids = [r["id"] for r in rows]
    ext_ids = [r["external_id"] for r in rows]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tr.ts, p.external_id, tr.value
                FROM timeseries_readings tr
                JOIN points p ON tr.point_id = p.id
                WHERE tr.point_id = ANY(%s::uuid[])
                  AND tr.ts >= %s AND tr.ts <= %s
                ORDER BY tr.ts
                """,
                (point_ids, start_ts, end_ts),
            )
            rows = cur.fetchall()

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df = df.pivot_table(index="ts", columns="external_id", values="value")
    df = df.reset_index()
    csv_cols = {ext: column_map.get(ext, ext) for ext in ext_ids}
    df = df.rename(columns=csv_cols)
    df["timestamp"] = pd.to_datetime(df["ts"])
    return df


def load_timeseries_for_equipment(
    site_id: str,
    equipment_id: str,
    start_ts: datetime,
    end_ts: datetime,
    column_map: dict[str, str],
) -> Optional[pd.DataFrame]:
    """
    Load timeseries_readings for one equipment into a DataFrame.
    Requires points.equipment_id and equipment table; falls back to site-level points.
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.external_id
                FROM points p
                JOIN equipment e ON p.equipment_id = e.id
                WHERE (p.site_id = %s OR p.site_id::text = %s)
                  AND e.name = %s
                """,
                (site_id, site_id, equipment_id),
            )
            rows = cur.fetchall()
    if not rows:
        return None

    point_ids = [r["id"] for r in rows]
    ext_ids = [r["external_id"] for r in rows]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tr.ts, p.external_id, tr.value
                FROM timeseries_readings tr
                JOIN points p ON tr.point_id = p.id
                WHERE tr.point_id = ANY(%s::uuid[])
                  AND tr.ts >= %s AND tr.ts <= %s
                """,
                (point_ids, start_ts, end_ts),
            )
            rows = cur.fetchall()

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df = df.pivot_table(index="ts", columns="external_id", values="value")
    df = df.reset_index()
    csv_cols = {ext: column_map.get(ext, ext) for ext in ext_ids}
    df = df.rename(columns=csv_cols)
    df["timestamp"] = pd.to_datetime(df["ts"])
    return df


def _point_lookup_for_equipment(
    site_id: str,
    equipment_id: str,
    column_map: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Build lookup keys -> point identity metadata for one equipment."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.external_id, p.fdd_input, p.bacnet_device_id, p.object_identifier, p.object_name
                FROM points p
                JOIN equipment e ON p.equipment_id = e.id
                WHERE (p.site_id = %s OR p.site_id::text = %s)
                  AND e.name = %s
                """,
                (site_id, site_id, equipment_id),
            )
            rows = cur.fetchall()
    inverse_column_map: dict[str, str] = {}
    for k, v in (column_map or {}).items():
        ks = str(k or "").strip()
        vs = str(v or "").strip()
        if ks and vs and vs not in inverse_column_map:
            inverse_column_map[vs] = ks

    lookup: dict[str, dict[str, str]] = {}
    for r in rows:
        external_id = (r.get("external_id") or "").strip()
        if not external_id:
            continue
        fdd_input = (r.get("fdd_input") or "").strip()
        mapped_key = (column_map.get(external_id) or external_id).strip()
        semantic_key = inverse_column_map.get(external_id, "").strip()
        meta = {
            "point_id": str(r.get("id") or "").strip(),
            "external_id": external_id,
            "bacnet_device_id": str(r.get("bacnet_device_id") or "").strip(),
            "object_identifier": str(r.get("object_identifier") or "").strip(),
            "object_name": str(r.get("object_name") or "").strip(),
        }
        for key in (external_id, fdd_input, mapped_key, semantic_key):
            if key and key not in lookup:
                lookup[key] = meta
    return lookup


def _point_lookup_for_site(
    site_id: str,
    column_map: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Build lookup keys -> point identity metadata for whole site fallback run."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.external_id, p.fdd_input, p.bacnet_device_id, p.object_identifier, p.object_name
                FROM points p
                WHERE (p.site_id = %s OR p.site_id::text = %s)
                """,
                (site_id, site_id),
            )
            rows = cur.fetchall()
    inverse_column_map: dict[str, str] = {}
    for k, v in (column_map or {}).items():
        ks = str(k or "").strip()
        vs = str(v or "").strip()
        if ks and vs and vs not in inverse_column_map:
            inverse_column_map[vs] = ks

    lookup: dict[str, dict[str, str]] = {}
    for r in rows:
        external_id = (r.get("external_id") or "").strip()
        if not external_id:
            continue
        fdd_input = (r.get("fdd_input") or "").strip()
        mapped_key = (column_map.get(external_id) or external_id).strip()
        semantic_key = inverse_column_map.get(external_id, "").strip()
        meta = {
            "point_id": str(r.get("id") or "").strip(),
            "external_id": external_id,
            "bacnet_device_id": str(r.get("bacnet_device_id") or "").strip(),
            "object_identifier": str(r.get("object_identifier") or "").strip(),
            "object_name": str(r.get("object_name") or "").strip(),
        }
        for key in (external_id, fdd_input, mapped_key, semantic_key):
            if key and key not in lookup:
                lookup[key] = meta
    return lookup


def _results_with_provenance(
    df: pd.DataFrame,
    site_id: str,
    equipment_id: str,
    rules: list[dict],
    point_lookup: dict[str, dict[str, str]],
    timestamp_col: str = "timestamp",
) -> list[FDDResult]:
    """
    Convert runner DataFrame rows to FDD results and attach point provenance.

    open-fdd's helper currently writes evidence=None; this keeps fault rows
    attributable by carrying point metadata derived from rule inputs.
    """
    results: list[FDDResult] = []
    if len(df) == 0:
        return results

    flag_cols = [c for c in df.columns if str(c).endswith("_flag")]
    ts_series = df[timestamp_col]
    if hasattr(ts_series.iloc[0], "to_pydatetime"):
        ts_series = ts_series.dt.tz_localize(None) if ts_series.dt.tz else ts_series

    rule_by_flag: dict[str, dict] = {}
    for rule in rules:
        if isinstance(rule, dict):
            flag = rule.get("flag")
            if isinstance(flag, str) and flag:
                rule_by_flag[flag] = rule

    for pos in range(len(df)):
        row = df.iloc[pos]
        t = ts_series.iloc[pos]
        if hasattr(t, "to_pydatetime"):
            t = t.to_pydatetime()
        for col in flag_cols:
            val = row.get(col, 0)
            if val is None or pd.isna(val):
                continue
            if not bool(val):
                continue
            rule = rule_by_flag.get(col, {})
            inputs = rule.get("inputs") if isinstance(rule, dict) else {}
            input_keys = list(inputs.keys()) if isinstance(inputs, dict) else []
            candidates = [
                point_lookup[k]
                for k in input_keys
                if isinstance(k, str) and k in point_lookup
            ]
            primary = candidates[0] if candidates else None
            evidence = {
                "rule_name": rule.get("name") if isinstance(rule, dict) else None,
                "fault_flag": col,
                "source": {
                    "input_keys": input_keys,
                    "point_candidates": candidates,
                },
            }
            if primary:
                evidence.update(primary)
                evidence["point"] = primary

            results.append(
                FDDResult(
                    ts=t,
                    site_id=site_id,
                    equipment_id=equipment_id,
                    fault_id=col,
                    flag_value=1,
                    evidence=evidence,
                )
            )
    return results


def _sync_fault_definitions_from_rules(rules: list) -> None:
    """
    Upsert fault_definitions from rule YAML so the matrix and definitions table
    stay in sync with rules_dir. Prunes definitions for rules no longer on disk.
    Called every FDD run after loading rules (hot reload).
    """
    if not rules:
        return
    try:
        current_fault_ids: list[str] = []
        with get_conn() as conn:
            with conn.cursor() as cur:
                for r in rules:
                    fault_id = r.get("flag") or f"{r.get('name', 'rule')}_flag"
                    current_fault_ids.append(fault_id)
                    name = r.get("name") or fault_id
                    description = r.get("description")
                    severity = str(r.get("severity", "warning"))
                    category = str(r.get("category", "general"))
                    eq_types = r.get("equipment_types") or r.get("equipment_type")
                    if isinstance(eq_types, list):
                        equipment_types = eq_types
                    elif eq_types is not None:
                        equipment_types = [eq_types]
                    else:
                        equipment_types = None
                    cur.execute(
                        """
                        INSERT INTO fault_definitions (fault_id, name, description, severity, category, equipment_types, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (fault_id) DO UPDATE SET
                          name = EXCLUDED.name,
                          description = EXCLUDED.description,
                          severity = EXCLUDED.severity,
                          category = EXCLUDED.category,
                          equipment_types = EXCLUDED.equipment_types,
                          updated_at = now()
                        """,
                        (
                            fault_id,
                            name,
                            description,
                            severity,
                            category,
                            equipment_types,
                        ),
                    )
                # Prune definitions for rules no longer in rules_dir (removes phantom rows)
                if current_fault_ids:
                    cur.execute(
                        "DELETE FROM fault_definitions WHERE fault_id != ALL(%s)",
                        (current_fault_ids,),
                    )
            conn.commit()
    except Exception:
        pass  # do not fail FDD run if sync fails


def sync_fault_definitions_from_rules_dir() -> None:
    """
    Load all rule YAML from configured rules_dir and sync fault_definitions (upsert + prune).
    Used by POST /rules/sync-definitions so the UI updates without waiting for the next FDD run.
    """
    from open_fdd.engine.runner import load_rules_from_dir

    settings = get_platform_settings()
    repo_root = Path(__file__).resolve().parent.parent.parent
    rules_path = Path(settings.rules_dir)
    if not rules_path.is_absolute():
        rules_path = repo_root / rules_path
    if not rules_path.exists():
        rules_path = repo_root / "stack" / "rules"
    all_rules = load_rules_from_dir(rules_path)
    _sync_fault_definitions_from_rules(all_rules)


def run_fdd_loop(
    site_id: Optional[str] = None,
    rules_dir: Optional[Path] = None,
    brick_ttl: Optional[Path] = None,
    lookback_days: Optional[int] = None,
    column_map_resolver: Optional["ColumnMapResolver"] = None,
) -> list[FDDResult]:
    """
    Run FDD on last N days of data, write fault_results to DB.
    Loads rules from YAML every run (rule edits apply immediately).
    Runs all rules (sensor + weather) against site-level data.

    ``column_map_resolver``: optional :class:`~open_fdd.engine.column_map_resolver.ColumnMapResolver`.
    Default is :class:`~openfdd_stack.platform.brick_ttl_resolver.BrickTtlColumnMapResolver` (Brick TTL),
    matching historical behavior. The Docker ``fdd-loop`` entrypoint does not pass this; it uses the default.
    """
    from open_fdd.engine.runner import RuleRunner, load_rules_from_dir
    from openfdd_stack.platform.brick_ttl_resolver import (
        BrickTtlColumnMapResolver,
        get_equipment_types_from_ttl,
    )

    settings = get_platform_settings()
    lookback = lookback_days if lookback_days is not None else settings.lookback_days

    # Rules: one place (stack/rules by default); fallback to stack/rules if configured path missing
    repo_root = Path(__file__).resolve().parent.parent.parent
    if rules_dir is not None:
        rules_path = Path(rules_dir)
    else:
        rules_path = Path(settings.rules_dir)
        if not rules_path.is_absolute():
            rules_path = repo_root / rules_path
    if not rules_path.exists():
        rules_path = repo_root / "stack" / "rules"

    # Use same TTL file as the rest of the platform (API, graph sync) so column_map matches the data model.
    if brick_ttl is not None:
        ttl_path = Path(brick_ttl) if isinstance(brick_ttl, str) else brick_ttl
        if not ttl_path.is_absolute():
            ttl_path = (repo_root / ttl_path).resolve()
    else:
        ttl_path = Path(get_ttl_path_resolved())
    # If config only has brick_ttl_dir (e.g. "config"), resolve to config/data_model.ttl so we have a file, not a dir.
    if ttl_path.exists() and ttl_path.is_dir():
        ttl_path = ttl_path / "data_model.ttl"
    if not ttl_path.exists():
        ttl_path = (repo_root / "config" / "data_model.ttl").resolve()

    resolver = (
        column_map_resolver
        if column_map_resolver is not None
        else BrickTtlColumnMapResolver()
    )
    column_map = resolver.build_column_map(ttl_path=ttl_path)
    equipment_types = (
        get_equipment_types_from_ttl(str(ttl_path)) if ttl_path.exists() else []
    )

    # Load rules every run (hot reload for rule tuning)
    all_rules = load_rules_from_dir(rules_path)
    _sync_fault_definitions_from_rules(all_rules)
    rules = [
        r
        for r in all_rules
        if not r.get("equipment_type")
        or any(et in equipment_types for et in r.get("equipment_type", []))
    ]
    runner = RuleRunner(rules=rules)
    strict = bool(getattr(settings, "fdd_strict_rules", False))

    end_ts = datetime.now(timezone.utc)
    start_ts = end_ts - timedelta(days=lookback)

    # Sites to run: one site or all
    with get_conn() as conn:
        with conn.cursor() as cur:
            if site_id:
                site_uuid = resolve_site_uuid(site_id, create_if_empty=False)
                if site_uuid is None:
                    return []
                cur.execute(
                    "SELECT id, name FROM sites WHERE id = %s",
                    (str(site_uuid),),
                )
            else:
                cur.execute("SELECT id, name FROM sites ORDER BY name")
            site_rows = cur.fetchall()

    all_results: list[FDDResult] = []
    sites_processed = 0
    try:
        for row in site_rows:
            sid = str(row["id"])
            site_name = row["name"] or sid
            # Run per-equipment when equipment has points so fault_state shows device name
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, name FROM equipment WHERE site_id = %s ORDER BY name",
                        (sid,),
                    )
                    equipment_rows = cur.fetchall()
            ran_equipment = False
            for eq_row in equipment_rows:
                eq_name = eq_row["name"] or str(eq_row["id"])
                df = load_timeseries_for_equipment(
                    sid, eq_name, start_ts, end_ts, column_map
                )
                if df is None or len(df) < 6:
                    continue
                ran_equipment = True
                res = runner.run(
                    df,
                    **_fdd_runner_run_kwargs(
                        settings, strict=strict, column_map=column_map
                    ),
                )
                point_lookup = _point_lookup_for_equipment(sid, eq_name, column_map)
                results = _results_with_provenance(
                    res,
                    sid,
                    eq_name,
                    rules,
                    point_lookup,
                    timestamp_col="timestamp",
                )
                all_results.extend(results)
            # Fallback: site-level run when no equipment had enough data
            if not ran_equipment:
                df = load_timeseries_for_site(sid, start_ts, end_ts, column_map)
                if df is not None and len(df) >= 6:
                    sites_processed += 1
                    res = runner.run(
                        df,
                        **_fdd_runner_run_kwargs(
                            settings, strict=strict, column_map=column_map
                        ),
                    )
                    point_lookup = _point_lookup_for_site(sid, column_map)
                    results = _results_with_provenance(
                        res,
                        sid,
                        site_name,
                        rules,
                        point_lookup=point_lookup,
                        timestamp_col="timestamp",
                    )
                    all_results.extend(results)
            elif ran_equipment:
                sites_processed += 1

        if all_results:
            _write_fault_results(all_results)
            try:
                from openfdd_stack.platform.fault_state_sync import (
                    sync_fault_state_from_results,
                )

                sync_fault_state_from_results(all_results)
            except Exception as e:
                # fault_results are already committed; state is best-effort for HA/UI
                _log.warning(
                    "fault_state sync failed after writing fault_results: %s",
                    e,
                    exc_info=_log.isEnabledFor(logging.DEBUG),
                )

        _write_fdd_run_log(
            run_ts=datetime.now(timezone.utc),
            status="ok",
            sites_processed=sites_processed,
            faults_written=len(all_results),
        )
    except Exception as e:
        _write_fdd_run_log(
            run_ts=datetime.now(timezone.utc),
            status="error",
            sites_processed=sites_processed,
            faults_written=0,
            error_message=str(e)[:500],
        )
        raise

    return all_results


def _write_fault_results(results: list[FDDResult]) -> None:
    """Bulk insert fault_results. Coerce site_id/equipment_id to str so UUID never reaches psycopg2."""
    rows = []
    for r in results:
        evidence = r.evidence
        if isinstance(evidence, (dict, list)):
            evidence = Json(evidence)
        rows.append(
            (
                r.ts,
                str(r.site_id),
                str(r.equipment_id),
                r.fault_id,
                r.flag_value,
                evidence,
            )
        )
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO fault_results (ts, site_id, equipment_id, fault_id, flag_value, evidence)
                VALUES %s
                """,
                rows,
                page_size=500,
            )
            conn.commit()


def _write_fdd_run_log(
    run_ts: datetime,
    status: str,
    sites_processed: int,
    faults_written: int,
    error_message: Optional[str] = None,
) -> None:
    """Record FDD run status for Grafana fault runner panel."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fdd_run_log (run_ts, status, sites_processed, faults_written, error_message)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (run_ts, status, sites_processed, faults_written, error_message),
            )
            conn.commit()
