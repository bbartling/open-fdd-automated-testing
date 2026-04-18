#!/usr/bin/env python3
"""BACnet scrape runner — rusty-bacnet backed, writes to SeleneDB.

Replaces the old JSON-RPC + Postgres path (Phase 2.5d rewrite). The
loop body is now a few lines:

1. Open a :class:`BipTransport` (UDP/47808 on the host network).
2. Load a :class:`~openfdd_stack.platform.bacnet.ScrapePlan` from
   SeleneDB — ``:bacnet_device``-``:bacnet_object``-``:point``
   bindings walked by :func:`load_scrape_plan`.
3. Run :meth:`BacnetScraper.scrape_once`. Samples land in
   SeleneDB via ``ts_write``.
4. Sleep ``OFDD_BACNET_SCRAPE_INTERVAL_MIN`` minutes; repeat.

Container entrypoint (unchanged CLI shape so docker-compose keeps
working): ``python -m openfdd_stack.platform.drivers.run_bacnet_scrape
--loop``.

Exit behaviour:

- SIGTERM / SIGINT → finish the current scrape, close transport,
  exit 0.
- Fatal transport error (can't bind UDP, can't reach Selene) →
  log and exit non-zero so the container restarts per compose
  policy.
- Per-device scrape failures are tolerated by
  :class:`BacnetScraper.scrape_once` and do not crash the loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from openfdd_stack.platform.bacnet import (
    BacnetError,
    BacnetScraper,
    BipTransport,
    ScrapeResult,
    load_scrape_plan,
)
from openfdd_stack.platform.config import get_platform_settings
from openfdd_stack.platform.selene import make_selene_client_from_settings

logger = logging.getLogger("openfdd.bacnet.scrape")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _make_transport() -> BipTransport:
    """Build the transport from platform settings.

    All knobs come from ``OFDD_BACNET_*`` env (via pydantic settings).
    See ``docker-compose.yml``'s ``bacnet-scraper`` service for the
    container-side values.
    """
    s = get_platform_settings()
    return BipTransport(
        interface=getattr(s, "bacnet_interface", None) or "0.0.0.0",
        port=int(getattr(s, "bacnet_port", None) or 47808),
        broadcast_address=getattr(s, "bacnet_broadcast_address", None)
        or "255.255.255.255",
        apdu_timeout_ms=int(getattr(s, "bacnet_apdu_timeout_ms", None) or 6000),
    )


async def _scrape_cycle(scraper: BacnetScraper) -> ScrapeResult:
    """One pass: refresh plan from Selene, scrape, log summary."""
    plan = await asyncio.to_thread(_load_plan_from_selene_blocking)
    if plan is None:
        logger.warning("bacnet scrape skipped: could not load plan from Selene")
        return ScrapeResult(0, 0, 0)

    if plan.binding_count == 0:
        logger.info(
            "bacnet scrape: no :bacnet_object→:point bindings in Selene; "
            "idle until something gets bound via the API"
        )
        return ScrapeResult(0, 0, 0)

    result = await scraper.scrape_once(plan)
    logger.info(
        "bacnet scrape: wrote=%d errors=%d device_failures=%d devices=%d",
        result.samples_written,
        result.read_errors,
        result.device_failures,
        len(plan.devices),
    )
    return result


def _load_plan_from_selene_blocking():
    """Synchronous plan load — runs on a worker thread via ``to_thread``."""
    try:
        with make_selene_client_from_settings() as client:
            return load_scrape_plan(client)
    except Exception:  # noqa: BLE001 — any Selene failure should skip this cycle
        logger.warning("bacnet scrape: load_scrape_plan failed", exc_info=True)
        return None


async def _run_forever(
    interval_sec: float,
    *,
    stop_event: asyncio.Event,
) -> int:
    """Main loop; returns process exit code."""
    try:
        transport = _make_transport()
    except Exception:  # noqa: BLE001 — couldn't even construct, fatal
        logger.critical("bacnet scrape: cannot construct transport", exc_info=True)
        return 2

    try:
        async with transport as tx:
            scraper = BacnetScraper(tx, make_selene_client_from_settings)
            logger.info(
                "bacnet scrape ready: interface=%s port=%d interval=%.0fs",
                tx._interface,  # type: ignore[attr-defined]  — surface for log only
                tx._port,  # type: ignore[attr-defined]
                interval_sec,
            )
            while not stop_event.is_set():
                try:
                    await _scrape_cycle(scraper)
                except BacnetError:
                    # Per-scrape errors are caught inside scrape_once; a bare
                    # BacnetError escaping here means the transport itself
                    # is unhealthy. Log and keep looping; the driver handles
                    # transient UDP hiccups.
                    logger.warning(
                        "bacnet scrape cycle failed (will retry next interval)",
                        exc_info=True,
                    )
                except Exception:  # noqa: BLE001
                    # Anything else is surprising — log with full traceback
                    # and keep looping so one bug doesn't kill the container.
                    logger.exception("bacnet scrape cycle hit unexpected error")
                # Sleep but wake early on stop_event so SIGTERM handling is fast.
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
                except asyncio.TimeoutError:
                    pass
    except BacnetError:
        logger.critical(
            "bacnet scrape: transport unrecoverable; exiting", exc_info=True
        )
        return 3
    logger.info("bacnet scrape: stop requested, exiting cleanly")
    return 0


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event
) -> None:
    """Wire SIGTERM / SIGINT to the stop event for graceful shutdown."""

    def _request_stop() -> None:
        logger.info("bacnet scrape: received signal, initiating shutdown")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows — fall back to the default handler; SIGINT still
            # raises KeyboardInterrupt which escapes the asyncio.run().
            pass


def _resolved_interval_sec() -> float:
    """Interval in seconds; defaults to 5 minutes, clamped to ≥10s."""
    s = get_platform_settings()
    minutes = max(1, int(getattr(s, "bacnet_scrape_interval_min", 5) or 5))
    # Fractional minutes are supported by the settings module for
    # testing; honour them here too.
    try:
        raw = float(getattr(s, "bacnet_scrape_interval_min", 5) or 5)
    except (TypeError, ValueError):  # fmt: skip
        raw = 5.0
    seconds = max(10.0, raw * 60.0)
    logger.debug("bacnet scrape interval: minutes=%s → %.1fs", minutes, seconds)
    return seconds


async def _main_async(args: argparse.Namespace) -> int:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    _install_signal_handlers(loop, stop_event)

    if not args.loop:
        # One-shot mode: run a single cycle, exit with the result's
        # device_failures count as a loose health signal.
        try:
            transport = _make_transport()
        except Exception:  # noqa: BLE001
            logger.critical("bacnet scrape: cannot construct transport", exc_info=True)
            return 2
        async with transport as tx:
            scraper = BacnetScraper(tx, make_selene_client_from_settings)
            result = await _scrape_cycle(scraper)
        return 0 if result.device_failures == 0 else 1

    return await _run_forever(_resolved_interval_sec(), stop_event=stop_event)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "BACnet scrape runner (rusty-bacnet + SeleneDB). "
            "Reads :bacnet_object → :point bindings from Selene and "
            "writes present-value samples via ts_write."
        )
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously on the configured interval (default: one-shot).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Debug-level logging.",
    )
    # ``--site`` kept for CLI backward-compatibility with the prior runner;
    # it's a no-op now because bindings carry their site context in the
    # graph (``:bacnet_network`` node).
    parser.add_argument(
        "--site",
        default=None,
        help="[deprecated] Ignored — site is encoded in the graph.",
    )
    args = parser.parse_args()

    _configure_logging(args.verbose)

    if args.site:
        logger.warning(
            "bacnet scrape: --site is deprecated and ignored "
            "(bindings carry their site in the graph)"
        )

    try:
        return asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
