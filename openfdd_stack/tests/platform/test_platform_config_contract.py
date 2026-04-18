"""Contract: platform-config layers + precedence.

Three historical layers exist for platform config:

1. **Code defaults** — ``openfdd_stack/platform/default_config.py`` →
   ``DEFAULT_PLATFORM_CONFIG``. Used when the RDF / Selene graph has
   no platform config and for GET /config fallback.

2. **Graph / overlay** — ``set_config_overlay(get_config_from_graph())``
   is the persisted operator-facing config (PUT /config). Lives in
   ``config/data_model.ttl`` (Timescale backend) or the
   ``:ofdd_platform_config`` node (Selene backend).

3. **Process environment** — ``OFDD_*`` vars read directly by pydantic
   at ``PlatformSettings()`` construction.

The legacy ``OFDD_BACNET_SERVER_URL`` env-wins-over-graph contract was
retired in Phase 2.5d — there's no longer a gateway URL; rusty-bacnet
runs in-process. The selene / storage-backend invariants below still
hold.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic_settings")

from openfdd_stack.platform.api.config import get_config
from openfdd_stack.platform.config import get_platform_settings, set_config_overlay


def test_storage_backend_defaults_to_timescale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strangler flag default preserves existing behavior (Decision D1, graph node 10172).

    A fresh deployment with no OFDD_STORAGE_BACKEND set must continue to run against
    TimescaleDB until an operator explicitly flips the backend.
    """
    monkeypatch.delenv("OFDD_STORAGE_BACKEND", raising=False)
    assert get_platform_settings().storage_backend == "timescale"


def test_selene_defaults_point_at_compose_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selene defaults resolve the compose service name (container-internal DNS)."""
    monkeypatch.delenv("OFDD_SELENE_URL", raising=False)
    s = get_platform_settings()
    assert s.selene_url == "http://selene:8080"
    assert s.selene_timeout_sec == 10.0
    assert s.selene_identity is None
    assert s.selene_secret is None


def test_selene_pack_order_contains_pinned_packs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registration order default must list hvac-fdd before bacnet-driver so the
    inheritance chain (bacnet_network extends protocol_network from the same pack)
    and cross-pack deps (bacnet-driver depends_on hvac-fdd) resolve."""
    monkeypatch.delenv("OFDD_SELENE_PACK_ORDER", raising=False)
    order = [s.strip() for s in get_platform_settings().selene_pack_order.split(",")]
    assert order[:2] == ["hvac-fdd", "bacnet-driver"]


def test_bacnet_driver_settings_have_embedded_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rusty-bacnet driver defaults: bind 0.0.0.0:47808 (ASHRAE 135 default)."""
    for k in (
        "OFDD_BACNET_INTERFACE",
        "OFDD_BACNET_PORT",
        "OFDD_BACNET_BROADCAST_ADDRESS",
        "OFDD_BACNET_APDU_TIMEOUT_MS",
    ):
        monkeypatch.delenv(k, raising=False)
    set_config_overlay({})
    s = get_platform_settings()
    assert s.bacnet_interface == "0.0.0.0"
    assert s.bacnet_port == 47808
    assert s.bacnet_broadcast_address == "255.255.255.255"
    assert s.bacnet_apdu_timeout_ms == 6000


def test_bacnet_port_graph_overlay_wins_over_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph overlay can override the port default (operator PUT /config)."""
    monkeypatch.delenv("OFDD_BACNET_PORT", raising=False)
    set_config_overlay({"bacnet_port": 47809})
    try:
        assert get_platform_settings().bacnet_port == 47809
        # And it flows through GET /config response so the UI matches runtime.
        assert get_config()["bacnet_port"] == 47809
    finally:
        set_config_overlay({})
