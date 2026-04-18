"""Contract: where platform / BACnet URL configuration comes from (AI + operator context).

Historically three layers existed without a single written contract, which caused bugs:

1. **Code defaults** — ``openfdd_stack/platform/default_config.py`` → ``DEFAULT_PLATFORM_CONFIG``
   (e.g. ``bacnet_server_url: http://localhost:8080``). Used when the RDF graph has no platform
   config and for GET /config fallback.

2. **RDF graph / ``config/data_model.ttl``** — ``ofdd:bacnetServerUrl`` is loaded at API startup into
   ``set_config_overlay(get_config_from_graph())``. That value is the **persisted** operator-facing
   config (PUT /config) and matches SPARQL / knowledge-graph workflows.

3. **Process environment** — ``OFDD_BACNET_SERVER_URL`` in ``stack/.env``, injected by Docker Compose.
   In containers, ``localhost`` in the graph points at the **container**, not the host. Docker stacks
   therefore **must** set ``OFDD_BACNET_SERVER_URL`` to a host-reachable URL (LAN IP, host-gateway, etc.).

**Contract (after regression fixes):**

- ``get_platform_settings()``: after merging the RDF overlay onto Pydantic env, if
  ``OFDD_BACNET_SERVER_URL`` is set in ``os.environ``, it **re-applies** and wins over
  ``bacnet_server_url`` from the graph (``openfdd_stack/platform/config.py``).

- ``GET /config``: response is normalized for display; ``OFDD_BACNET_SERVER_URL`` overrides the
  returned ``bacnet_server_url`` so the Config UI matches runtime (``api/config.py``).

- ``_effective_bacnet_server_url()`` (BACnet proxy): already preferred ``os.environ`` first; it must
  stay aligned with ``get_platform_settings().bacnet_server_url`` for the default gateway.

**What is *not* duplicated incorrectly:** keeping ``http://localhost:8080`` in the TTL for dev
machines is fine; production Docker must set ``OFDD_BACNET_SERVER_URL``. The tests below lock
precedence so graph-only localhost cannot silently override compose again.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic_settings")

from openfdd_stack.platform.api.bacnet import _effective_bacnet_server_url
from openfdd_stack.platform.api.config import get_config
from openfdd_stack.platform.config import get_platform_settings, set_config_overlay


def test_effective_bacnet_url_matches_get_platform_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default gateway URL resolution must agree between BACnet proxy and merged settings."""
    monkeypatch.setenv("OFDD_BACNET_SERVER_URL", "http://gateway-contract.test:8080")
    set_config_overlay({"bacnet_server_url": "http://localhost:8080"})
    try:
        s = get_platform_settings()
        assert s.bacnet_server_url == "http://gateway-contract.test:8080"
        assert _effective_bacnet_server_url() == s.bacnet_server_url
    finally:
        set_config_overlay({})
        monkeypatch.delenv("OFDD_BACNET_SERVER_URL", raising=False)


def test_get_config_display_overrides_graph_bacnet_url_with_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /config must show the same BACnet URL the API uses when OFDD_BACNET_SERVER_URL is set."""
    monkeypatch.setenv("OFDD_BACNET_SERVER_URL", "http://192.168.204.99:8080")
    set_config_overlay(
        {
            "bacnet_server_url": "http://localhost:8080",
            "bacnet_site_id": "default",
            "rule_interval_hours": 3.0,
        }
    )
    try:
        body = get_config()
        assert body["bacnet_server_url"] == "http://192.168.204.99:8080"
    finally:
        set_config_overlay({})
        monkeypatch.delenv("OFDD_BACNET_SERVER_URL", raising=False)


def test_default_platform_config_constant_matches_graph_dev_literal() -> None:
    """DEFAULT_PLATFORM_CONFIG and typical data_model.ttl both use localhost for host-side dev."""
    from openfdd_stack.platform.default_config import (
        DEFAULT_BACNET_SERVER_URL,
        DEFAULT_PLATFORM_CONFIG,
    )

    assert DEFAULT_PLATFORM_CONFIG["bacnet_server_url"] == DEFAULT_BACNET_SERVER_URL
    assert DEFAULT_BACNET_SERVER_URL == "http://localhost:8080"


def test_graph_only_bacnet_url_used_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without OFDD_BACNET_SERVER_URL, graph overlay is authoritative for settings and GET /config."""
    monkeypatch.delenv("OFDD_BACNET_SERVER_URL", raising=False)
    set_config_overlay({"bacnet_server_url": "http://graph-only.example:8080"})
    try:
        assert (
            get_platform_settings().bacnet_server_url
            == "http://graph-only.example:8080"
        )
        assert get_config()["bacnet_server_url"] == "http://graph-only.example:8080"
    finally:
        set_config_overlay({})


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
