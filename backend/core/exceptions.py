"""Custom application exception hierarchy.

Each subclass pins a default HTTP status code and a stable ``error_code``
string used by the API exception handlers to render structured error
responses. Domain code raises these instead of bare HTTPException so the
rest of the stack stays framework-agnostic.
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
    ):
        """Store the human-readable message plus structured error metadata.

        Args:
            message: Human-readable error description shown to the caller.
            status_code: HTTP status code the API layer should return.
            error_code: Stable machine-readable error identifier.
            details: Optional structured context to attach to the response body.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class ServiceError(AppError):
    """Raised when the service_gateway cannot fulfill a request."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialise with HTTP 500 / ``SERVICE_ERROR`` defaults.

        Args:
            message: Human-readable error description.
            details: Optional structured context.
        """
        super().__init__(
            message,
            status_code=500,
            error_code="SERVICE_ERROR",
            details=details,
        )


class NotFoundError(AppError):
    """Resource not found (HTTP 404)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialise with HTTP 404 / ``NOT_FOUND`` defaults.

        Args:
            message: Human-readable error description.
            details: Optional structured context.
        """
        super().__init__(
            message,
            status_code=404,
            error_code="NOT_FOUND",
            details=details,
        )


class ValidationError(AppError):
    """Request validation failed (HTTP 400)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialise with HTTP 400 / ``VALIDATION_ERROR`` defaults.

        Args:
            message: Human-readable error description.
            details: Optional structured context.
        """
        super().__init__(
            message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class UnauthorizedError(AppError):
    """Authentication required (HTTP 401)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialise with HTTP 401 / ``UNAUTHORIZED`` defaults.

        Args:
            message: Human-readable error description.
            details: Optional structured context.
        """
        super().__init__(
            message,
            status_code=401,
            error_code="UNAUTHORIZED",
            details=details,
        )


class ForbiddenError(AppError):
    """Access forbidden (HTTP 403)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialise with HTTP 403 / ``FORBIDDEN`` defaults.

        Args:
            message: Human-readable error description.
            details: Optional structured context.
        """
        super().__init__(
            message,
            status_code=403,
            error_code="FORBIDDEN",
            details=details,
        )


class ConflictError(AppError):
    """Resource conflict (HTTP 409)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialise with HTTP 409 / ``CONFLICT`` defaults.

        Args:
            message: Human-readable error description.
            details: Optional structured context.
        """
        super().__init__(
            message,
            status_code=409,
            error_code="CONFLICT",
            details=details,
        )


class RateLimitError(AppError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialise with HTTP 429 / ``RATE_LIMIT`` defaults.

        Args:
            message: Human-readable error description.
            details: Optional structured context.
        """
        super().__init__(
            message,
            status_code=429,
            error_code="RATE_LIMIT",
            details=details,
        )
