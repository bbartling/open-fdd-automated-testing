"""Platform configuration.

Runtime config is built from **Pydantic env** (``OFDD_*`` / ``stack/.env``) plus the **RDF overlay**
(``data_model.ttl`` / PUT /config). The overlay is applied on top of env for graph-backed keys.

**Exception:** ``OFDD_BACNET_SERVER_URL`` in the process environment, when set, **always wins** over
``ofdd:bacnetServerUrl`` in the graph. The TTL often carries ``http://localhost:8080`` for local dev;
that would break Docker (bridge → ``localhost`` is the container, not the host). The DIY gateway
typically runs with ``network_mode: host`` — it is **not** on the same Docker bridge as ``api`` /
``frontend``; reachability is **host routing / firewall**, not ordinary sibling-container DNS.
"""

import os
from typing import Optional

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings  # type: ignore

# Overlay from RDF graph (GET/PUT /config). Merged over env in get_platform_settings().
_config_overlay: dict = {}


def set_config_overlay(overlay: dict | None) -> None:
    """Set the config overlay (from graph). Called after load_from_file() and on PUT /config."""
    global _config_overlay
    _config_overlay = dict(overlay) if overlay else {}


def get_config_overlay() -> dict:
    """Return current overlay (snake_case keys)."""
    return dict(_config_overlay)


class PlatformSettings(BaseSettings):
    """App settings from env."""

    db_dsn: str = "postgresql://postgres:postgres@localhost:5432/openfdd"
    brick_ttl_dir: str = "data/brick"
    brick_ttl_path: str = (
        "config/data_model.ttl"  # unified graph: Brick + BACnet + config; auto-synced on CRUD
    )
    app_title: str = "Open-FDD API"
    # Bump with root pyproject.toml [project].version and frontend/package.json "version".
    app_version: str = "2.0.16"
    debug: bool = False

    # FDD loop
    rule_interval_hours: float = 3.0  # fractional OK for testing (e.g. 0.1 = 6 min)
    lookback_days: int = 3
    fdd_backfill_enabled: bool = False
    fdd_backfill_start: Optional[str] = None
    fdd_backfill_end: Optional[str] = None
    fdd_backfill_step_hours: int = 3
    fdd_trigger_file: Optional[str] = (
        "config/.run_fdd_now"  # touch to run now + reset timer
    )
    rules_dir: str = (
        "stack/rules"  # default rules next to stack/docker; hot reload each run
    )
    # When True: FDD loop fails fast on bad column_map / non-numeric inputs (open-fdd input_validation=strict, skip_missing_columns=False). Use in dev/CI.
    fdd_strict_rules: bool = False

    # Driver intervals
    bacnet_scrape_interval_min: int = 5
    open_meteo_interval_hours: int = 24
    onboard_scrape_interval_min: int = 180
    csv_scrape_interval_min: int = 180

    # Driver on/off (like Volttron agent enable/disable)
    bacnet_scrape_enabled: bool = True
    open_meteo_enabled: bool = True
    onboard_enabled: bool = False
    csv_enabled: bool = False

    # Open-Meteo: geo and fetch window (used when open_meteo_enabled)
    open_meteo_latitude: float = 41.88
    open_meteo_longitude: float = -87.63
    open_meteo_timezone: str = "America/Chicago"
    open_meteo_days_back: int = 3
    open_meteo_site_id: str = "default"  # site name or UUID to store weather under

    # Onboard API ingestion (read-only metadata + timeseries)
    onboard_api_base_url: str = "https://api.onboarddata.io"
    onboard_api_key: Optional[str] = None
    onboard_building_ids: str = ""
    onboard_backfill_start: Optional[str] = None
    onboard_backfill_end: Optional[str] = None
    onboard_site_id_strategy: str = "onboard-building-id"
    onboard_create_points: bool = True

    # CSV ingestion (local files -> points/timeseries)
    csv_sources: str = ""
    csv_backfill_start: Optional[str] = None
    csv_backfill_end: Optional[str] = None
    csv_create_points: bool = True

    # Graph model: sync in-memory graph to data_model.ttl every N minutes
    graph_sync_interval_min: int = 5

    # BACnet: use diy-bacnet-server JSON-RPC when set (e.g. http://localhost:8080)
    bacnet_server_url: Optional[str] = None
    # Site to tag when scraping (single gateway or remote gateway pushing to central)
    bacnet_site_id: str = "default"
    # Optional: multiple gateways (central aggregator). JSON array of {"url", "site_id", ...}; scrape uses KG points per site.
    bacnet_gateways: Optional[str] = None

    # API key for REST/WebSocket auth (Bearer). When set, required on all endpoints except /health, /, /app (and /app/*)
    api_key: Optional[str] = None
    # Single-user Phase-1 auth (bootstrap-managed); hash should be argon2id.
    app_user: Optional[str] = None
    app_user_hash: Optional[str] = None
    # Access-token signing secret (required when Phase 1 app user is enabled).
    jwt_secret: Optional[str] = None
    access_token_minutes: int = 60
    refresh_token_days: int = 7
    # When true, expose /docs, /redoc, /openapi.json (HTTP lab). False when edge uses self-signed Caddy (bootstrap).
    enable_openapi_docs: bool = False
    # When true, treat X-Forwarded-Proto: https as HTTPS for Secure cookies (TLS at reverse proxy only).
    trust_forwarded_proto: bool = False
    # When set, requests with header X-Caddy-Auth equal to this value are trusted (Caddy sets it after Basic auth). Use behind Caddy so the browser only does Basic once.
    caddy_internal_secret: Optional[str] = None

    # Reserved for RDF overlay compatibility (always "disabled" in core builds).
    ai_backend: str = "disabled"

    model_config = {"env_prefix": "OFDD_", "env_file": ".env"}


def get_platform_settings() -> PlatformSettings:
    """Merge RDF overlay onto env-backed settings. ``OFDD_BACNET_SERVER_URL`` wins over graph when set."""
    s = PlatformSettings()
    overlay = get_config_overlay()
    key_to_attr = {
        "bacnet_enabled": "bacnet_scrape_enabled",
        "ai_backend": "ai_backend",
    }  # RDF/API name -> PlatformSettings attr
    for k, v in overlay.items():
        attr = key_to_attr.get(k, k)
        if hasattr(s, attr):
            setattr(s, attr, v)
    env_bacnet = (os.environ.get("OFDD_BACNET_SERVER_URL") or "").strip()
    if env_bacnet:
        s.bacnet_server_url = env_bacnet.rstrip("/")
    return s
