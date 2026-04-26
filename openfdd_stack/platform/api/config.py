"""Config API: GET/PUT platform config (RDF in same graph as Brick + BACnet, SPARQL via POST /data-model/sparql)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from openfdd_stack.platform.config import get_config_overlay, set_config_overlay
from openfdd_stack.platform.default_config import DEFAULT_PLATFORM_CONFIG
from openfdd_stack.platform.driver_profile import driver_services_mapping, load_driver_profile
from openfdd_stack.platform.graph_model import (
    get_config_from_graph,
    set_config_in_graph,
    write_ttl_to_file,
)

router = APIRouter(prefix="/config", tags=["config"])

# Allowed keys for PUT (subset of PlatformSettings that live in RDF)
CONFIG_KEYS = {
    "rule_interval_hours",
    "lookback_days",
    "fdd_backfill_enabled",
    "fdd_backfill_start",
    "fdd_backfill_end",
    "fdd_backfill_step_hours",
    "rules_dir",
    "brick_ttl_dir",
    "bacnet_enabled",
    "bacnet_scrape_interval_min",
    "bacnet_server_url",
    "bacnet_site_id",
    "bacnet_gateways",
    "open_meteo_enabled",
    "open_meteo_interval_hours",
    "open_meteo_latitude",
    "open_meteo_longitude",
    "open_meteo_timezone",
    "open_meteo_days_back",
    "open_meteo_site_id",
    "onboard_enabled",
    "onboard_api_base_url",
    "onboard_building_ids",
    "onboard_scrape_interval_min",
    "onboard_backfill_start",
    "onboard_backfill_end",
    "onboard_site_id_strategy",
    "onboard_create_points",
    "csv_enabled",
    "csv_sources",
    "csv_scrape_interval_min",
    "csv_backfill_start",
    "csv_backfill_end",
    "csv_create_points",
    "graph_sync_interval_min",
}


class ConfigBody(BaseModel):
    """Platform config (RDF-backed). Omitted keys are left unchanged."""

    rule_interval_hours: float | None = Field(
        None, description="FDD rule run interval (hours)"
    )
    lookback_days: int | None = Field(None, description="Days of data per FDD run")
    fdd_backfill_enabled: bool | None = Field(
        None, description="Enable one-pass FDD historical backfill run"
    )
    fdd_backfill_start: datetime | None = Field(
        None, description="Historical FDD backfill start timestamp (ISO-8601)"
    )
    fdd_backfill_end: datetime | None = Field(
        None, description="Historical FDD backfill end timestamp (ISO-8601, optional)"
    )
    fdd_backfill_step_hours: int | None = Field(
        None, description="Historical FDD backfill window size (hours)"
    )
    rules_dir: str | None = Field(None, description="Path to FDD rules YAML")
    brick_ttl_dir: str | None = Field(None, description="Directory for Brick TTL")
    bacnet_enabled: bool | None = Field(None, description="Enable BACnet scraper")
    bacnet_scrape_interval_min: int | None = Field(
        None, description="BACnet scrape interval (minutes)"
    )
    bacnet_server_url: str | None = Field(None, description="diy-bacnet-server URL")
    bacnet_site_id: str | None = Field(
        None, description="Default site for BACnet scrape"
    )
    bacnet_gateways: str | None = Field(
        None,
        description='JSON array of {"url","site_id"} for multi-gateway; BACnet addresses come from the data model',
    )
    open_meteo_enabled: bool | None = Field(None, description="Enable Open-Meteo fetch")
    open_meteo_interval_hours: int | None = Field(
        None, description="Weather fetch interval (hours)"
    )
    open_meteo_latitude: float | None = Field(None, description="Latitude")
    open_meteo_longitude: float | None = Field(None, description="Longitude")
    open_meteo_timezone: str | None = Field(None, description="Timezone")
    open_meteo_days_back: int | None = Field(
        None, description="Days of weather to fetch"
    )
    open_meteo_site_id: str | None = Field(None, description="Site for weather points")
    onboard_enabled: bool | None = Field(None, description="Enable Onboard API ingestion")
    onboard_api_base_url: str | None = Field(
        None, description="Onboard API base URL"
    )
    onboard_building_ids: str | None = Field(
        None,
        description="Building selectors as CSV (66,67), bracketed list ([66,67]), or JSON array of IDs/names (e.g. [\"Office Building\"])",
    )
    onboard_scrape_interval_min: int | None = Field(
        None, description="Onboard incremental scrape interval (minutes)"
    )
    onboard_backfill_start: datetime | None = Field(
        None, description="Onboard backfill window start timestamp (ISO-8601)"
    )
    onboard_backfill_end: datetime | None = Field(
        None, description="Onboard backfill window end timestamp (ISO-8601)"
    )
    onboard_site_id_strategy: Literal["default", "onboard-building-id"] | None = Field(
        None,
        description='Site mapping strategy for Onboard buildings ("default" or "onboard-building-id")',
    )
    onboard_create_points: bool | None = Field(
        None,
        description="When true, ingest metadata can auto-create points before timeseries writes",
    )
    csv_enabled: bool | None = Field(None, description="Enable CSV ingestion")
    csv_sources: str | None = Field(
        None,
        description='JSON array of CSV sources: [{"path":"...","site_id":"..."}]',
    )
    csv_scrape_interval_min: int | None = Field(
        None, description="CSV scraper loop interval (minutes)"
    )
    csv_backfill_start: datetime | None = Field(
        None, description="CSV backfill start timestamp (ISO-8601)"
    )
    csv_backfill_end: datetime | None = Field(
        None, description="CSV backfill end timestamp (ISO-8601)"
    )
    csv_create_points: bool | None = Field(
        None, description="When true, CSV ingest can auto-create points"
    )
    graph_sync_interval_min: int | None = Field(
        None, description="Graph sync to TTL (minutes)"
    )


def _normalize_config_for_display(raw: dict) -> dict:
    """Apply display defaults and reflect runtime env overrides.

    ``OFDD_BACNET_SERVER_URL`` (set by Docker Compose / ``stack/.env``) overrides ``bacnet_server_url``
    in the returned dict so GET /config matches what ``get_platform_settings()`` uses. Without this,
    the graph often still has ``http://localhost:8080`` while containers use a LAN or
    ``host.docker.internal`` URL — operators and UI drift from reality.
    """
    out = dict(raw)
    # Preserve explicit zero; default only when key is truly missing/unset.
    if out.get("rule_interval_hours") is None:
        out["rule_interval_hours"] = 3.0
    if out.get("bacnet_gateways") == "string":
        out["bacnet_gateways"] = ""
    env_bs = (os.environ.get("OFDD_BACNET_SERVER_URL") or "").strip()
    if env_bs:
        out["bacnet_server_url"] = env_bs.rstrip("/")
    return out


@router.get("", summary="Get platform config")
def get_config():
    """Return platform config for the Config UI (graph + display normalizations).

    RDF / ``data_model.ttl`` is the persisted source of truth for PUT; ``OFDD_BACNET_SERVER_URL``
    in the process environment is merged into the GET payload when set (see ``_normalize_config_for_display``).
    """
    overlay = get_config_overlay()
    if overlay:
        return _normalize_config_for_display(overlay)
    from_graph = get_config_from_graph()
    if from_graph:
        return _normalize_config_for_display(from_graph)
    return _normalize_config_for_display(dict(DEFAULT_PLATFORM_CONFIG))


class DriverProfileStatus(BaseModel):
    profile_path: str
    profile_exists: bool
    drivers: dict[str, bool]
    services: dict[str, bool]


@router.get(
    "/driver-profile",
    summary="Get driver bootstrap profile",
    response_model=DriverProfileStatus,
)
def get_driver_profile():
    drivers, path, exists = load_driver_profile()
    return {
        "profile_path": str(path),
        "profile_exists": exists,
        "drivers": drivers,
        "services": driver_services_mapping(drivers),
    }


@router.put("", summary="Set platform config (RDF + TTL)")
def put_config(body: ConfigBody):
    """Update platform config in the graph and serialize to config/data_model.ttl. Omitted keys are unchanged."""
    overlay = get_config_overlay()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        # No changes; still persist current overlay to graph if any
        if overlay:
            set_config_in_graph(overlay)
            ok, err = write_ttl_to_file()
            if not ok:
                raise HTTPException(500, f"Failed to write TTL: {err}")
        return get_config()

    if overlay:
        merged = dict(overlay)
    else:
        from_graph = get_config_from_graph()
        merged = dict(from_graph) if from_graph else dict(DEFAULT_PLATFORM_CONFIG)
    for k, v in updates.items():
        if k in CONFIG_KEYS:
            merged[k] = v
    set_config_in_graph(merged)
    ok, err = write_ttl_to_file()
    if not ok:
        raise HTTPException(500, f"Failed to write TTL: {err}")
    set_config_overlay(merged)
    try:
        from openfdd_stack.platform.realtime import (
            emit,
            TOPIC_CONFIG_UPDATED,
            TOPIC_GRAPH_UPDATED,
        )

        emit(TOPIC_CONFIG_UPDATED, {"keys": list(updates.keys())})
        emit(TOPIC_GRAPH_UPDATED, {})
    except Exception:
        pass
    return _normalize_config_for_display(merged)
