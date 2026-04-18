"""SeleneDB client + schema pack loader.

Stack integration layer for SeleneDB (graph + time-series + vector + RDF in one
runtime). Replaces TimescaleDB + rdflib when ``OFDD_STORAGE_BACKEND=selene``.

Strangler pattern: code paths branch on ``settings.storage_backend``. Phase 1
scope is the client + pack registration only; data-path migration happens in
Phase 2 (semantic model) and Phase 3 (time-series + FDD).
"""

from openfdd_stack.platform.selene.client import SeleneClient
from openfdd_stack.platform.selene.exceptions import (
    SeleneAuthError,
    SeleneConnectionError,
    SeleneError,
    SeleneNotFound,
    SeleneQueryError,
    SeleneValidationError,
)
from openfdd_stack.platform.selene.graph_config import (
    SELENE_CONFIG_LABEL,
    SeleneConfigStore,
    make_selene_client_from_settings,
)
from openfdd_stack.platform.selene.graph_crud import (
    EQUIPMENT_LABEL,
    EXTERNAL_ID_PROP,
    SITE_LABEL,
    delete_equipment,
    delete_site,
    upsert_equipment,
    upsert_site,
)

__all__ = [
    "SeleneClient",
    "SeleneError",
    "SeleneConnectionError",
    "SeleneAuthError",
    "SeleneNotFound",
    "SeleneQueryError",
    "SeleneValidationError",
    "SeleneConfigStore",
    "SELENE_CONFIG_LABEL",
    "make_selene_client_from_settings",
    "SITE_LABEL",
    "EQUIPMENT_LABEL",
    "EXTERNAL_ID_PROP",
    "upsert_site",
    "delete_site",
    "upsert_equipment",
    "delete_equipment",
]
