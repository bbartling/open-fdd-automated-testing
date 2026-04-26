#!/usr/bin/env python3
"""
Run FDD rule loop on a schedule (default: every 3 hours, 3-day lookback).

Each run: if Open-Meteo is enabled (graph/config), fetches weather for the same
lookback window so rules have fresh data; then loads rules from YAML, pulls last N days
of site data into pandas, runs all rules (sensor + weather), writes fault_results.
YAML edits take effect on the next run; no restart required.

Weather: Fetched at each FDD run (same interval as rule_interval_hours). To avoid
redundant fetches, do not run the standalone weather scraper (run_weather_fetch.py --loop)
when using this loop; use one or the other.

Usage:
  python -m openfdd_stack.platform.drivers.run_rule_loop         # one-shot (run now, exit)
  python -m openfdd_stack.platform.drivers.run_rule_loop --loop  # scheduled loop (checks trigger file every 60s)
  python -m openfdd_stack.platform.drivers.run_trigger_fdd       # touch trigger file → loop runs now + resets timer

When --loop: touch config/.run_fdd_now (or OFDD_FDD_TRIGGER_FILE) to run immediately
and restart the interval. Useful after rule edits.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openfdd_stack.platform.config import get_platform_settings
from openfdd_stack.platform.config import set_config_overlay
from openfdd_stack.platform.drivers.onboard import parse_iso_ts
from openfdd_stack.platform.graph_model import get_config_from_graph, load_from_file
from openfdd_stack.platform.loop import run_fdd_loop
from openfdd_stack.platform.site_resolver import resolve_site_uuid

TRIGGER_POLL_SEC = 60  # check for trigger file every N seconds
BACKFILL_STATE_KEY = "fdd:global"


def setup_logging(verbose: bool = False) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S")


def _runtime_loop_settings() -> tuple[float, int, int, str | None]:
    """Read current runtime config for one loop cycle.

    Returns: (interval_hours, sleep_seconds, lookback_days, trigger_path).
    Values come from get_platform_settings() so graph/config updates are used
    without restarting the fdd-loop container.
    """
    # fdd-loop is a separate process from the API, so refresh graph-backed config
    # from the shared TTL before reading settings.
    log = logging.getLogger("open_fdd.fdd_loop")
    try:
        load_from_file()
        set_config_overlay(get_config_from_graph())
    except Exception as e:
        # Keep loop running with env defaults if TTL parse/read fails.
        log.error("Failed to refresh graph-backed runtime config; continuing: %s", e, exc_info=True)

    settings = get_platform_settings()
    interval_hours = float(getattr(settings, "rule_interval_hours", 3.0))
    sleep_sec = max(60, int(interval_hours * 3600))  # avoid tight loop
    lookback_days = int(getattr(settings, "lookback_days", 3))
    trigger_path = getattr(settings, "fdd_trigger_file", None) or "config/.run_fdd_now"
    return interval_hours, sleep_sec, lookback_days, trigger_path


def _load_backfill_state(state_key: str) -> dict:
    from openfdd_stack.platform.database import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT state_key, last_window_end, cfg_start, cfg_end
                FROM fdd_backfill_state
                WHERE state_key = %s
                """,
                (state_key,),
            )
            row = cur.fetchone()
    return row or {"state_key": state_key, "last_window_end": None, "cfg_start": None, "cfg_end": None}


