"""GET /data-model/ttl when OFDD_STORAGE_BACKEND=selene.

Confirms the handler short-circuits the rdflib/Postgres paths and asks Selene
for the RDF export directly. Uses httpx.MockTransport so the test never hits
a live Selene — the Selene client factory in ``openfdd_stack.platform.api``
is patched to hand back a MockTransport-backed client.
"""

from __future__ import annotations

import httpx
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from openfdd_stack.platform.api import data_model as data_model_api
from openfdd_stack.platform.api.main import app
from openfdd_stack.platform.selene import SeleneClient

client = TestClient(app)


def _mock_selene(handler) -> SeleneClient:
    return SeleneClient(
        "http://selene.local:8080",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        owns_client=True,
    )


_SAMPLE_TTL = """@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix : <http://openfdd.local/site#> .

:default a brick:Site ;
    rdfs:label "Default" .
"""


def test_get_ttl_returns_selene_export_when_backend_is_selene(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/graph/rdf"
        assert request.url.params.get("format") == "turtle"
        assert request.headers.get("Accept") == "text/turtle"
        return httpx.Response(
            200,
            content=_SAMPLE_TTL.encode(),
            headers={"content-type": "text/turtle"},
        )

    selene_client = _mock_selene(handler)
    monkeypatch.setattr(
        "openfdd_stack.platform.selene.make_selene_client_from_settings",
        lambda: selene_client,
    )

    r = client.get("/data-model/ttl")
    assert r.status_code == 200
    assert "text/turtle" in r.headers.get("content-type", "")
    assert r.text == _SAMPLE_TTL
    # Selene path ignores ``save`` and ``site_id`` — no X-TTL-Save header
    # because no file write is attempted.
    assert "x-ttl-save" not in {k.lower() for k in r.headers.keys()}


def test_get_ttl_returns_502_when_selene_export_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """Selene error should surface as a gateway error, not a 500 trace."""
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "selene")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "graph export failed"})

    selene_client = _mock_selene(handler)
    monkeypatch.setattr(
        "openfdd_stack.platform.selene.make_selene_client_from_settings",
        lambda: selene_client,
    )

    r = client.get("/data-model/ttl")
    assert r.status_code == 502
    # Stack's error middleware wraps HTTPException detail into
    # ``{"error": {"message": ...}}``; the selene failure text must propagate.
    assert "selene rdf export failed" in r.json()["error"]["message"]


def test_get_ttl_skips_selene_when_backend_is_timescale(
    monkeypatch: pytest.MonkeyPatch,
):
    """Timescale mode must keep the rdflib + Postgres path untouched.

    Patching the Selene factory to raise ensures the handler never reaches it
    — if it did, the test would 500 with RuntimeError.
    """
    monkeypatch.setenv("OFDD_STORAGE_BACKEND", "timescale")

    def boom() -> None:
        raise RuntimeError("should not be called on timescale")

    monkeypatch.setattr(
        "openfdd_stack.platform.selene.make_selene_client_from_settings",
        boom,
    )

    # Stub the DB + graph path so the handler returns 200 without real deps.
    monkeypatch.setattr(data_model_api, "serialize_to_ttl", lambda: _SAMPLE_TTL)
    monkeypatch.setattr(
        data_model_api,
        "write_ttl_to_file",
        lambda: (True, None),
    )

    r = client.get("/data-model/ttl?save=false")
    assert r.status_code == 200
    assert r.text == _SAMPLE_TTL
