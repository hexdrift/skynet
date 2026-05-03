"""Custom application exception hierarchy.

Each subclass pins a default HTTP status code and a stable ``error_code``
string used by the API exception handlers to render structured error
responses. Domain code raises these instead of bare HTTPException so the
rest of the stack stays framework-agnostic.

The optional ``code`` / ``params`` pair on :class:`AppError` mirrors the
contract of :class:`core.api.errors.DomainError`: when set, the API exception
handler emits them on the wire alongside the English ``detail`` so frontends
can render localised copy from their own catalogs (PER-83).
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
        code: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        """Store the human-readable message plus structured error metadata.

        Args:
            message: English error description shown to the caller as ``detail``.
            status_code: HTTP status code the API layer should return.
            error_code: Stable machine-readable error identifier.
            details: Optional structured context to attach to the response body.
            code: Optional stable i18n key matching :class:`core.i18n_keys.I18nKey`.
                When provided, the exception handler emits ``code`` + ``params``
                on the response so frontends can render localised copy.
            params: Optional substitution params for ``code``. Ignored when
                ``code`` is ``None``.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        self.code = code
        self.params: dict[str, Any] = params or {}


class ServiceError(AppError):
    """Raised when the service_gateway cannot fulfill a request."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        """Initialise with HTTP 500 / ``SERVICE_ERROR`` defaults.

        Args:
            message: English error description.
            details: Optional structured context attached to the response body.
                Keyword-only to match :class:`AppError` and avoid accidentally
                passing a dict in a positional slot.
            code: Optional stable i18n key (see :class:`AppError`).
            params: Optional substitution params for ``code``.
        """
        super().__init__(
            message,
            status_code=500,
            error_code="SERVICE_ERROR",
            details=details,
            code=code,
            params=params,
        )


class ValidationError(AppError):
    """Request validation failed (HTTP 400)."""

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        code: str | None = None,
        params: dict[str, Any] | None = None,
    ):
        """Initialise with HTTP 400 / ``VALIDATION_ERROR`` defaults.

        Args:
            message: English error description.
            details: Optional structured context (e.g. offending field name).
                Keyword-only to match :class:`AppError`.
            code: Optional stable i18n key (see :class:`AppError`).
            params: Optional substitution params for ``code``.
        """
        super().__init__(
            message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details,
            code=code,
            params=params,
        )
