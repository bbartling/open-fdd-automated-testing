"""Onboard API ingestion driver (read-only metadata + timeseries)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any
from uuid import UUID

import requests
from psycopg2.extras import execute_values

from openfdd_stack.platform.database import get_conn
from openfdd_stack.platform.site_resolver import resolve_site_uuid


def parse_iso_ts(value: str | None) -> datetime | None:
    """Parse ISO-8601 string and normalize to UTC."""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_building_filters(raw: str | None) -> list[str]:
    """Parse csv/json building selectors (IDs and/or names)."""
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("onboard_building_ids JSON must be an array")
        return [str(v).strip() for v in data if str(v).strip()]
    return [v.strip() for v in text.split(",") if v.strip()]


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _site_key_for_building(
    building: dict[str, Any], strategy: str, default_site_id: str
) -> str:
    if strategy == "default":
        return default_site_id
    bldg_id = building.get("id")
    if bldg_id is None:
        return default_site_id
    return f"onboard-{bldg_id}"


@dataclass
class OnboardClient:
    base_url: str
    api_key: str
    timeout_sec: int = 30

    def _headers(self) -> dict[str, str]:
        return {"X-OB-Api": self.api_key, "Content-Type": "application/json"}

    def _get(self, path: str) -> Any:
        resp = requests.get(
            f"{self.base_url.rstrip('/')}{path}",
            headers=self._headers(),
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        resp = requests.post(
            f"{self.base_url.rstrip('/')}{path}",
            headers=self._headers(),
            json=body,
            timeout=self.timeout_sec,
        )
        resp.raise_for_status()
        return resp.json()

    def get_buildings(self, building_filters: list[str]) -> list[dict[str, Any]]:
        data = self._get("/buildings")
        buildings = data if isinstance(data, list) else []
        if not building_filters:
            return buildings

        by_id = {str(b.get("id")): b for b in buildings if b.get("id") is not None}
        by_name_ci = {
            str(b.get("name")).strip().casefold(): b
            for b in buildings
            if str(b.get("name") or "").strip()
        }
        out: list[dict[str, Any]] = []
        seen: set[int] = set()
        for token in building_filters:
            key = str(token).strip()
            if not key:
                continue
            match = by_id.get(key)
            if match is None:
                match = by_name_ci.get(key.casefold())
            if match is None:
                continue
            bldg_id = int(match["id"])
            if bldg_id in seen:
                continue
            seen.add(bldg_id)
            out.append(match)
        return out

    def get_points(self, building_id: int) -> list[dict[str, Any]]:
        data = self._get(f"/buildings/{int(building_id)}/points")
        return data if isinstance(data, list) else []

    def query_v2(
        self, start: datetime, end: datetime, point_ids: list[int]
    ) -> list[dict[str, Any]]:
        body = {
            "start": start.astimezone(timezone.utc).isoformat(),
            "end": end.astimezone(timezone.utc).isoformat(),
            "point_ids": point_ids,
        }
        data = self._post("/query-v2", body)
        return data if isinstance(data, list) else []


def _load_state(cur, state_key: str) -> dict[str, Any]:
    cur.execute(
        "SELECT state_key, backfill_done, last_poll_end FROM onboard_ingest_state WHERE state_key=%s",
        (state_key,),
    )
    row = cur.fetchone()
    if row:
        return row
    return {"state_key": state_key, "backfill_done": False, "last_poll_end": None}


def _save_state(
    cur, state_key: str, backfill_done: bool, last_poll_end: datetime | None
) -> None:
    cur.execute(
        """
        INSERT INTO onboard_ingest_state (state_key, backfill_done, last_poll_end, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (state_key) DO UPDATE SET
            backfill_done = EXCLUDED.backfill_done,
            last_poll_end = EXCLUDED.last_poll_end,
            updated_at = now()
        """,
        (state_key, backfill_done, last_poll_end),
    )


def _point_external_id(point: dict[str, Any]) -> str:
    topic = str(point.get("topic") or "").strip()
    if topic:
        return topic
    return f"onboard:{point.get('building_id')}:{point.get('id')}"


def _point_description(point: dict[str, Any]) -> str:
    fields = [
        str(point.get("type") or "").strip(),
        str(point.get("name") or "").strip(),
        str(point.get("device") or "").strip(),
        str(point.get("objectId") or "").strip(),
    ]
    return " | ".join([v for v in fields if v])


def _upsert_points_for_building(
    cur,
    site_id: UUID,
    points: list[dict[str, Any]],
    create_points: bool,
) -> tuple[dict[int, UUID], int]:
    point_uuid_by_onboard_id: dict[int, UUID] = {}
    points_created = 0

    if create_points:
        for p in points:
            point_id = p.get("id")
            if point_id is None:
                continue
            ext = _point_external_id(p)
            unit = str(p.get("tagged_units") or p.get("units") or "").strip() or None
            description = _point_description(p) or None
            cur.execute(
                """
                INSERT INTO points (site_id, external_id, unit, description)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (site_id, external_id) DO UPDATE SET
                    unit = EXCLUDED.unit,
                    description = EXCLUDED.description
                RETURNING id
                """,
                (site_id, ext, unit, description),
            )
            row = cur.fetchone()
            if row:
                point_uuid_by_onboard_id[int(point_id)] = row["id"]
                points_created += 1
    else:
        ext_ids = [_point_external_id(p) for p in points if p.get("id") is not None]
        if ext_ids:
            cur.execute(
                "SELECT id, external_id FROM points WHERE site_id=%s AND external_id = ANY(%s)",
                (site_id, ext_ids),
            )
            existing = {r["external_id"]: r["id"] for r in cur.fetchall() or []}
            for p in points:
                point_id = p.get("id")
                if point_id is None:
                    continue
                maybe_uuid = existing.get(_point_external_id(p))
                if maybe_uuid:
                    point_uuid_by_onboard_id[int(point_id)] = maybe_uuid

    return point_uuid_by_onboard_id, points_created


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


def _extract_rows_from_query_result(
    point_uuid_by_onboard_id: dict[int, UUID],
    site_id: UUID,
    result_rows: list[dict[str, Any]],
) -> list[tuple]:
    out: list[tuple] = []
    site_text = str(site_id)
    for item in result_rows:
        onboard_point_id = item.get("point_id")
        if onboard_point_id is None:
            continue
        point_uuid = point_uuid_by_onboard_id.get(int(onboard_point_id))
        if point_uuid is None:
            continue
        values = item.get("values") or []
        for row in values:
            if not isinstance(row, list) or len(row) < 2:
                continue
            ts_raw = row[0]
            ts = parse_iso_ts(str(ts_raw))
            if ts is None:
                continue
            # query-v2 commonly returns [time, raw, converted-unit]
            value_raw = row[-1] if len(row) >= 3 else row[1]
            val = _as_float(value_raw)
            if val is None:
                continue
            out.append((ts, site_text, point_uuid, val, None))
    return out


def _window_chunks(
    start: datetime, end: datetime, step_minutes: int = 180
) -> list[tuple[datetime, datetime]]:
    if start >= end:
        return []
    chunks: list[tuple[datetime, datetime]] = []
    cur = start
    step = timedelta(minutes=max(1, step_minutes))
    while cur < end:
        nxt = min(cur + step, end)
        chunks.append((cur, nxt))
        cur = nxt
    return chunks


def run_onboard_ingest_once(
    log: logging.Logger,
    *,
    base_url: str,
    api_key: str,
    building_filters: list[str],
    backfill_start: datetime | None,
    scrape_interval_min: int,
    backfill_end: datetime | None = None,
    site_id_strategy: str,
    create_points: bool,
    default_site_id: str = "default",
) -> dict[str, int]:
    """Run one ingestion cycle across selected Onboard buildings."""
    client = OnboardClient(base_url=base_url, api_key=api_key)
    summary = {"rows_inserted": 0, "points_seen": 0, "points_upserted": 0, "buildings": 0}
    buildings = client.get_buildings(building_filters)
    summary["buildings"] = len(buildings)
    now_utc = datetime.now(timezone.utc)

    with get_conn() as conn:
        for building in buildings:
            try:
                with conn.cursor() as cur:
                    building_id = int(building["id"])
                    state_key = f"onboard:{building_id}"
                    state = _load_state(cur, state_key)
                    points = client.get_points(building_id)
                    summary["points_seen"] += len(points)

                    site_key = _site_key_for_building(building, site_id_strategy, default_site_id)
                    site_uuid = resolve_site_uuid(site_key, create_if_empty=True)
                    if site_uuid is None:
                        log.warning(
                            "Skipping building %s; could not resolve site id", building_id
                        )
                        continue

                    point_map, created_count = _upsert_points_for_building(
                        cur, site_uuid, points, create_points
                    )
                    summary["points_upserted"] += created_count
                    if not point_map:
                        log.info(
                            "No point mappings resolved for building %s; skipping query",
                            building_id,
                        )
                        continue

                    point_ids = list(point_map.keys())
                    batches = [point_ids[i : i + 200] for i in range(0, len(point_ids), 200)]
                    total_rows_this_building = 0

                    last_poll_end = state.get("last_poll_end")
                    window_min = max(1, int(scrape_interval_min))
                    is_first_backfill_run = backfill_start is not None and not isinstance(
                        last_poll_end, datetime
                    )
                    backfill_window_min = max(180, window_min)
                    if backfill_start is not None:
                        if isinstance(last_poll_end, datetime):
                            inc_start = max(last_poll_end, backfill_start)
                        else:
                            inc_start = backfill_start
                    else:
                        if isinstance(last_poll_end, datetime):
                            inc_start = last_poll_end
                        else:
                            inc_start = now_utc - timedelta(minutes=window_min)

                    inc_end = now_utc
                    if backfill_end is not None:
                        inc_end = min(inc_end, backfill_end)

                    if inc_start < inc_end:
                        step_min = backfill_window_min if is_first_backfill_run else window_min
                        for win_start, win_end in _window_chunks(
                            inc_start, inc_end, step_minutes=step_min
                        ):
                            for batch in batches:
                                q = client.query_v2(win_start, win_end, batch)
                                rows = _extract_rows_from_query_result(point_map, site_uuid, q)
                                total_rows_this_building += _insert_timeseries_rows(cur, rows)

                    if backfill_start is None:
                        backfill_done = bool(state.get("backfill_done"))
                    else:
                        target_end = backfill_end if backfill_end is not None else now_utc
                        backfill_done = inc_end >= target_end
                    _save_state(
                        cur,
                        state_key,
                        backfill_done,
                        inc_end,
                    )
                    summary["rows_inserted"] += total_rows_this_building
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return summary