def _save_backfill_state(
    state_key: str, last_window_end: datetime | None, cfg_start: str | None, cfg_end: str | None
) -> None:
    from openfdd_stack.platform.database import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fdd_backfill_state (state_key, last_window_end, cfg_start, cfg_end, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (state_key) DO UPDATE SET
                    last_window_end = EXCLUDED.last_window_end,
                    cfg_start = EXCLUDED.cfg_start,
                    cfg_end = EXCLUDED.cfg_end,
                    updated_at = now()
                """,
                (state_key, last_window_end, cfg_start, cfg_end),
            )
            conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="FDD rule loop: periodic runs with hot-reload (default 3h interval, 3-day lookback)"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run every N hours (OFDD_RULE_INTERVAL_HOURS)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("open_fdd.fdd_loop")

    def _run(lookback_days: int) -> int:
        settings = get_platform_settings()
        # Run Open-Meteo fetch when FDD runs so weather is fresh for rules (same interval, graph-driven).
        if getattr(settings, "open_meteo_enabled", True):
            try:
                from openfdd_stack.platform.drivers.open_meteo import run_open_meteo_fetch

                site_uuid = resolve_site_uuid(
                    getattr(settings, "open_meteo_site_id", "default") or "default"
                )
                if site_uuid:
                    # Use 1-day lookback when run from FDD (every rule_interval_hours);
                    # fetching 3 days every 3h is unnecessary and heavy on the API.
                    weather_days_back = 1
                    run_open_meteo_fetch(
                        site_uuid,
                        getattr(settings, "open_meteo_latitude", 41.88),
                        getattr(settings, "open_meteo_longitude", -87.63),
                        days_back=weather_days_back,
                        timezone=getattr(
                            settings, "open_meteo_timezone", "America/Chicago"
                        ),
                    )
                    log.info("Open-Meteo fetch OK before FDD run (1-day window)")
            except Exception as we:
                log.warning(
                    "Open-Meteo fetch before FDD run failed (continuing): %s", we
                )

        log.info(
            "FDD run: lookback=%d days, rules reload from YAML",
            lookback_days,
        )
        try:
            results = run_fdd_loop(lookback_days=lookback_days)
            log.info("FDD run OK: %d fault samples written", len(results))
            return 0
        except Exception as e:
            log.exception("FDD run failed: %s", e)
            # Hint when DB is unavailable
            try:
                import psycopg2

                if isinstance(e, psycopg2.OperationalError):
                    log.info(
                        "Tip: rule loop needs TimescaleDB. Start platform: ./scripts/bootstrap.sh or docker compose -f platform/docker-compose.yml up -d"
                    )
            except ImportError:
                pass
            return 1

    def _run_window(start_ts: datetime, end_ts: datetime) -> int:
        log.info("FDD backfill window: %s -> %s", start_ts.isoformat(), end_ts.isoformat())
        try:
            results = run_fdd_loop(start_ts=start_ts, end_ts=end_ts)
            log.info("FDD backfill window OK: %d fault samples written", len(results))
            return 0
        except Exception as e:
            log.exception("FDD backfill window failed: %s", e)
            return 1

    def _run_backfill_pass() -> tuple[int, bool]:
        settings = get_platform_settings()
        enabled = bool(getattr(settings, "fdd_backfill_enabled", False))
        if not enabled:
            return 0, False
        cfg_start_raw = getattr(settings, "fdd_backfill_start", None)
        cfg_end_raw = getattr(settings, "fdd_backfill_end", None)
        cfg_start = parse_iso_ts(cfg_start_raw)
        cfg_end = parse_iso_ts(cfg_end_raw)
        if cfg_start is None:
            log.warning("fdd_backfill_enabled=true but fdd_backfill_start is empty; skipping.")
            return 0, False
        if cfg_end is not None and cfg_end <= cfg_start:
            log.warning("Invalid FDD backfill bounds: end <= start; skipping.")
            return 0, False
        step_hours = max(1, int(getattr(settings, "fdd_backfill_step_hours", 3)))

        state = _load_backfill_state(BACKFILL_STATE_KEY)
        cfg_start_key = cfg_start.isoformat()
        cfg_end_key = cfg_end.isoformat() if cfg_end is not None else None
        if state.get("cfg_start") != cfg_start_key or state.get("cfg_end") != cfg_end_key:
            cursor = cfg_start
        else:
            cursor = state.get("last_window_end") or cfg_start

        target_end = cfg_end or datetime.now(timezone.utc)
        if cursor >= target_end:
            log.info("FDD backfill already complete up to %s", target_end.isoformat())
            return 0, False

        windows_run = 0
        while cursor < target_end:
            win_end = min(cursor + timedelta(hours=step_hours), target_end)
            rc = _run_window(cursor, win_end)
            if rc != 0:
                return rc, True
            windows_run += 1
            cursor = win_end
            _save_backfill_state(
                BACKFILL_STATE_KEY,
                cursor,
                cfg_start_key,
                cfg_end_key,
            )
        log.info("FDD backfill pass complete: %d windows", windows_run)
        return 0, windows_run > 0

    if args.loop:
        interval_hours, sleep_sec, lookback_days, trigger_path = _runtime_loop_settings()
        log.info(
            "FDD loop started: every %.2f h (%d s), lookback %d days (touch %s to run now)",
            interval_hours,
            sleep_sec,
            lookback_days,
            trigger_path or "config/.run_fdd_now",
        )

        while True:
            # Reload runtime config each cycle so GET/PUT /config changes apply without restart.
            interval_hours, sleep_sec, lookback_days, trigger_path = _runtime_loop_settings()
            rc, backfill_ran = _run_backfill_pass()
            if rc != 0:
                log.error("FDD backfill pass failed with rc=%s; continuing with routine lookback run", rc)
                _run(lookback_days=lookback_days)
            elif backfill_ran:
                log.info("Backfill windows ran this cycle; skipping routine lookback run to avoid overlap")
            else:
                _run(lookback_days=lookback_days)
            elapsed = 0
            while elapsed < sleep_sec:
                nap = min(TRIGGER_POLL_SEC, sleep_sec - elapsed)
                time.sleep(nap)
                elapsed += nap
                if trigger_path:
                    p = Path(trigger_path)
                    if not p.is_absolute():
                        p = Path.cwd() / p
                    if p.exists():
                        try:
                            p.unlink()
                        except OSError as e:
                            log.warning(
                                "Trigger file detected but could not remove %s (%s). "
                                "Loop will re-trigger every 60s until file is gone. "
                                "If running in Docker, ensure config volume is writable.",
                                p,
                                e,
                            )
                        log.info("Trigger file detected → running now, timer reset")
                        rc, backfill_ran = _run_backfill_pass()
                        if rc != 0:
                            log.error(
                                "Triggered FDD backfill pass failed with rc=%s; continuing with routine lookback run",
                                rc,
                            )
                            _run(lookback_days=lookback_days)
                        elif backfill_ran:
                            log.info("Triggered backfill windows ran; skipping routine lookback run")
                        else:
                            _run(lookback_days=lookback_days)
                        elapsed = 0  # reset timer
            log.info("Next run in %.2f h", interval_hours)
    else:
        _, _, lookback_days, _ = _runtime_loop_settings()
        rc, _ = _run_backfill_pass()
        if rc != 0:
            return rc
        return _run(lookback_days=lookback_days)


if __name__ == "__main__":
    sys.exit(main())
