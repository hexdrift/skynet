"""Tests for core.exceptions custom exception hierarchy."""

from __future__ import annotations

import pytest

from core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServiceError,
    UnauthorizedError,
    ValidationError,
)


def test_app_error_stores_message() -> None:
    """``AppError.message`` returns the constructor argument verbatim."""
    exc = AppError("something went wrong")

    assert exc.message == "something went wrong"


def test_app_error_default_status_code() -> None:
    """``AppError`` defaults to HTTP 500."""
    exc = AppError("oops")

    assert exc.status_code == 500


def test_app_error_default_error_code() -> None:
    """``AppError`` defaults to ``error_code='INTERNAL_ERROR'``."""
    exc = AppError("oops")

    assert exc.error_code == "INTERNAL_ERROR"


def test_app_error_default_details_is_empty_dict() -> None:
    """``AppError.details`` defaults to an empty dict."""
    exc = AppError("oops")

    assert exc.details == {}


def test_app_error_custom_status_code() -> None:
    """``AppError`` accepts a custom ``status_code``."""
    exc = AppError("custom", status_code=418)

    assert exc.status_code == 418


def test_app_error_custom_error_code() -> None:
    """``AppError`` accepts a custom ``error_code``."""
    exc = AppError("custom", error_code="MY_CODE")

    assert exc.error_code == "MY_CODE"


def test_app_error_custom_details() -> None:
    """``AppError`` stores caller-provided ``details`` verbatim."""
    exc = AppError("custom", details={"field": "name", "reason": "too long"})

    assert exc.details == {"field": "name", "reason": "too long"}


def test_app_error_none_details_becomes_empty_dict() -> None:
    """Passing ``details=None`` normalises to an empty dict."""
    exc = AppError("custom", details=None)

    assert exc.details == {}


def test_app_error_is_exception_subclass() -> None:
    """``AppError`` inherits from ``Exception``."""
    exc = AppError("msg")

    assert isinstance(exc, Exception)


def test_app_error_str_is_message() -> None:
    """``str(AppError)`` returns the constructor message."""
    exc = AppError("the message")

    assert str(exc) == "the message"


def test_app_error_can_be_raised_and_caught() -> None:
    """``AppError`` is raisable and matchable via ``pytest.raises``."""
    with pytest.raises(AppError, match="boom"):
        raise AppError("boom")


def test_service_error_status_code_is_500() -> None:
    """``ServiceError`` pins ``status_code=500``."""
    exc = ServiceError("service down")

    assert exc.status_code == 500


def test_service_error_error_code() -> None:
    """``ServiceError`` pins ``error_code='SERVICE_ERROR'``."""
    exc = ServiceError("service down")

    assert exc.error_code == "SERVICE_ERROR"


def test_service_error_message() -> None:
    """``ServiceError.message`` returns the constructor argument verbatim."""
    exc = ServiceError("db unreachable")

    assert exc.message == "db unreachable"


def test_service_error_details_passed_through() -> None:
    """``ServiceError`` stores caller-provided ``details``."""
    exc = ServiceError("failed", details={"host": "localhost"})

    assert exc.details == {"host": "localhost"}


def test_service_error_is_app_error() -> None:
    """``ServiceError`` is a subclass of ``AppError``."""
    exc = ServiceError("x")

    assert isinstance(exc, AppError)


def test_service_error_can_be_raised_and_caught() -> None:
    """``ServiceError`` is raisable and matchable via ``pytest.raises``."""
    with pytest.raises(ServiceError, match="service down"):
        raise ServiceError("service down")


def test_not_found_error_status_code_is_404() -> None:
    """``NotFoundError`` pins ``status_code=404``."""
    exc = NotFoundError("item missing")

    assert exc.status_code == 404


def test_not_found_error_error_code() -> None:
    """``NotFoundError`` pins ``error_code='NOT_FOUND'``."""
    exc = NotFoundError("item missing")

    assert exc.error_code == "NOT_FOUND"


def test_not_found_error_message() -> None:
    """``NotFoundError.message`` returns the constructor argument verbatim."""
    exc = NotFoundError("job 42 not found")

    assert exc.message == "job 42 not found"


def test_not_found_error_is_app_error() -> None:
    """``NotFoundError`` is a subclass of ``AppError``."""
    assert isinstance(NotFoundError("x"), AppError)


def test_not_found_error_can_be_raised_and_caught() -> None:
    """``NotFoundError`` is raisable via ``pytest.raises``."""
    with pytest.raises(NotFoundError):
        raise NotFoundError("gone")


def test_validation_error_status_code_is_400() -> None:
    """``ValidationError`` pins ``status_code=400``."""
    exc = ValidationError("bad input")

    assert exc.status_code == 400


def test_validation_error_error_code() -> None:
    """``ValidationError`` pins ``error_code='VALIDATION_ERROR'``."""
    exc = ValidationError("bad input")

    assert exc.error_code == "VALIDATION_ERROR"


def test_validation_error_message() -> None:
    """``ValidationError.message`` returns the constructor argument verbatim."""
    exc = ValidationError("field required")

    assert exc.message == "field required"


def test_validation_error_is_app_error() -> None:
    """``ValidationError`` is a subclass of ``AppError``."""
    assert isinstance(ValidationError("x"), AppError)


def test_validation_error_can_be_raised_and_caught() -> None:
    """``ValidationError`` is raisable and matchable via ``pytest.raises``."""
    with pytest.raises(ValidationError, match="field required"):
        raise ValidationError("field required")


