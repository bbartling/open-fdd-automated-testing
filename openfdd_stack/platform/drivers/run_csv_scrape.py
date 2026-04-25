#!/usr/bin/env python3
"""Run CSV scrape: local CSV files -> TimescaleDB."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request

from openfdd_stack.platform.config import get_platform_settings
from openfdd_stack.platform.drivers.csv_driver import (
    parse_csv_sources,
    parse_iso_ts,
    run_csv_ingest_once,
)

_CONFIG_CACHE: dict[str, object] = {"ts": 0.0, "cfg": None}


def _get_api_url() -> str:
    return os.getenv("OFDD_API_URL", "http://localhost:8000").rstrip("/")


def _fetch_platform_config(log: logging.Logger) -> dict | None:
    url = f"{_get_api_url()}/config"
    req = urllib.request.Request(url)
    api_key = os.environ.get("OFDD_API_KEY", "").strip()
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        log.warning("GET /config failed: %s (%s).", e.code, url)
        return None
    except Exception as e:
        log.warning("Could not fetch platform config from %s (%s).", url, e)
        return None


def _fetch_platform_config_cached(log: logging.Logger, ttl_sec: int = 30) -> dict | None:
    now = time.time()
    ts = float(_CONFIG_CACHE["ts"])
    if now - ts < ttl_sec:
        return _CONFIG_CACHE["cfg"]  # type: ignore[return-value]
    cfg = _fetch_platform_config(log)
    if cfg is not None:
        _CONFIG_CACHE["ts"] = now
        _CONFIG_CACHE["cfg"] = cfg
    return cfg


def _cfg_value(cfg: dict | None, key: str, fallback):
    if cfg and cfg.get(key) is not None:
        return cfg.get(key)
    return fallback


def setup_logging(verbose: bool = False) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S")


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV scrape -> TimescaleDB")
    parser.add_argument("--loop", action="store_true", help="Run scrape in a loop")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("open_fdd.csv")

    settings = get_platform_settings()
    prev_interval_min: int | None = None

    while True:
        cfg = _fetch_platform_config_cached(log)
        enabled = bool(_cfg_value(cfg, "csv_enabled", settings.csv_enabled))
        if not enabled:
            log.info("CSV ingestion disabled via config/env.")
            if not args.loop:
                return 0
            time.sleep(60)
            continue

        interval_raw = _cfg_value(cfg, "csv_scrape_interval_min", settings.csv_scrape_interval_min)
        try:
            interval_min = int(interval_raw)
        except (TypeError, ValueError):
            interval_min = settings.csv_scrape_interval_min
            log.warning(
                "Invalid csv_scrape_interval_min=%r; using default %s",
                interval_raw,
                interval_min,
            )

        sources_raw = str(_cfg_value(cfg, "csv_sources", settings.csv_sources))
        backfill_start = parse_iso_ts(_cfg_value(cfg, "csv_backfill_start", settings.csv_backfill_start))
        backfill_end = parse_iso_ts(_cfg_value(cfg, "csv_backfill_end", settings.csv_backfill_end))
        create_points = bool(_cfg_value(cfg, "csv_create_points", settings.csv_create_points))

        try:
            sources = parse_csv_sources(sources_raw)
        except Exception as e:
            log.error("Invalid csv_sources: %s", e)
            return 1
        if not sources:
            log.warning("CSV ingestion enabled but csv_sources is empty.")
            if not args.loop:
                return 0
            time.sleep(max(1, interval_min) * 60)
            continue

        if prev_interval_min is not None and interval_min != prev_interval_min:
            log.info("CSV scrape interval changed: %d min -> %d min", prev_interval_min, interval_min)
        prev_interval_min = interval_min

        try:
            summary = run_csv_ingest_once(
                log,
                sources=sources,
                backfill_start=backfill_start,
                backfill_end=backfill_end,
                create_points=create_points,
            )
            log.info(
                "CSV ingest OK: sources=%s points=%s rows=%s",
                summary["sources"],
                summary["points_upserted"],
                summary["rows_inserted"],
            )
        except Exception as e:
            log.exception("CSV ingest failed: %s", e)
            if not args.loop:
                return 1

        if not args.loop:
            break
        time.sleep(max(1, interval_min) * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
