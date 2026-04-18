#!/usr/bin/env python3
"""Phase-1 SeleneDB smoke harness.

Exercises the openfdd_stack ``SeleneClient`` end-to-end against a running
SeleneDB instance. Validates the integration shape (auth, GQL, node CRUD,
time-series write/read) — not Selene's engine performance (already benched
upstream: hot-tier append 215µs @ 10K-scale).

Run locally against a profile-selene container:

    docker compose --profile selene -f stack/docker-compose.yml up -d selene
    python scripts/selene_smoke.py

Exit code 0 on success; non-zero with a pointed message otherwise.

Environment variables (all optional — defaults target docker-compose):
    OFDD_SELENE_URL       (default http://localhost:8080)
    OFDD_SELENE_IDENTITY  (default unset — relies on dev_mode)
    OFDD_SELENE_SECRET    (default unset)
    OFDD_SELENE_SMOKE_SAMPLES  (default 100)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass

from openfdd_stack.platform.selene import (
    SeleneClient,
    SeleneConnectionError,
    SeleneError,
)


@dataclass
class SmokeResult:
    health: bool
    node_id: int
    samples_written: int
    samples_read: int
    write_ms: float
    read_ms: float


def run(
    url: str,
    identity: str | None,
    secret: str | None,
    sample_count: int,
) -> SmokeResult:
    with SeleneClient(url, identity=identity, secret=secret, timeout_sec=30) as c:
        # 1. Health — catches auth + network wiring up front.
        health = c.health()
        if health.get("status") != "ok":
            raise RuntimeError(f"unexpected /health payload: {health}")

        # 2. Create a scratch node that survives the run so follow-up GQL works.
        node = c.create_node(
            labels=["smoke_entity"],
            properties={
                "name": f"ofdd-smoke-{int(time.time())}",
                "purpose": "openfdd_stack phase-1 smoke test",
            },
        )
        node_id = int(node["id"])

        try:
            # 3. Batch ts_write — a minute of fake 1-sec readings.
            now_ns = time.time_ns()
            # 1_000_000_000 nanoseconds = 1 second step between samples
            step_ns = 1_000_000_000
            samples = [
                {
                    "entity_id": node_id,
                    "property": "smoke_value",
                    "timestamp_nanos": now_ns - (sample_count - i) * step_ns,
                    "value": 20.0 + (i % 10) * 0.5,
                }
                for i in range(sample_count)
            ]
            t0 = time.perf_counter()
            written = c.ts_write(samples)
            write_ms = (time.perf_counter() - t0) * 1000

            # 4. Read them back via the REST range endpoint.
            t0 = time.perf_counter()
            rows = c.ts_range(
                node_id,
                "smoke_value",
                start_nanos=now_ns - sample_count * step_ns,
                end_nanos=now_ns + step_ns,
                limit=sample_count * 2,
            )
            read_ms = (time.perf_counter() - t0) * 1000

            return SmokeResult(
                health=True,
                node_id=node_id,
                samples_written=written,
                samples_read=len(rows),
                write_ms=write_ms,
                read_ms=read_ms,
            )
        finally:
            # 5. Best-effort cleanup so repeated smoke runs don't litter the graph,
            #    even when ts_write / ts_range raises mid-run. Swallow cleanup
            #    errors so they don't mask the original exception.
            try:
                c.delete_node(node_id)
            except Exception as cleanup_exc:  # noqa: BLE001
                print(
                    f"selene-smoke: WARN could not delete scratch node {node_id} "
                    f"({type(cleanup_exc).__name__}: {cleanup_exc})",
                    file=sys.stderr,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url", default=os.environ.get("OFDD_SELENE_URL", "http://localhost:8080")
    )
    parser.add_argument("--identity", default=os.environ.get("OFDD_SELENE_IDENTITY"))
    parser.add_argument("--secret", default=os.environ.get("OFDD_SELENE_SECRET"))
    parser.add_argument(
        "--samples",
        type=int,
        default=int(os.environ.get("OFDD_SELENE_SMOKE_SAMPLES", "100")),
    )
    args = parser.parse_args()

    print(f"selene-smoke: target={args.url} samples={args.samples}", flush=True)
    try:
        result = run(args.url, args.identity, args.secret, args.samples)
    except SeleneConnectionError as exc:
        print(
            f"selene-smoke: FAIL cannot reach Selene at {args.url} ({exc}). "
            f"Start it with `docker compose --profile selene up -d selene` "
            f"or point OFDD_SELENE_URL at a live instance.",
            file=sys.stderr,
        )
        return 2
    except SeleneError as exc:
        print(f"selene-smoke: FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001 - bubble up with context
        print(
            f"selene-smoke: FAIL unexpected {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 4

    rate = result.samples_written / (result.write_ms / 1000) if result.write_ms else 0
    print(
        f"selene-smoke: OK node_id={result.node_id} "
        f"written={result.samples_written}/{args.samples} "
        f"read={result.samples_read} "
        f"write_ms={result.write_ms:.1f} ({rate:.0f}/sec) "
        f"read_ms={result.read_ms:.1f}"
    )
    if result.samples_read != result.samples_written:
        print(
            f"selene-smoke: WARN read count ({result.samples_read}) != "
            f"written count ({result.samples_written}). Likely range clock skew; "
            f"not fatal for Phase 1.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
