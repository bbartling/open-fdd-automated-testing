"""bacnet_host_gateway — Docker bridge fallback URLs."""

import pytest

from openfdd_stack.platform import bacnet_host_gateway as m


@pytest.fixture(autouse=True)
def _clear_ofdd_bacnet_address_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OFDD_BACNET_ADDRESS", raising=False)


def test_host_http_url_from_bacnet_address_env_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OFDD_BACNET_ADDRESS", raising=False)
    assert m.host_http_url_from_bacnet_address_env() is None


def test_host_http_url_from_bacnet_address_env_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFDD_BACNET_ADDRESS", "192.168.204.18/24:47808")
    assert m.host_http_url_from_bacnet_address_env() == "http://192.168.204.18:8080"


def test_bacnet_rpc_base_candidates_plain_url_no_extra():
    assert m.bacnet_rpc_base_candidates("http://192.168.1.10:8080") == ["http://192.168.1.10:8080"]


def test_bacnet_rpc_base_candidates_adds_from_env_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFDD_BACNET_ADDRESS", "10.0.0.5/24:47808")
    monkeypatch.setattr(m, "linux_default_ipv4_gateway", lambda: "172.20.0.1")
    assert m.bacnet_rpc_base_candidates("http://host.docker.internal:8080") == [
        "http://10.0.0.5:8080",
        m.CADDY_INTERNAL_DIY_BACNET_BASE,
        "http://host.docker.internal:8080",
        "http://172.20.0.1:8080",
    ]


def test_bacnet_rpc_base_candidates_adds_gateway_when_host_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m, "linux_default_ipv4_gateway", lambda: "172.20.0.1")
    assert m.bacnet_rpc_base_candidates("http://host.docker.internal:8080") == [
        m.CADDY_INTERNAL_DIY_BACNET_BASE,
        "http://host.docker.internal:8080",
        "http://172.20.0.1:8080",
    ]


def test_bacnet_rpc_base_candidates_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m, "linux_default_ipv4_gateway", lambda: None)
    assert m.bacnet_rpc_base_candidates("http://host.docker.internal:8080") == [
        m.CADDY_INTERNAL_DIY_BACNET_BASE,
        "http://host.docker.internal:8080",
    ]


def test_bacnet_rpc_base_candidates_dedupes_lan_same_as_gateway_swap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFDD_BACNET_ADDRESS", "172.20.0.1/16:47808")
    monkeypatch.setattr(m, "linux_default_ipv4_gateway", lambda: "172.20.0.1")
    assert m.bacnet_rpc_base_candidates("http://host.docker.internal:8080") == [
        "http://172.20.0.1:8080",
        m.CADDY_INTERNAL_DIY_BACNET_BASE,
        "http://host.docker.internal:8080",
    ]


def test_bacnet_rpc_base_candidates_lan_first_when_primary_is_caddy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OFDD_BACNET_ADDRESS", "10.0.0.5/24:47808")
    assert m.bacnet_rpc_base_candidates(m.CADDY_INTERNAL_DIY_BACNET_BASE) == [
        "http://10.0.0.5:8080",
        m.CADDY_INTERNAL_DIY_BACNET_BASE,
    ]


def test_bacnet_rpc_base_candidates_empty():
    assert m.bacnet_rpc_base_candidates("") == []
    assert m.bacnet_rpc_base_candidates("   ") == []
