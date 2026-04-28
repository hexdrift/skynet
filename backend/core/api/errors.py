"""HTTP errors that carry semantic i18n codes.

Routes should raise :class:`DomainError` instead of ``HTTPException(detail=t(...))``.
The response envelope then exposes both the rendered message (for legacy clients
and logs) and the semantic ``code``/``params`` pair (for clients that prefer to
render copy with their own i18n layer).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..i18n import t
from ..i18n_keys import I18nKey


class DomainError(HTTPException):
    """HTTPException with an attached semantic i18n key and parameters.

    Example::

        raise DomainError(
            "optimization.not_found",
            status=404,
            optimization_id=optimization_id,
        )

    The exception handler in :mod:`backend.core.api.app` picks up ``code`` and
    ``params`` and emits them alongside the rendered ``detail`` so clients can
    choose which one to display.
    """

    def __init__(
        self,
        code: I18nKey | str,
        *,
        status: int = 400,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Build an HTTPException carrying an i18n key plus rendered detail.

        Args:
            code: The i18n key, either as an ``I18nKey`` enum or a raw string.
            status: HTTP status code to return; defaults to 400.
            params: Optional explicit dict of substitution params.
            **kwargs: Additional substitution params merged on top of ``params``.
        """
        key = code.value if isinstance(code, I18nKey) else str(code)
        merged: dict[str, Any] = {}
        if params:
            merged.update(params)
        merged.update(kwargs)
        self.code: str = key
        self.params: dict[str, Any] = merged
        detail = t(key, **merged)
        super().__init__(status_code=status, detail=detail)