def test_unauthorized_error_status_code_is_401() -> None:
    """``UnauthorizedError`` pins ``status_code=401``."""
    exc = UnauthorizedError("not logged in")

    assert exc.status_code == 401


def test_unauthorized_error_error_code() -> None:
    """``UnauthorizedError`` pins ``error_code='UNAUTHORIZED'``."""
    exc = UnauthorizedError("not logged in")

    assert exc.error_code == "UNAUTHORIZED"


def test_unauthorized_error_message() -> None:
    """``UnauthorizedError.message`` returns the constructor argument verbatim."""
    exc = UnauthorizedError("token expired")

    assert exc.message == "token expired"


def test_unauthorized_error_is_app_error() -> None:
    """``UnauthorizedError`` is a subclass of ``AppError``."""
    assert isinstance(UnauthorizedError("x"), AppError)


def test_forbidden_error_status_code_is_403() -> None:
    """``ForbiddenError`` pins ``status_code=403``."""
    exc = ForbiddenError("no access")

    assert exc.status_code == 403


def test_forbidden_error_error_code() -> None:
    """``ForbiddenError`` pins ``error_code='FORBIDDEN'``."""
    exc = ForbiddenError("no access")

    assert exc.error_code == "FORBIDDEN"


def test_forbidden_error_message() -> None:
    """``ForbiddenError.message`` returns the constructor argument verbatim."""
    exc = ForbiddenError("you shall not pass")

    assert exc.message == "you shall not pass"


def test_forbidden_error_is_app_error() -> None:
    """``ForbiddenError`` is a subclass of ``AppError``."""
    assert isinstance(ForbiddenError("x"), AppError)


def test_conflict_error_status_code_is_409() -> None:
    """``ConflictError`` pins ``status_code=409``."""
    exc = ConflictError("already exists")

    assert exc.status_code == 409


def test_conflict_error_error_code() -> None:
    """``ConflictError`` pins ``error_code='CONFLICT'``."""
    exc = ConflictError("already exists")

    assert exc.error_code == "CONFLICT"


def test_conflict_error_message() -> None:
    """``ConflictError.message`` returns the constructor argument verbatim."""
    exc = ConflictError("duplicate key")

    assert exc.message == "duplicate key"


def test_conflict_error_is_app_error() -> None:
    """``ConflictError`` is a subclass of ``AppError``."""
    assert isinstance(ConflictError("x"), AppError)


def test_rate_limit_error_status_code_is_429() -> None:
    """``RateLimitError`` pins ``status_code=429``."""
    exc = RateLimitError("too many requests")

    assert exc.status_code == 429


def test_rate_limit_error_error_code() -> None:
    """``RateLimitError`` pins ``error_code='RATE_LIMIT'``."""
    exc = RateLimitError("too many requests")

    assert exc.error_code == "RATE_LIMIT"


def test_rate_limit_error_message() -> None:
    """``RateLimitError.message`` returns the constructor argument verbatim."""
    exc = RateLimitError("slow down")

    assert exc.message == "slow down"


def test_rate_limit_error_is_app_error() -> None:
    """``RateLimitError`` is a subclass of ``AppError``."""
    assert isinstance(RateLimitError("x"), AppError)


def test_rate_limit_error_can_be_raised_and_caught() -> None:
    """``RateLimitError`` is raisable and matchable via ``pytest.raises``."""
    with pytest.raises(RateLimitError, match="slow down"):
        raise RateLimitError("slow down")


@pytest.mark.parametrize(
    ("exc_class", "expected_status", "expected_code"),
    [
        (ServiceError, 500, "SERVICE_ERROR"),
        (NotFoundError, 404, "NOT_FOUND"),
        (ValidationError, 400, "VALIDATION_ERROR"),
        (UnauthorizedError, 401, "UNAUTHORIZED"),
        (ForbiddenError, 403, "FORBIDDEN"),
        (ConflictError, 409, "CONFLICT"),
        (RateLimitError, 429, "RATE_LIMIT"),
    ],
    ids=["service", "not_found", "validation", "unauthorized", "forbidden", "conflict", "rate_limit"],
)
def test_exception_subclass_status_and_code(
    exc_class: type[AppError], expected_status: int, expected_code: str
) -> None:
    """Each ``AppError`` subclass pins the expected HTTP status and error code."""
    exc = exc_class("test message")

    assert exc.status_code == expected_status
    assert exc.error_code == expected_code


@pytest.mark.parametrize(
    "exc_class",
    [ServiceError, NotFoundError, ValidationError, UnauthorizedError, ForbiddenError, ConflictError, RateLimitError],
    ids=["service", "not_found", "validation", "unauthorized", "forbidden", "conflict", "rate_limit"],
)
def test_exception_subclass_accepts_details(exc_class: type[AppError]) -> None:
    """Each ``AppError`` subclass accepts and stores a ``details`` mapping."""
    exc = exc_class("msg", details={"key": "value"})

    assert exc.details == {"key": "value"}


@pytest.mark.parametrize(
    "exc_class",
    [ServiceError, NotFoundError, ValidationError, UnauthorizedError, ForbiddenError, ConflictError, RateLimitError],
    ids=["service", "not_found", "validation", "unauthorized", "forbidden", "conflict", "rate_limit"],
)
def test_exception_subclass_none_details_becomes_empty_dict(exc_class: type[AppError]) -> None:
    """Each ``AppError`` subclass normalises ``details=None`` to an empty dict."""
    exc = exc_class("msg", details=None)

    assert exc.details == {}
