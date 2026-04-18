"""SeleneDB client exception hierarchy."""

from __future__ import annotations


class SeleneError(Exception):
    """Base for all SeleneDB client errors."""


class SeleneConnectionError(SeleneError):
    """Network failure, DNS, timeout, or unreachable server."""


class SeleneAuthError(SeleneError):
    """401/403. Missing, invalid, or insufficient credentials."""


class SeleneNotFound(SeleneError):
    """404. Entity (node, edge, schema, time-series) not found."""


class SeleneValidationError(SeleneError):
    """400/422. Malformed request or schema validation failure."""


class SeleneQueryError(SeleneError):
    """GQL returned a non-zero GQLSTATUS, or other 4xx/5xx where the request
    parsed but the operation could not complete."""

    def __init__(self, message: str, status: str | None = None) -> None:
        super().__init__(message)
        self.status = status
