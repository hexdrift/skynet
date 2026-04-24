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
    """Verify AppError stores the message string."""
    exc = AppError("something went wrong")

    assert exc.message == "something went wrong"


def test_app_error_default_status_code() -> None:
    """Verify AppError defaults status_code to 500."""
    exc = AppError("oops")

    assert exc.status_code == 500


def test_app_error_default_error_code() -> None:
    """Verify AppError defaults error_code to 'INTERNAL_ERROR'."""
    exc = AppError("oops")

    assert exc.error_code == "INTERNAL_ERROR"


def test_app_error_default_details_is_empty_dict() -> None:
    """Verify AppError defaults details to an empty dict."""
    exc = AppError("oops")

    assert exc.details == {}


def test_app_error_custom_status_code() -> None:
    """Verify AppError accepts a custom HTTP status code."""
    exc = AppError("custom", status_code=418)

    assert exc.status_code == 418


def test_app_error_custom_error_code() -> None:
    """Verify AppError accepts a custom error_code string."""
    exc = AppError("custom", error_code="MY_CODE")

    assert exc.error_code == "MY_CODE"


def test_app_error_custom_details() -> None:
    """Verify AppError stores a custom details dict."""
    exc = AppError("custom", details={"field": "name", "reason": "too long"})

    assert exc.details == {"field": "name", "reason": "too long"}


def test_app_error_none_details_becomes_empty_dict() -> None:
    """Verify AppError converts None details to an empty dict."""
    exc = AppError("custom", details=None)

    assert exc.details == {}


def test_app_error_is_exception_subclass() -> None:
    """Verify AppError is a subclass of Exception."""
    exc = AppError("msg")

    assert isinstance(exc, Exception)


def test_app_error_str_is_message() -> None:
    """Verify str(AppError) equals the message string."""
    exc = AppError("the message")

    assert str(exc) == "the message"


def test_app_error_can_be_raised_and_caught() -> None:
    """Verify AppError can be raised and caught in a standard try/except."""
    with pytest.raises(AppError, match="boom"):
        raise AppError("boom")




def test_service_error_status_code_is_500() -> None:
    """Verify ServiceError has status_code 500."""
    exc = ServiceError("service down")

    assert exc.status_code == 500


def test_service_error_error_code() -> None:
    """Verify ServiceError has error_code 'SERVICE_ERROR'."""
    exc = ServiceError("service down")

    assert exc.error_code == "SERVICE_ERROR"


def test_service_error_message() -> None:
    """Verify ServiceError stores the message string."""
    exc = ServiceError("db unreachable")

    assert exc.message == "db unreachable"


def test_service_error_details_passed_through() -> None:
    """Verify ServiceError passes the details dict through to AppError."""
    exc = ServiceError("failed", details={"host": "localhost"})

    assert exc.details == {"host": "localhost"}


def test_service_error_is_app_error() -> None:
    """Verify ServiceError is a subclass of AppError."""
    exc = ServiceError("x")

    assert isinstance(exc, AppError)


def test_service_error_can_be_raised_and_caught() -> None:
    """Verify ServiceError can be raised and caught."""
    with pytest.raises(ServiceError, match="service down"):
        raise ServiceError("service down")




def test_not_found_error_status_code_is_404() -> None:
    """Verify NotFoundError has status_code 404."""
    exc = NotFoundError("item missing")

    assert exc.status_code == 404


def test_not_found_error_error_code() -> None:
    """Verify NotFoundError has error_code 'NOT_FOUND'."""
    exc = NotFoundError("item missing")

    assert exc.error_code == "NOT_FOUND"


def test_not_found_error_message() -> None:
    """Verify NotFoundError stores the message string."""
    exc = NotFoundError("job 42 not found")

    assert exc.message == "job 42 not found"


def test_not_found_error_is_app_error() -> None:
    """Verify NotFoundError is a subclass of AppError."""
    assert isinstance(NotFoundError("x"), AppError)


def test_not_found_error_can_be_raised_and_caught() -> None:
    """Verify NotFoundError can be raised and caught."""
    with pytest.raises(NotFoundError):
        raise NotFoundError("gone")




def test_validation_error_status_code_is_400() -> None:
    """Verify ValidationError has status_code 400."""
    exc = ValidationError("bad input")

    assert exc.status_code == 400


def test_validation_error_error_code() -> None:
    """Verify ValidationError has error_code 'VALIDATION_ERROR'."""
    exc = ValidationError("bad input")

    assert exc.error_code == "VALIDATION_ERROR"


def test_validation_error_message() -> None:
    """Verify ValidationError stores the message string."""
    exc = ValidationError("field required")

    assert exc.message == "field required"


def test_validation_error_is_app_error() -> None:
    """Verify ValidationError is a subclass of AppError."""
    assert isinstance(ValidationError("x"), AppError)


