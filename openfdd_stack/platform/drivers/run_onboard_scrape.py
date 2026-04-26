#!/usr/bin/env python3
"""Run Onboard API scrape: metadata + query-v2 -> TimescaleDB."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from openfdd_stack.platform.config import get_platform_settings
from openfdd_stack.platform.drivers.onboard import (
    parse_building_filters,
    parse_iso_ts,
    run_onboard_ingest_once,
)


_CONFIG_CACHE: dict[str, object] = {"ts": 0.0, "cfg": None}


def _get_api_url() -> str:
    return os.getenv("OFDD_API_URL", "http://localhost:8000").rstrip("/")


def _fetch_platform_config(log: logging.Logger) -> dict | None:
    url = f"{_get_api_url()}/config"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        log.warning("Unsupported OFDD_API_URL scheme for %s", url)
        return None
    req = urllib.request.Request(url)
    api_key = os.environ.get("OFDD_API_KEY", "").strip()
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            log.warning("GET /config returned 401; scraper will use env/defaults.")
        else:
            log.warning("GET /config failed: %s %s. Using env/defaults.", e.code, url)
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
    parser = argparse.ArgumentParser(description="Onboard API scrape -> TimescaleDB")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run scrape every onboard_scrape_interval_min",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    log = logging.getLogger("open_fdd.onboard")

    prev_interval_min: int | None = None

    while True:
        settings = get_platform_settings()
        cfg = _fetch_platform_config_cached(log)
        enabled = bool(_cfg_value(cfg, "onboard_enabled", settings.onboard_enabled))
        if not enabled:
            log.info("Onboard ingestion disabled via config/env.")
            if not args.loop:
                return 0
            time.sleep(60)
            continue

        api_key = (settings.onboard_api_key or "").strip()
        if not api_key:
            log.error("OFDD_ONBOARD_API_KEY is required when onboard_enabled=true.")
            if not args.loop:
                return 1
            sleep_sec = max(1, int(settings.onboard_scrape_interval_min)) * 60
            time.sleep(sleep_sec)
            continue

        base_url = str(
            _cfg_value(cfg, "onboard_api_base_url", settings.onboard_api_base_url)
        ).strip()
        building_ids_raw = str(
            _cfg_value(cfg, "onboard_building_ids", settings.onboard_building_ids)
        )
        interval_raw = _cfg_value(
            cfg, "onboard_scrape_interval_min", settings.onboard_scrape_interval_min
        )
        try:
            interval_min = int(interval_raw)
        except (ValueError, TypeError):
            interval_min = settings.onboard_scrape_interval_min
            log.warning(
                "Invalid onboard_scrape_interval_min=%r; using default %s",
                interval_raw,
                interval_min,
            )
        backfill_start = parse_iso_ts(
            _cfg_value(cfg, "onboard_backfill_start", settings.onboard_backfill_start)
        )
        backfill_end = parse_iso_ts(
            _cfg_value(cfg, "onboard_backfill_end", settings.onboard_backfill_end)
        )
        site_id_strategy = str(
            _cfg_value(
                cfg, "onboard_site_id_strategy", settings.onboard_site_id_strategy
            )
        ).strip() or "onboard-building-id"
        create_points = bool(
            _cfg_value(cfg, "onboard_create_points", settings.onboard_create_points)
        )
        default_site_id = "default"

        try:
            building_filters = parse_building_filters(building_ids_raw)
        except Exception as e:
            log.error("Invalid onboard_building_ids: %s", e)
            if not args.loop:
                return 1
            time.sleep(max(1, interval_min) * 60)
            continue

        if prev_interval_min is not None and interval_min != prev_interval_min:
            log.info(
                "Onboard scrape interval changed: %d min -> %d min",
                prev_interval_min,
                interval_min,
            )
        prev_interval_min = interval_min

        try:
            summary = run_onboard_ingest_once(
                log,
                base_url=base_url,
                api_key=api_key,
                building_filters=building_filters,
                backfill_start=backfill_start,
                scrape_interval_min=interval_min,
                backfill_end=backfill_end,
                site_id_strategy=site_id_strategy,
                create_points=create_points,
                default_site_id=default_site_id,
            )
            log.info(
                "Onboard ingest OK: buildings=%s points_seen=%s points_upserted=%s rows=%s",
                summary.get("buildings", 0),
                summary.get("points_seen", 0),
                summary.get("points_upserted", 0),
                summary.get("rows_inserted", 0),
            )
        except Exception as e:
            log.exception("Onboard ingest failed: %s", e)
            if not args.loop:
                return 1

        if not args.loop:
            break
        time.sleep(max(1, interval_min) * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
