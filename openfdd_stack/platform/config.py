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
    app_version: str = "2.0.14"
    debug: bool = False

    # FDD loop
    rule_interval_hours: float = 3.0  # fractional OK for testing (e.g. 0.1 = 6 min)
    lookback_days: int = 3
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

    # Driver on/off (like Volttron agent enable/disable)
    bacnet_scrape_enabled: bool = True
    open_meteo_enabled: bool = True

    # Open-Meteo: geo and fetch window (used when open_meteo_enabled)
    open_meteo_latitude: float = 41.88
    open_meteo_longitude: float = -87.63
    open_meteo_timezone: str = "America/Chicago"
    open_meteo_days_back: int = 3
    open_meteo_site_id: str = "default"  # site name or UUID to store weather under

    # Graph model: sync in-memory graph to data_model.ttl every N minutes
    graph_sync_interval_min: int = 5

    # BACnet/IP driver (rusty-bacnet, embedded) — every scrape cycle
    # reads these from the pydantic settings layer. Container runs with
    # ``network_mode: host`` so the UDP port is bound to the host NIC.
    bacnet_interface: str = "0.0.0.0"
    bacnet_port: int = 47808
    bacnet_broadcast_address: str = "255.255.255.255"
    bacnet_apdu_timeout_ms: int = 6000
    # Optional: this node's BACnet device instance (0-4194303). When
    # unset the driver acts as a pure client; set it to register the
    # driver as a Device object on the network (required for COV
    # subscriptions and some vendor gateways).
    bacnet_device_instance: Optional[int] = None

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

    # SeleneDB migration (Phase 1, strangler flag). Default "timescale" preserves
    # existing behavior; flip to "selene" per-surface as migration phases land.
    # See graph Decision D1 (node 10172) and Milestone 10167.
    storage_backend: str = "timescale"
    selene_url: str = "http://selene:8080"
    selene_identity: Optional[str] = None
    selene_secret: Optional[str] = None
    selene_timeout_sec: float = 10.0
    # Directory of pinned schema pack JSONs (relative to repo root or absolute).
    selene_schema_pack_dir: str = "config/schema_packs"
    # Registration order (pack filenames without extension). Dependencies resolve
    # left-to-right; unlisted packs run last in filesystem order.
    selene_pack_order: str = "hvac-fdd,bacnet-driver"

    model_config = {"env_prefix": "OFDD_", "env_file": ".env"}


def get_platform_settings() -> PlatformSettings:
    """Merge RDF overlay onto env-backed settings.

    The RDF/graph config (``set_config_overlay``) contributes to the
    merged view for keys the settings class knows about; anything
    else is silently dropped. Env wins implicitly because pydantic
    reads env first and the overlay only sets attributes that exist.
    """
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
    return s


def is_selene_backend() -> bool:
    """Shared backend-detection helper used by every strangler branch.

    Returns True when ``OFDD_STORAGE_BACKEND=selene``. Settings lookup is
    wrapped so a misconfigured environment never crashes the hot path —
    callers treat any failure as "assume timescale (rdflib)" and keep going.
    """
    try:
        return (
            getattr(get_platform_settings(), "storage_backend", "timescale") == "selene"
        )
    except Exception:  # noqa: BLE001 — settings error must not break the loop
        return False
