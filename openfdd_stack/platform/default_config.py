"""Canonical default platform config for Open-FDD.

Used when the graph has no config yet (GET /config fallback), by the test script
for PUT /config (mock setup), and by bootstrap. All CRUD config (GET/PUT/PATCH) uses
the same graph; this dict is the default state so the app and tests stay in sync.
"""

# AFDD rule running
DEFAULT_RULE_INTERVAL_HOURS = 3.0  # Production default; FDD loop runs every N hours
DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_FDD_BACKFILL_ENABLED = False
DEFAULT_FDD_BACKFILL_START = None
DEFAULT_FDD_BACKFILL_END = None
DEFAULT_FDD_BACKFILL_STEP_HOURS = 3
DEFAULT_RULES_DIR = "stack/rules"

# Brick / data model TTL location
DEFAULT_BRICK_TTL_DIR = "config"

# BACnet driver — host-side dev default (browser on same machine as diy-bacnet).
# Docker: set OFDD_BACNET_SERVER_URL in stack/.env (overrides graph + this default at runtime).
DEFAULT_BACNET_ENABLED = True
DEFAULT_BACNET_SCRAPE_INTERVAL_MIN = 5
DEFAULT_BACNET_SERVER_URL = "http://caddy:8081"
DEFAULT_BACNET_SITE_ID = "default"
DEFAULT_BACNET_GATEWAYS = ""  # JSON array of gateways; future multi-gateway feature

# Open-Meteo weather
DEFAULT_OPEN_METEO_ENABLED = True
DEFAULT_OPEN_METEO_INTERVAL_HOURS = 24
DEFAULT_OPEN_METEO_LATITUDE = 41.88
DEFAULT_OPEN_METEO_LONGITUDE = -87.63
DEFAULT_OPEN_METEO_TIMEZONE = "America/Chicago"
DEFAULT_OPEN_METEO_DAYS_BACK = 3
DEFAULT_OPEN_METEO_SITE_ID = "default"

# Onboard API
DEFAULT_ONBOARD_ENABLED = False
DEFAULT_ONBOARD_API_BASE_URL = "https://api.onboarddata.io"
DEFAULT_ONBOARD_BUILDING_IDS = ""
DEFAULT_ONBOARD_SCRAPE_INTERVAL_MIN = 180
DEFAULT_ONBOARD_BACKFILL_START = None
DEFAULT_ONBOARD_BACKFILL_END = None
DEFAULT_ONBOARD_SITE_ID_STRATEGY = "onboard-building-id"
DEFAULT_ONBOARD_CREATE_POINTS = True

# CSV ingestion
DEFAULT_CSV_ENABLED = False
DEFAULT_CSV_SOURCES = ""
DEFAULT_CSV_SCRAPE_INTERVAL_MIN = 180
DEFAULT_CSV_BACKFILL_START = None
DEFAULT_CSV_BACKFILL_END = None
DEFAULT_CSV_CREATE_POINTS = True

# Graph sync to TTL file
DEFAULT_GRAPH_SYNC_INTERVAL_MIN = 5

# Full dict for PUT /config and GET /config fallback (snake_case keys for API)
DEFAULT_PLATFORM_CONFIG: dict = {
    "rule_interval_hours": DEFAULT_RULE_INTERVAL_HOURS,
    "lookback_days": DEFAULT_LOOKBACK_DAYS,
    "fdd_backfill_enabled": DEFAULT_FDD_BACKFILL_ENABLED,
    "fdd_backfill_start": DEFAULT_FDD_BACKFILL_START,
    "fdd_backfill_end": DEFAULT_FDD_BACKFILL_END,
    "fdd_backfill_step_hours": DEFAULT_FDD_BACKFILL_STEP_HOURS,
    "rules_dir": DEFAULT_RULES_DIR,
    "brick_ttl_dir": DEFAULT_BRICK_TTL_DIR,
    "bacnet_enabled": DEFAULT_BACNET_ENABLED,
    "bacnet_scrape_interval_min": DEFAULT_BACNET_SCRAPE_INTERVAL_MIN,
    "bacnet_server_url": DEFAULT_BACNET_SERVER_URL,
    "bacnet_site_id": DEFAULT_BACNET_SITE_ID,
    "bacnet_gateways": DEFAULT_BACNET_GATEWAYS,
    "open_meteo_enabled": DEFAULT_OPEN_METEO_ENABLED,
    "open_meteo_interval_hours": DEFAULT_OPEN_METEO_INTERVAL_HOURS,
    "open_meteo_latitude": DEFAULT_OPEN_METEO_LATITUDE,
    "open_meteo_longitude": DEFAULT_OPEN_METEO_LONGITUDE,
    "open_meteo_timezone": DEFAULT_OPEN_METEO_TIMEZONE,
    "open_meteo_days_back": DEFAULT_OPEN_METEO_DAYS_BACK,
    "open_meteo_site_id": DEFAULT_OPEN_METEO_SITE_ID,
    "onboard_enabled": DEFAULT_ONBOARD_ENABLED,
    "onboard_api_base_url": DEFAULT_ONBOARD_API_BASE_URL,
    "onboard_building_ids": DEFAULT_ONBOARD_BUILDING_IDS,
    "onboard_scrape_interval_min": DEFAULT_ONBOARD_SCRAPE_INTERVAL_MIN,
    "onboard_backfill_start": DEFAULT_ONBOARD_BACKFILL_START,
    "onboard_backfill_end": DEFAULT_ONBOARD_BACKFILL_END,
    "onboard_site_id_strategy": DEFAULT_ONBOARD_SITE_ID_STRATEGY,
    "onboard_create_points": DEFAULT_ONBOARD_CREATE_POINTS,
    "csv_enabled": DEFAULT_CSV_ENABLED,
    "csv_sources": DEFAULT_CSV_SOURCES,
    "csv_scrape_interval_min": DEFAULT_CSV_SCRAPE_INTERVAL_MIN,
    "csv_backfill_start": DEFAULT_CSV_BACKFILL_START,
    "csv_backfill_end": DEFAULT_CSV_BACKFILL_END,
    "csv_create_points": DEFAULT_CSV_CREATE_POINTS,
    "graph_sync_interval_min": DEFAULT_GRAPH_SYNC_INTERVAL_MIN,
}
