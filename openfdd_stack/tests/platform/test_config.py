"""Tests for platform config (requires pydantic-settings)."""

import pytest

pytest.importorskip("pydantic_settings")
pytest.importorskip("pydantic")

from openfdd_stack.platform.config import (
    PlatformSettings,
    get_platform_settings,
    set_config_overlay,
)


def test_default_platform_config_keys_match_api():
    """DEFAULT_PLATFORM_CONFIG only has keys allowed by the config API (CONFIG_KEYS); optional keys like bacnet_gateways may be omitted."""
    from openfdd_stack.platform.default_config import DEFAULT_PLATFORM_CONFIG
    from openfdd_stack.platform.api.config import CONFIG_KEYS

    for key in DEFAULT_PLATFORM_CONFIG:
        assert (
            key in CONFIG_KEYS
        ), f"DEFAULT_PLATFORM_CONFIG has extra key not in CONFIG_KEYS: {key}"
    # All non-optional defaults that GET /config should expose when graph is empty
    assert "brick_ttl_dir" in DEFAULT_PLATFORM_CONFIG
    assert "rule_interval_hours" in DEFAULT_PLATFORM_CONFIG
    assert "bacnet_server_url" in DEFAULT_PLATFORM_CONFIG


def test_config_exposes_fdd_rule_settings():
    """GET /config and CONFIG_KEYS include rules_dir, rule_interval_hours, lookback_days so frontend and FDD loop stay in sync."""
    from unittest.mock import patch

    from openfdd_stack.platform.api.config import CONFIG_KEYS, get_config
    from openfdd_stack.platform.default_config import DEFAULT_PLATFORM_CONFIG

    for key in ("rules_dir", "rule_interval_hours", "lookback_days"):
        assert key in CONFIG_KEYS, f"CONFIG_KEYS must include {key} for FDD config"
        assert (
            key in DEFAULT_PLATFORM_CONFIG
        ), f"DEFAULT_PLATFORM_CONFIG must include {key}"
    set_config_overlay({})
    with patch("openfdd_stack.platform.api.config.get_config_from_graph", return_value={}):
        result = get_config()
    assert result["rules_dir"] == "stack/rules"
    assert result["rule_interval_hours"] == 3.0
    assert result["lookback_days"] == 3
    set_config_overlay({})


def test_default_platform_config_values():
    """DEFAULT_PLATFORM_CONFIG has expected default values (brick_ttl_dir, rule_interval_hours, etc.)."""
    from openfdd_stack.platform.default_config import (
        DEFAULT_PLATFORM_CONFIG,
        DEFAULT_BRICK_TTL_DIR,
        DEFAULT_RULE_INTERVAL_HOURS,
        DEFAULT_BACNET_SERVER_URL,
        DEFAULT_GRAPH_SYNC_INTERVAL_MIN,
    )

    assert DEFAULT_PLATFORM_CONFIG["brick_ttl_dir"] == DEFAULT_BRICK_TTL_DIR == "config"
    assert (
        DEFAULT_PLATFORM_CONFIG["rule_interval_hours"]
        == DEFAULT_RULE_INTERVAL_HOURS
        == 3.0
    )
    assert (
        DEFAULT_PLATFORM_CONFIG["bacnet_server_url"]
        == DEFAULT_BACNET_SERVER_URL
        == "http://localhost:8080"
    )
    assert (
        DEFAULT_PLATFORM_CONFIG["graph_sync_interval_min"]
        == DEFAULT_GRAPH_SYNC_INTERVAL_MIN
        == 5
    )
    assert DEFAULT_PLATFORM_CONFIG["rules_dir"] == "stack/rules"
    assert DEFAULT_PLATFORM_CONFIG["bacnet_enabled"] is True
    assert DEFAULT_PLATFORM_CONFIG["open_meteo_timezone"] == "America/Chicago"


def test_get_config_returns_default_when_graph_empty(monkeypatch):
    """When overlay and graph have no config, GET /config returns defaults (env must not skew equality)."""
    from unittest.mock import patch

    from openfdd_stack.platform.api.config import get_config
    from openfdd_stack.platform.default_config import DEFAULT_PLATFORM_CONFIG

    monkeypatch.delenv("OFDD_BACNET_SERVER_URL", raising=False)
    set_config_overlay({})
    with patch("openfdd_stack.platform.api.config.get_config_from_graph", return_value={}):
        result = get_config()
    assert result == DEFAULT_PLATFORM_CONFIG
    set_config_overlay({})


def test_platform_settings_defaults():
    """Platform settings have sensible defaults (env only when overlay empty)."""
    set_config_overlay({})
    s = get_platform_settings()
    assert s.db_dsn.startswith("postgresql://")
    assert s.rule_interval_hours == 3.0
    assert s.lookback_days == 3
    assert s.bacnet_scrape_interval_min == 5
    assert s.open_meteo_interval_hours == 24
    assert s.open_meteo_latitude == 41.88
    assert s.open_meteo_longitude == -87.63
    assert s.open_meteo_site_id == "default"


def test_platform_settings_overlay(monkeypatch):
    """Overlay overrides env for runtime config; OFDD_BACNET_SERVER_URL beats graph bacnet_server_url."""
    monkeypatch.delenv("OFDD_BACNET_SERVER_URL", raising=False)
    set_config_overlay({})
    s = get_platform_settings()
    assert s.rule_interval_hours == 3.0
    set_config_overlay(
        {"rule_interval_hours": 0.1, "bacnet_server_url": "http://localhost:8080"}
    )
    s2 = get_platform_settings()
    assert s2.rule_interval_hours == 0.1
    assert s2.bacnet_server_url == "http://localhost:8080"

    monkeypatch.setenv("OFDD_BACNET_SERVER_URL", "http://192.168.1.50:8080")
    s3 = get_platform_settings()
    assert s3.rule_interval_hours == 0.1
    assert s3.bacnet_server_url == "http://192.168.1.50:8080"

    set_config_overlay({})
    monkeypatch.delenv("OFDD_BACNET_SERVER_URL", raising=False)


def test_config_display_preserves_zero_rule_interval():
    """GET /config normalization must not rewrite explicit 0.0 to default 3.0."""
    from openfdd_stack.platform.api.config import _normalize_config_for_display

    body = _normalize_config_for_display({"rule_interval_hours": 0.0, "lookback_days": 2})
    assert body["rule_interval_hours"] == 0.0
    assert body["lookback_days"] == 2


def test_put_get_round_trip_allows_zero_rule_interval():
    """PUT /config with 0.0 persists and returns 0.0 on GET-style response."""
    from unittest.mock import patch

    from openfdd_stack.platform.api.config import ConfigBody, get_config, put_config

    set_config_overlay({})
    with patch("openfdd_stack.platform.api.config.set_config_in_graph") as _set_graph, patch(
        "openfdd_stack.platform.api.config.write_ttl_to_file", return_value=(True, None)
    ), patch("openfdd_stack.platform.api.config.get_config_from_graph", return_value={}):
        put_config(ConfigBody(rule_interval_hours=0.5))
        body_half = get_config()
        assert body_half["rule_interval_hours"] == 0.5

        put_config(ConfigBody(rule_interval_hours=0.0))
        body_zero = get_config()
        assert body_zero["rule_interval_hours"] == 0.0

        # Ensure persisted payload saw explicit 0.0 rather than defaulting back to 3.0.
        last_persisted = _set_graph.call_args_list[-1].args[0]
        assert last_persisted["rule_interval_hours"] == 0.0

    set_config_overlay({})
