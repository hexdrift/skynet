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
        """Initialize the application error with HTTP metadata.

        Args:
            message: Human-readable description of the error.
            status_code: HTTP status code to return (default 500).
            error_code: Machine-readable error code string (default ``"INTERNAL_ERROR"``).
            details: Optional dict with additional context about the error.
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}


class ServiceError(AppError):
    """Raised when the service_gateway cannot fulfill a request."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize with status 500 and error code ``SERVICE_ERROR``."""
        super().__init__(
            message,
            status_code=500,
            error_code="SERVICE_ERROR",
            details=details,
        )


class NotFoundError(AppError):
    """Resource not found (HTTP 404)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize with status 404 and error code ``NOT_FOUND``."""
        super().__init__(
            message,
            status_code=404,
            error_code="NOT_FOUND",
            details=details,
        )


class ValidationError(AppError):
    """Request validation failed (HTTP 400)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize with status 400 and error code ``VALIDATION_ERROR``."""
        super().__init__(
            message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details=details,
        )


class UnauthorizedError(AppError):
    """Authentication required (HTTP 401)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize with status 401 and error code ``UNAUTHORIZED``."""
        super().__init__(
            message,
            status_code=401,
            error_code="UNAUTHORIZED",
            details=details,
        )


class ForbiddenError(AppError):
    """Access forbidden (HTTP 403)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize with status 403 and error code ``FORBIDDEN``."""
        super().__init__(
            message,
            status_code=403,
            error_code="FORBIDDEN",
            details=details,
        )


class ConflictError(AppError):
    """Resource conflict (HTTP 409)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize with status 409 and error code ``CONFLICT``."""
        super().__init__(
            message,
            status_code=409,
            error_code="CONFLICT",
            details=details,
        )


class RateLimitError(AppError):
    """Rate limit exceeded (HTTP 429)."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize with status 429 and error code ``RATE_LIMIT``."""
        super().__init__(
            message,
            status_code=429,
            error_code="RATE_LIMIT",
            details=details,
        )
