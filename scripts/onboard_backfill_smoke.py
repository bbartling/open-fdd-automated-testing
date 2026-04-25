#!/usr/bin/env python3
"""Run one-shot Onboard ingest/backfill smoke check."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from openfdd_stack.platform.drivers.onboard import (
    parse_building_filters,
    parse_iso_ts,
    run_onboard_ingest_once,
)
from _onboard_cli import fallback_api_key_from_stack_env


def parse_bool_env(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Onboard one-shot ingest smoke test")
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("OFDD_ONBOARD_API_BASE_URL", "https://api.onboarddata.io"),
    )
    parser.add_argument("--api-key", default=os.getenv("OFDD_ONBOARD_API_KEY", ""))
    parser.add_argument(
        "--building-ids",
        default=os.getenv("OFDD_ONBOARD_BUILDING_IDS", ""),
        help="CSV or JSON array (ex: 66,67 or [66,67])",
    )
    parser.add_argument(
        "--building",
        action="append",
        default=[],
        help='Building name filter (repeatable), e.g. --building "Office Building"',
    )
    parser.add_argument(
        "--backfill-start",
        default=os.getenv("OFDD_ONBOARD_BACKFILL_START", ""),
        help="ISO-8601 start timestamp",
    )
    parser.add_argument(
        "--backfill-end",
        default=os.getenv("OFDD_ONBOARD_BACKFILL_END", ""),
        help="ISO-8601 end timestamp",
    )
    parser.add_argument(
        "--interval-min",
        default=os.getenv("OFDD_ONBOARD_SCRAPE_INTERVAL_MIN", "180"),
        type=int,
    )
    parser.add_argument(
        "--site-id-strategy",
        default=os.getenv("OFDD_ONBOARD_SITE_ID_STRATEGY", "onboard-building-id"),
        choices=["default", "onboard-building-id"],
    )
    parser.add_argument(
        "--create-points",
        action=argparse.BooleanOptionalAction,
        default=parse_bool_env(os.getenv("OFDD_ONBOARD_CREATE_POINTS", "true"), default=True),
    )
    parser.add_argument(
        "--no-stack-env-fallback",
        action="store_true",
        help="Do not read OFDD_ONBOARD_API_KEY from stack/.env when --api-key is empty",
    )
    args = parser.parse_args()

    api_key = (args.api_key or "").strip()
    if not api_key and not args.no_stack_env_fallback:
        api_key = fallback_api_key_from_stack_env()
    if not api_key:
        print("Missing API key. Set --api-key or OFDD_ONBOARD_API_KEY.", file=sys.stderr)
        return 1

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("onboard_backfill_smoke")

    building_filters = parse_building_filters(args.building_ids)
    building_filters.extend([b for b in args.building if str(b).strip()])
    summary = run_onboard_ingest_once(
        log,
        base_url=args.api_base_url,
        api_key=api_key,
        building_filters=building_filters,
        backfill_start=parse_iso_ts(args.backfill_start),
        scrape_interval_min=max(1, int(args.interval_min)),
        backfill_end=parse_iso_ts(args.backfill_end),
        site_id_strategy=args.site_id_strategy,
        create_points=bool(args.create_points),
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
