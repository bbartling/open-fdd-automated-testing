"""CSV ingestion driver (read-only local files -> points/timeseries)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from psycopg2.extras import execute_values

from openfdd_stack.platform.database import get_conn
from openfdd_stack.platform.site_resolver import resolve_site_uuid


@dataclass(frozen=True)
class CsvSource:
    path: str
    site_id: str


def parse_iso_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_csv_sources(raw: str | None) -> list[CsvSource]:
    """Parse CSV source config as JSON list of {'path','site_id'}."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("csv_sources must be a JSON array")
    out: list[CsvSource] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        site_id = str(item.get("site_id") or "").strip()
        if not path or not site_id:
            continue
        out.append(CsvSource(path=path, site_id=site_id))
    return out


def _source_key(source: CsvSource) -> str:
    digest = hashlib.sha1(f"{source.path}|{source.site_id}".encode("utf-8")).hexdigest()[:12]
    return f"csv:{digest}"


def _load_state(cur, state_key: str) -> dict[str, Any]:
    cur.execute(
        "SELECT state_key, last_ts FROM csv_ingest_state WHERE state_key=%s",
        (state_key,),
    )
    row = cur.fetchone()
    return row or {"state_key": state_key, "last_ts": None}


def _save_state(cur, state_key: str, last_ts: datetime | None) -> None:
    cur.execute(
        """
        INSERT INTO csv_ingest_state (state_key, last_ts, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (state_key) DO UPDATE SET
            last_ts = EXCLUDED.last_ts,
            updated_at = now()
        """,
        (state_key, last_ts),
    )


def _infer_timestamp_column(columns: list[str]) -> str:
    for col in columns:
        if str(col).strip().casefold() == "timestamp":
            return col
    for col in columns:
        if "timestamp" in str(col).strip().casefold():
            return col
    raise ValueError("CSV missing a timestamp column")


def _insert_timeseries_rows(cur, rows: list[tuple]) -> int:
    if not rows:
        return 0
    execute_values(
        cur,
        """
        INSERT INTO timeseries_readings (ts, site_id, point_id, value, job_id)
        VALUES %s
        """,
        rows,
        page_size=2000,
    )
    return len(rows)


def run_csv_ingest_once(
    log: logging.Logger,
    *,
    sources: list[CsvSource],
    backfill_start: datetime | None,
    backfill_end: datetime | None,
    create_points: bool,
) -> dict[str, int]:
    summary = {"sources": 0, "rows_inserted": 0, "points_upserted": 0}
    if not sources:
        return summary

    with get_conn() as conn:
        for source in sources:
            csv_path = Path(source.path)
            if not csv_path.is_absolute():
                csv_path = (Path.cwd() / csv_path).resolve()
            if not csv_path.exists():
                log.warning("CSV source missing; skipping: %s", csv_path)
                continue

            site_uuid = resolve_site_uuid(source.site_id, create_if_empty=True)
            if site_uuid is None:
                log.warning("Could not resolve site id '%s'; skipping %s", source.site_id, source.path)
                continue

            try:
                df = pd.read_csv(csv_path)
            except Exception as e:
                log.warning("Failed to read CSV %s: %s", csv_path, e)
                continue
            if df.empty:
                continue

            ts_col = _infer_timestamp_column([str(c) for c in df.columns])
            df["__ts"] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
            df = df[df["__ts"].notna()].copy()
            if df.empty:
                continue

            state_key = _source_key(source)
            try:
                with conn.cursor() as cur:
                    state = _load_state(cur, state_key)
                    min_ts = state.get("last_ts")
                    if backfill_start is not None:
                        min_ts = max(backfill_start, min_ts) if isinstance(min_ts, datetime) else backfill_start
                    if min_ts is not None:
                        df = df[df["__ts"] > min_ts]
                    if backfill_end is not None:
                        df = df[df["__ts"] <= backfill_end]
                    if df.empty:
                        _save_state(cur, state_key, state.get("last_ts"))
                        conn.commit()
                        continue

                    metric_cols = [c for c in df.columns if c not in (ts_col, "__ts")]
                    site_id_text = str(site_uuid)
                    point_ids: dict[str, Any] = {}
                    points_upserted = 0
                    if create_points:
                        for col in metric_cols:
                            ext_id = f"csv:{csv_path.stem}:{str(col).strip()}"
                            cur.execute(
                                """
                                INSERT INTO points (site_id, external_id, description)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (site_id, external_id) DO UPDATE SET
                                    description = EXCLUDED.description
                                RETURNING id
                                """,
                                (site_uuid, ext_id, f"CSV source {csv_path.name} column {col}"),
                            )
                            row = cur.fetchone()
                            if row:
                                point_ids[str(col)] = row["id"]
                                points_upserted += 1
                    else:
                        ext_ids = [f"csv:{csv_path.stem}:{str(col).strip()}" for col in metric_cols]
                        cur.execute(
                            "SELECT id, external_id FROM points WHERE site_id=%s AND external_id = ANY(%s)",
                            (site_uuid, ext_ids),
                        )
                        existing = {r["external_id"]: r["id"] for r in cur.fetchall() or []}
                        for col in metric_cols:
                            point_ids[str(col)] = existing.get(
                                f"csv:{csv_path.stem}:{str(col).strip()}"
                            )

                    rows: list[tuple] = []
                    for _, item in df.iterrows():
                        ts = item["__ts"]
                        if hasattr(ts, "to_pydatetime"):
                            ts = ts.to_pydatetime()
                        for col in metric_cols:
                            point_id = point_ids.get(str(col))
                            if point_id is None:
                                continue
                            try:
                                val = float(item[col])
                            except (TypeError, ValueError):
                                continue
                            rows.append((ts, site_id_text, point_id, val, None))

                    inserted = _insert_timeseries_rows(cur, rows)
                    last_ts = max(df["__ts"]).to_pydatetime()
                    _save_state(cur, state_key, last_ts)
                    conn.commit()
                    summary["sources"] += 1
                    summary["rows_inserted"] += inserted
                    if create_points:
                        summary["points_upserted"] += points_upserted
            except Exception:
                conn.rollback()
                raise

    return summary
