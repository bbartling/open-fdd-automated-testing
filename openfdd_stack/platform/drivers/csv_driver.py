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
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
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
    digest = hashlib.sha1(  # noqa: S324 - deterministic non-crypto state key
        f"{source.path}|{source.site_id}".encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]
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


def validate_csv_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Validate a CSV dataframe and report model-style errors."""
    errors: list[str] = []
    warnings: list[str] = []
    if df.empty:
        errors.append("CSV has no rows.")
        return {
            "errors": errors,
            "warnings": warnings,
            "rows_total": 0,
            "rows_with_valid_timestamp": 0,
            "timestamp_column": None,
            "metric_columns": [],
        }
    try:
        ts_col = _infer_timestamp_column([str(c) for c in df.columns])
    except ValueError:
        errors.append("Missing timestamp column. Expected 'timestamp' or similar name.")
        return {
            "errors": errors,
            "warnings": warnings,
            "rows_total": len(df.index),
            "rows_with_valid_timestamp": 0,
            "timestamp_column": None,
            "metric_columns": [],
        }

    ts_series = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    valid_ts = int(ts_series.notna().sum())
    if valid_ts == 0:
        errors.append(f"Timestamp column '{ts_col}' has no parseable values.")

    metric_cols = [c for c in df.columns if c != ts_col]
    if not metric_cols:
        errors.append("CSV has no metric columns besides timestamp.")
    else:
        numeric_cols = []
        non_numeric_cols = []
        for col in metric_cols:
            vals = pd.to_numeric(df[col], errors="coerce")
            if int(vals.notna().sum()) > 0:
                numeric_cols.append(str(col))
            else:
                non_numeric_cols.append(str(col))
        if not numeric_cols:
            errors.append("No numeric metric columns found.")
        if non_numeric_cols:
            warnings.append(
                "Non-numeric columns (ignored for ingest): " + ", ".join(non_numeric_cols)
            )

    return {
        "errors": errors,
        "warnings": warnings,
        "rows_total": len(df.index),
        "rows_with_valid_timestamp": valid_ts,
        "timestamp_column": ts_col,
        "metric_columns": [str(c) for c in metric_cols],
    }


def _build_rows_from_dataframe(
    *,
    df: pd.DataFrame,
    metric_cols: list[Any],
    point_ids: dict[str, Any],
    site_id_text: str,
) -> list[tuple]:
    if df.empty or not metric_cols:
        return []
    melted = df[["__ts", *metric_cols]].melt(
        id_vars=["__ts"],
        value_vars=metric_cols,
        var_name="metric",
        value_name="value",
    )
    melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
    melted = melted.dropna(subset=["__ts", "value"]).copy()
    if melted.empty:
        return []
    melted["point_id"] = melted["metric"].map(lambda c: point_ids.get(str(c)))
    melted = melted.dropna(subset=["point_id"]).copy()
    if melted.empty:
        return []

    ts_values = melted["__ts"].tolist()
    norm_ts = [t.to_pydatetime() if hasattr(t, "to_pydatetime") else t for t in ts_values]
    return list(
        zip(
            norm_ts,
            [site_id_text] * len(melted.index),
            melted["point_id"].tolist(),
            melted["value"].astype(float).tolist(),
            [None] * len(melted.index),
        )
    )


def _resolve_or_create_points(
    cur,
    *,
    site_uuid,
    metric_cols: list[Any],
    source_name: str,
    create_points: bool,
    site_id_text: str,
    log: logging.Logger | None = None,
) -> tuple[dict[str, Any], int]:
    point_ids: dict[str, Any] = {}
    points_upserted = 0
    if create_points:
        for col in metric_cols:
            ext_id = f"csv:{source_name}:{str(col).strip()}"
            cur.execute(
                """
                INSERT INTO points (site_id, external_id, description, polling)
                VALUES (%s, %s, %s, FALSE)
                ON CONFLICT (site_id, external_id) DO UPDATE SET
                    description = EXCLUDED.description
                RETURNING id
                """,
                (site_uuid, ext_id, f"CSV source {source_name} column {col}"),
            )
            row = cur.fetchone()
            if row:
                point_ids[str(col)] = row["id"]
                points_upserted += 1
    else:
        ext_ids = [f"csv:{source_name}:{str(col).strip()}" for col in metric_cols]
        cur.execute(
            "SELECT id, external_id FROM points WHERE site_id=%s AND external_id = ANY(%s)",
            (site_uuid, ext_ids),
        )
        existing = {r["external_id"]: r["id"] for r in cur.fetchall() or []}
        for col in metric_cols:
            point_ids[str(col)] = existing.get(f"csv:{source_name}:{str(col).strip()}")
        if log:
            unmapped_cols = [str(col) for col in metric_cols if point_ids.get(str(col)) is None]
            if unmapped_cols:
                log.info(
                    "CSV source %s site=%s has no mapped points for columns: %s",
                    source_name,
                    site_id_text,
                    ", ".join(unmapped_cols),
                )
    return point_ids, points_upserted


def ingest_csv_dataframe(
    *,
    site_id: str,
    df: pd.DataFrame,
    source_name: str,
    create_points: bool = True,
) -> dict[str, int]:
    """Ingest a validated CSV dataframe into points/timeseries."""
    site_uuid = resolve_site_uuid(site_id, create_if_empty=True)
    if site_uuid is None:
        raise ValueError(f"Could not resolve site id '{site_id}'")
    ts_col = _infer_timestamp_column([str(c) for c in df.columns])
    df = df.copy()
    df["__ts"] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    df = df[df["__ts"].notna()].copy()
    if df.empty:
        return {"rows_inserted": 0, "points_upserted": 0}

    metric_cols = [c for c in df.columns if c not in (ts_col, "__ts")]
    site_id_text = str(site_uuid)
    with get_conn() as conn:
        with conn.cursor() as cur:
            point_ids, points_upserted = _resolve_or_create_points(
                cur,
                site_uuid=site_uuid,
                metric_cols=metric_cols,
                source_name=source_name,
                create_points=create_points,
                site_id_text=site_id_text,
            )

            rows = _build_rows_from_dataframe(
                df=df,
                metric_cols=metric_cols,
                point_ids=point_ids,
                site_id_text=site_id_text,
            )
            inserted = _insert_timeseries_rows(cur, rows)
            conn.commit()
    return {"rows_inserted": inserted, "points_upserted": points_upserted}


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

            try:
                ts_col = _infer_timestamp_column([str(c) for c in df.columns])
                df["__ts"] = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
                df = df[df["__ts"].notna()].copy()
                if df.empty:
                    continue
            except (ValueError, TypeError) as e:
                log.warning("Skipping malformed CSV %s: %s", csv_path, e)
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
                    point_ids, points_upserted = _resolve_or_create_points(
                        cur,
                        site_uuid=site_uuid,
                        metric_cols=metric_cols,
                        source_name=csv_path.stem,
                        create_points=create_points,
                        site_id_text=site_id_text,
                        log=log,
                    )

                    rows = _build_rows_from_dataframe(
                        df=df,
                        metric_cols=metric_cols,
                        point_ids=point_ids,
                        site_id_text=site_id_text,
                    )

                    inserted = _insert_timeseries_rows(cur, rows)
                    last_ts = df["__ts"].max().to_pydatetime()
                    _save_state(cur, state_key, last_ts)
                    conn.commit()
                    summary["sources"] += 1
                    summary["rows_inserted"] += inserted
                    if create_points:
                        summary["points_upserted"] += points_upserted
            except Exception as e:
                conn.rollback()
                log.exception(
                    "CSV ingest failed for source=%s state_key=%s site_uuid=%s: %s",
                    csv_path.stem,
                    state_key,
                    site_uuid,
                    e,
                )
                continue

    return summary
