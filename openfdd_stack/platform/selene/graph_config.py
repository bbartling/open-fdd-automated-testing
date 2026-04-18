"""Platform config persisted as a single SeleneDB node.

Phase 2.1 scope: the ``ofdd:platform_config`` triples that ``graph_model.py``
stores in rdflib become properties on one ``ofdd_platform_config`` node in
Selene. No predicate translation (camelCase) \u2014 Selene stores snake_case keys
directly, matching what ``PlatformSettings`` exposes.

This module is a thin persistence layer. Env precedence, overlay merging, and
settings resolution still happen in ``openfdd_stack.platform.config``.
"""

from __future__ import annotations

import logging
from typing import Any

from openfdd_stack.platform.selene.client import SeleneClient
from openfdd_stack.platform.selene.exceptions import SeleneError

logger = logging.getLogger(__name__)

SELENE_CONFIG_LABEL = "ofdd_platform_config"


class SeleneConfigStore:
    """Read/write the platform config node.

    Boot ordering on a fresh Selene: no node exists. ``read_config()`` returns
    ``{}``; callers seed defaults and call ``write_config(defaults)`` to create
    the node. Subsequent boots see the persisted values.
    """

    def __init__(self, client: SeleneClient, *, label: str = SELENE_CONFIG_LABEL):
        self._client = client
        self._label = label

    def read_config(self) -> dict[str, Any]:
        """Return the config node's properties or ``{}`` if it does not exist."""
        body = self._client.list_nodes(label=self._label, limit=2)
        nodes = body.get("nodes", []) or []
        if not nodes:
            return {}
        if len(nodes) > 1:
            logger.warning(
                "%d %s nodes exist; reading the first (id=%s). "
                "A concurrent PUT /config likely created a duplicate.",
                len(nodes),
                self._label,
                nodes[0].get("id"),
            )
        return dict(nodes[0].get("properties", {}) or {})

    def write_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Upsert the config node with ``config`` as its properties.

        ``None`` values are skipped (Selene would reject them on typed schemas
        and they have no semantic meaning for absent config keys).
        """
        cleaned = {k: v for k, v in config.items() if v is not None}
        body = self._client.list_nodes(label=self._label, limit=1)
        nodes = body.get("nodes", []) or []
        if nodes:
            node_id = nodes[0]["id"]
            existing_props = set((nodes[0].get("properties") or {}).keys())
            incoming_props = set(cleaned.keys())
            # Sort so the wire order is deterministic across runs (easier log
            # diffing + snapshot testing).
            remove = sorted(existing_props - incoming_props)
            return self._client.modify_node(
                node_id,
                set_properties=cleaned,
                remove_properties=remove or None,
            )
        return self._client.create_node([self._label], cleaned)


def make_selene_client_from_settings() -> SeleneClient:
    """Factory that builds a ``SeleneClient`` from ``PlatformSettings``.

    Centralized so every caller (graph_model, API lifespan, future CRUD paths)
    uses the same URL / credentials / timeout. Raises :class:`SeleneError` on
    misconfiguration.
    """
    from openfdd_stack.platform.config import get_platform_settings

    settings = get_platform_settings()
    url = getattr(settings, "selene_url", "") or ""
    if not url:
        raise SeleneError(
            "OFDD_SELENE_URL is empty; cannot construct SeleneClient "
            "(backend is selene but URL was not configured)."
        )
    return SeleneClient(
        url,
        identity=getattr(settings, "selene_identity", None) or None,
        secret=getattr(settings, "selene_secret", None) or None,
        timeout_sec=getattr(settings, "selene_timeout_sec", 10.0) or 10.0,
    )