def test_validation_error_can_be_raised_and_caught() -> None:
    """Verify ValidationError can be raised and caught."""
    with pytest.raises(ValidationError, match="field required"):
        raise ValidationError("field required")




def test_unauthorized_error_status_code_is_401() -> None:
    """Verify UnauthorizedError has status_code 401."""
    exc = UnauthorizedError("not logged in")

    assert exc.status_code == 401


def test_unauthorized_error_error_code() -> None:
    """Verify UnauthorizedError has error_code 'UNAUTHORIZED'."""
    exc = UnauthorizedError("not logged in")

    assert exc.error_code == "UNAUTHORIZED"


def test_unauthorized_error_message() -> None:
    """Verify UnauthorizedError stores the message string."""
    exc = UnauthorizedError("token expired")

    assert exc.message == "token expired"


def test_unauthorized_error_is_app_error() -> None:
    """Verify UnauthorizedError is a subclass of AppError."""
    assert isinstance(UnauthorizedError("x"), AppError)




def test_forbidden_error_status_code_is_403() -> None:
    """Verify ForbiddenError has status_code 403."""
    exc = ForbiddenError("no access")

    assert exc.status_code == 403


def test_forbidden_error_error_code() -> None:
    """Verify ForbiddenError has error_code 'FORBIDDEN'."""
    exc = ForbiddenError("no access")

    assert exc.error_code == "FORBIDDEN"


def test_forbidden_error_message() -> None:
    """Verify ForbiddenError stores the message string."""
    exc = ForbiddenError("you shall not pass")

    assert exc.message == "you shall not pass"


def test_forbidden_error_is_app_error() -> None:
    """Verify ForbiddenError is a subclass of AppError."""
    assert isinstance(ForbiddenError("x"), AppError)




def test_conflict_error_status_code_is_409() -> None:
    """Verify ConflictError has status_code 409."""
    exc = ConflictError("already exists")

    assert exc.status_code == 409


def test_conflict_error_error_code() -> None:
    """Verify ConflictError has error_code 'CONFLICT'."""
    exc = ConflictError("already exists")

    assert exc.error_code == "CONFLICT"


def test_conflict_error_message() -> None:
    """Verify ConflictError stores the message string."""
    exc = ConflictError("duplicate key")

    assert exc.message == "duplicate key"


def test_conflict_error_is_app_error() -> None:
    """Verify ConflictError is a subclass of AppError."""
    assert isinstance(ConflictError("x"), AppError)




def test_rate_limit_error_status_code_is_429() -> None:
    """Verify RateLimitError has status_code 429."""
    exc = RateLimitError("too many requests")

    assert exc.status_code == 429


def test_rate_limit_error_error_code() -> None:
    """Verify RateLimitError has error_code 'RATE_LIMIT'."""
    exc = RateLimitError("too many requests")

    assert exc.error_code == "RATE_LIMIT"


def test_rate_limit_error_message() -> None:
    """Verify RateLimitError stores the message string."""
    exc = RateLimitError("slow down")

    assert exc.message == "slow down"


def test_rate_limit_error_is_app_error() -> None:
    """Verify RateLimitError is a subclass of AppError."""
    assert isinstance(RateLimitError("x"), AppError)


def test_rate_limit_error_can_be_raised_and_caught() -> None:
    """Verify RateLimitError can be raised and caught."""
    with pytest.raises(RateLimitError, match="slow down"):
        raise RateLimitError("slow down")




@pytest.mark.parametrize(
    "exc_class,expected_status,expected_code",
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
    """Verify each AppError subclass has the correct status_code and error_code."""
    exc = exc_class("test message")

    assert exc.status_code == expected_status
    assert exc.error_code == expected_code




@pytest.mark.parametrize(
    "exc_class",
    [ServiceError, NotFoundError, ValidationError, UnauthorizedError, ForbiddenError, ConflictError, RateLimitError],
    ids=["service", "not_found", "validation", "unauthorized", "forbidden", "conflict", "rate_limit"],
)
def test_exception_subclass_accepts_details(exc_class: type[AppError]) -> None:
    """Verify all AppError subclasses accept and store a details dict."""
    exc = exc_class("msg", details={"key": "value"})

    assert exc.details == {"key": "value"}


@pytest.mark.parametrize(
    "exc_class",
    [ServiceError, NotFoundError, ValidationError, UnauthorizedError, ForbiddenError, ConflictError, RateLimitError],
    ids=["service", "not_found", "validation", "unauthorized", "forbidden", "conflict", "rate_limit"],
)
def test_exception_subclass_none_details_becomes_empty_dict(exc_class: type[AppError]) -> None:
    """Verify all AppError subclasses normalize None details to an empty dict."""
    exc = exc_class("msg", details=None)

    assert exc.details == {}
