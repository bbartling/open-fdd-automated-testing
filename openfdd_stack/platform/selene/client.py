"""SeleneDB HTTP client.

Thin synchronous ``httpx`` wrapper around the documented SeleneDB HTTP API.
Mirrors the MCP tool surface names (``ts_write``, ``ts_range``, ``gql``,
``semantic_search``) so stack code that reads fine against MCP tooling in
docs reads fine against this client.

Auth: Bearer ``<identity>:<secret>`` when both are set. When neither is set,
no ``Authorization`` header is sent — works in Selene ``dev_mode``.

Concurrency: synchronous. The stack is synchronous psycopg2-style; matching
that pattern avoids async-bleed into the existing data-path modules. Future
async client can share the same method surface.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

import httpx

from openfdd_stack.platform.selene.exceptions import (
    SeleneAuthError,
    SeleneConnectionError,
    SeleneError,
    SeleneNotFound,
    SeleneQueryError,
    SeleneValidationError,
)

logger = logging.getLogger(__name__)

GQLSTATUS_OK = "00000"
GQLSTATUS_NO_DATA = "02000"


class SeleneClient:
    """Synchronous client for a single SeleneDB instance.

    >>> client = SeleneClient("http://selene:8080", identity="admin", secret="dev")
    >>> client.health()
    {'status': 'ok', ...}
    """

    def __init__(
        self,
        url: str,
        *,
        identity: str | None = None,
        secret: str | None = None,
        timeout_sec: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self._identity = identity
        self._secret = secret
        self._timeout = timeout_sec
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_sec)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SeleneClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Request plumbing
    # ------------------------------------------------------------------

    def _headers(self, *, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._identity and self._secret:
            headers["Authorization"] = f"Bearer {self._identity}:{self._secret}"
        if extra:
            headers.update(extra)
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        content: bytes | str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        url = f"{self.url}{path}"
        try:
            response = self._client.request(
                method,
                url,
                json=json,
                params=params,
                content=content,
                headers=self._headers(extra=extra_headers),
            )
        except httpx.TimeoutException as exc:
            raise SeleneConnectionError(
                f"timeout contacting {method} {url}: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SeleneConnectionError(
                f"network error contacting {method} {url}: {exc}"
            ) from exc
        self._raise_for_status(response)
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        """Decode ``response.json()`` or raise :class:`SeleneError`.

        Keeps the typed-exception contract when a proxy or misconfigured Selene
        returns non-JSON (HTML error pages, plaintext, truncated bodies).
        """
        try:
            return response.json()
        except ValueError as exc:
            snippet = response.text[:200]
            raise SeleneError(
                f"invalid JSON from {response.request.method} "
                f"{response.request.url.path} ({response.status_code}): {snippet!r}"
            ) from exc

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        content: bytes | str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Same as ``_request`` but decodes the JSON body with typed errors."""
        response = self._request(
            method,
            path,
            json=json,
            params=params,
            content=content,
            extra_headers=extra_headers,
        )
        return self._json(response)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = response.text
        # Try to pull the standard {"error": "..."} body
        try:
            body = response.json()
            if isinstance(body, dict) and "error" in body:
                detail = body["error"]
        except Exception:  # noqa: BLE001 - fall back to raw text
            pass
        status = response.status_code
        if status in (401, 403):
            raise SeleneAuthError(detail)
        if status == 404:
            raise SeleneNotFound(detail)
        if status in (400, 422):
            raise SeleneValidationError(detail)
        raise SeleneError(f"{status} {detail}")

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """GET /health — returns uptime and (when authenticated) graph counts."""
        return self._request_json("GET", "/health")

    # ------------------------------------------------------------------
    # GQL
    # ------------------------------------------------------------------

    def gql(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        *,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        """Execute a GQL query or mutation.

        Returns the full response body: ``{status, message, row_count, data, mutations?}``.
        Raises :class:`SeleneQueryError` when ``status`` is not ``00000``/``02000``.
        """
        payload: dict[str, Any] = {"query": query}
        if parameters is not None:
            payload["parameters"] = parameters
        if timeout_ms is not None:
            payload["timeout_ms"] = timeout_ms
        body = self._request_json("POST", "/gql", json=payload)
        if not isinstance(body, dict):
            raise SeleneError(
                f"expected JSON object from POST /gql, got {type(body).__name__}"
            )
        status = body.get("status", "")
        if status not in (GQLSTATUS_OK, GQLSTATUS_NO_DATA):
            raise SeleneQueryError(
                body.get("message", "GQL query failed"), status=status
            )
        return body

    def gql_rows(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        *,
        timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        """Convenience: run a read-only query and return only the ``data`` array."""
        return self.gql(query, parameters, timeout_ms=timeout_ms).get("data", []) or []

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    def get_node(self, node_id: int) -> dict[str, Any]:
        return self._request_json("GET", f"/nodes/{node_id}")

    def list_nodes(
        self,
        *,
        label: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Returns ``{nodes: [...], total: N}``."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if label:
            params["label"] = label
        return self._request_json("GET", "/nodes", params=params)

    def create_node(
        self,
        labels: list[str],
        properties: dict[str, Any] | None = None,
        *,
        parent_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "labels": labels,
            "properties": properties or {},
        }
        if parent_id is not None:
            payload["parent_id"] = parent_id
        return self._request_json("POST", "/nodes", json=payload)

    def modify_node(
        self,
        node_id: int,
        *,
        set_properties: dict[str, Any] | None = None,
        remove_properties: list[str] | None = None,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if set_properties is not None:
            payload["set_properties"] = set_properties
        if remove_properties is not None:
            payload["remove_properties"] = remove_properties
        if add_labels is not None:
            payload["add_labels"] = add_labels
        if remove_labels is not None:
            payload["remove_labels"] = remove_labels
        return self._request_json("PUT", f"/nodes/{node_id}", json=payload)

    def delete_node(self, node_id: int) -> None:
        self._request("DELETE", f"/nodes/{node_id}")

    # ------------------------------------------------------------------
    # Edge CRUD
    # ------------------------------------------------------------------

    def create_edge(
        self,
        source: int,
        target: int,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "source": source,
            "target": target,
            "label": label,
            "properties": properties or {},
        }
        return self._request_json("POST", "/edges", json=payload)

    def list_edges(
        self,
        *,
        label: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if label:
            params["label"] = label
        return self._request_json("GET", "/edges", params=params)

    # ------------------------------------------------------------------
    # Time-series
    # ------------------------------------------------------------------

    def ts_write(self, samples: Iterable[dict[str, Any]]) -> int:
        """POST /ts/write. Each sample: ``{entity_id, property, timestamp_nanos, value}``.

        Returns the count the server confirmed written.
        """
        payload = {"samples": list(samples)}
        body = self._request_json("POST", "/ts/write", json=payload)
        if not isinstance(body, dict):
            raise SeleneError(
                f"expected JSON object from POST /ts/write, got {type(body).__name__}"
            )
        return int(body.get("written", 0))

    def ts_range(
        self,
        entity_id: int,
        property_name: str,
        *,
        start_nanos: int | None = None,
        end_nanos: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Raw samples for (entity_id, property) in [start, end].

        Uses the REST ``GET /ts/{id}/{property}`` endpoint, which returns a
        bare JSON array per the HTTP reference.
        """
        params: dict[str, Any] = {}
        if start_nanos is not None:
            params["start"] = start_nanos
        if end_nanos is not None:
            params["end"] = end_nanos
        if limit is not None:
            params["limit"] = limit
        body = self._request_json(
            "GET", f"/ts/{entity_id}/{property_name}", params=params
        )
        # Server returns an array of samples; tolerate a future wrapped shape.
        if isinstance(body, list):
            return body
        if isinstance(body, dict) and "samples" in body:
            return body["samples"]
        return []

    def ts_latest(self, entity_id: int, property_name: str) -> dict[str, Any] | None:
        """Single most recent sample via ``CALL ts.latest``."""
        rows = self.gql_rows(
            "CALL ts.latest($entity_id, $property) YIELD timestamp, value",
            {"entity_id": entity_id, "property": property_name},
        )
        return rows[0] if rows else None

    # ------------------------------------------------------------------
    # Vector / semantic
    # ------------------------------------------------------------------

    def semantic_search(
        self,
        query_text: str,
        *,
        k: int = 10,
        label: str | None = None,
    ) -> list[dict[str, Any]]:
        """HNSW semantic search via ``CALL semantic.search``.

        Thin wrapper; caller enriches with ``get_node`` for full properties.
        """
        params: dict[str, Any] = {"q": query_text, "k": k}
        query = "CALL semantic.search($q, $k"
        if label:
            query += ", $label"
            params["label"] = label
        query += ") YIELD node_id, score"
        return self.gql_rows(query, params)

    # ------------------------------------------------------------------
    # Schemas
    # ------------------------------------------------------------------

    def list_schemas(self) -> dict[str, Any]:
        return self._request_json("GET", "/schemas")

    def register_node_schema(
        self,
        label: str,
        properties: list[dict[str, Any]],
        *,
        description: str | None = None,
        valid_edge_labels: list[str] | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /schemas/nodes. Idempotent per Selene docs (replaces on match)."""
        payload: dict[str, Any] = {"label": label, "properties": properties}
        if description is not None:
            payload["description"] = description
        if valid_edge_labels is not None:
            payload["valid_edge_labels"] = valid_edge_labels
        if annotations is not None:
            payload["annotations"] = annotations
        return self._request_json("POST", "/schemas/nodes", json=payload)

    def register_edge_schema(
        self,
        label: str,
        *,
        properties: list[dict[str, Any]] | None = None,
        description: str | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"label": label, "properties": properties or []}
        if description is not None:
            payload["description"] = description
        if annotations is not None:
            payload["annotations"] = annotations
        return self._request_json("POST", "/schemas/edges", json=payload)
