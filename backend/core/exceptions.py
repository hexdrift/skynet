from __future__ import annotations

from typing import Any

# Domain exceptions that map to HTTP status codes.
# Services raise these instead of HTTPException for clean separation of concerns.


class AppError(Exception):
    """Base exception for all application errors.

    Attributes:
        message: Human-readable error message
        status_code: HTTP status code (default 500)
        error_code: Machine-readable error code
        details: Additional context (optional)
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class ServiceError(AppError):
    """Raised when the service_gateway cannot fulfill a request."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=500,
            error_code="SERVICE_ERROR",
            details=details,
        )


class NotFoundError(AppError):
    """Resource not found (HTTP 404)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=404,
            error_code="NOT_FOUND",
            details=details,
        )


class ValidationError(AppError):
    """Request validation failed (HTTP 400)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class UnauthorizedError(AppError):
    """Authentication required (HTTP 401)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=401,
            error_code="UNAUTHORIZED",
            details=details,
        )


class ForbiddenError(AppError):
    """Access forbidden (HTTP 403)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=403,
            error_code="FORBIDDEN",
            details=details,
        )


class ConflictError(AppError):
    """Resource conflict (HTTP 409)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=409,
            error_code="CONFLICT",
            details=details,
        )


class RateLimitError(AppError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message,
            status_code=429,
            error_code="RATE_LIMIT",
            details=details,
        )
