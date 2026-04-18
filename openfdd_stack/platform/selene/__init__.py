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

__all__ = [
    "SeleneClient",
    "SeleneError",
    "SeleneConnectionError",
    "SeleneAuthError",
    "SeleneNotFound",
    "SeleneQueryError",
    "SeleneValidationError",
]
