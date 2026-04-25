#!/usr/bin/env python3
"""List Onboard buildings and point metadata for troubleshooting."""

from __future__ import annotations

import argparse
import json
import os
import sys

from openfdd_stack.platform.drivers.onboard import OnboardClient, parse_building_ids


def main() -> int:
    parser = argparse.ArgumentParser(description="List Onboard metadata")
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
    args = parser.parse_args()

    api_key = (args.api_key or "").strip()
    if not api_key:
        print("Missing API key. Set --api-key or OFDD_ONBOARD_API_KEY.", file=sys.stderr)
        return 1

    client = OnboardClient(base_url=args.api_base_url, api_key=api_key)
    building_ids = parse_building_ids(args.building_ids)
    buildings = client.get_buildings(building_ids)

    out: list[dict] = []
    for b in buildings:
        bldg_id = int(b["id"])
        points = client.get_points(bldg_id)
        out.append(
            {
                "building_id": bldg_id,
                "name": b.get("name"),
                "point_count": len(points),
                "sample_points": points[:5],
            }
        )
    print(json.dumps({"buildings": out}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
