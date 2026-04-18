"""Canonical default platform config for Open-FDD.

Used when the graph has no config yet (GET /config fallback), by the test script
for PUT /config (mock setup), and by bootstrap. All CRUD config (GET/PUT/PATCH) uses
the same graph; this dict is the default state so the app and tests stay in sync.
"""

# AFDD rule running
DEFAULT_RULE_INTERVAL_HOURS = 3.0  # Production default; FDD loop runs every N hours
DEFAULT_LOOKBACK_DAYS = 3
DEFAULT_RULES_DIR = "stack/rules"

# Brick / data model TTL location
DEFAULT_BRICK_TTL_DIR = "config"

# BACnet/IP driver (rusty-bacnet, embedded).
# Docker: container runs ``network_mode: host`` so the UDP port is
# bound to the host NIC; override via ``OFDD_BACNET_*`` env vars.
DEFAULT_BACNET_ENABLED = True
DEFAULT_BACNET_SCRAPE_INTERVAL_MIN = 1  # 5 in production
DEFAULT_BACNET_INTERFACE = "0.0.0.0"
DEFAULT_BACNET_PORT = 47808
DEFAULT_BACNET_BROADCAST_ADDRESS = "255.255.255.255"
DEFAULT_BACNET_APDU_TIMEOUT_MS = 6000

# Open-Meteo weather
DEFAULT_OPEN_METEO_ENABLED = True
DEFAULT_OPEN_METEO_INTERVAL_HOURS = 24
DEFAULT_OPEN_METEO_LATITUDE = 41.88
DEFAULT_OPEN_METEO_LONGITUDE = -87.63
DEFAULT_OPEN_METEO_TIMEZONE = "America/Chicago"
DEFAULT_OPEN_METEO_DAYS_BACK = 3
DEFAULT_OPEN_METEO_SITE_ID = "default"

# Graph sync to TTL file
DEFAULT_GRAPH_SYNC_INTERVAL_MIN = 5

# Full dict for PUT /config and GET /config fallback (snake_case keys for API)
DEFAULT_PLATFORM_CONFIG: dict = {
    "rule_interval_hours": DEFAULT_RULE_INTERVAL_HOURS,
    "lookback_days": DEFAULT_LOOKBACK_DAYS,
    "rules_dir": DEFAULT_RULES_DIR,
    "brick_ttl_dir": DEFAULT_BRICK_TTL_DIR,
    "bacnet_enabled": DEFAULT_BACNET_ENABLED,
    "bacnet_scrape_interval_min": DEFAULT_BACNET_SCRAPE_INTERVAL_MIN,
    "bacnet_interface": DEFAULT_BACNET_INTERFACE,
    "bacnet_port": DEFAULT_BACNET_PORT,
    "bacnet_broadcast_address": DEFAULT_BACNET_BROADCAST_ADDRESS,
    "bacnet_apdu_timeout_ms": DEFAULT_BACNET_APDU_TIMEOUT_MS,
    "open_meteo_enabled": DEFAULT_OPEN_METEO_ENABLED,
    "open_meteo_interval_hours": DEFAULT_OPEN_METEO_INTERVAL_HOURS,
    "open_meteo_latitude": DEFAULT_OPEN_METEO_LATITUDE,
    "open_meteo_longitude": DEFAULT_OPEN_METEO_LONGITUDE,
    "open_meteo_timezone": DEFAULT_OPEN_METEO_TIMEZONE,
    "open_meteo_days_back": DEFAULT_OPEN_METEO_DAYS_BACK,
    "open_meteo_site_id": DEFAULT_OPEN_METEO_SITE_ID,
    "graph_sync_interval_min": DEFAULT_GRAPH_SYNC_INTERVAL_MIN,
}
