"""Per-user overrides for the job quota.

The default per-user cap lives in ``constants.MAX_JOBS_PER_USER`` (100).
Two kinds of exceptions are handled here, both hand-edited in Python so
changes are version-controlled and require only a backend restart — no
rebuild, no UI, no environment variables.

- ``ADMIN_USERNAMES``: users that bypass the quota entirely. They can
  create as many jobs as they like. Admin detection follows the same
  trust boundary as the rest of the submission flow: the username is
  taken from the request payload, so whoever is authorized to write
  this module is responsible for keeping the list accurate.

- ``QUOTA_OVERRIDES``: per-user overrides of the default cap for
  non-admin users. An ``int`` raises the cap to that value; ``None``
  means "unlimited" (equivalent to being an admin for quota purposes
  only).

Example::

    ADMIN_USERNAMES = frozenset({"gilad", "ops"})
    QUOTA_OVERRIDES = {
        "power_user": 500,
        "researcher": None,  # unlimited
    }
"""
from __future__ import annotations

from typing import Final, Optional

ADMIN_USERNAMES: Final[frozenset[str]] = frozenset()

QUOTA_OVERRIDES: Final[dict[str, Optional[int]]] = {}


def get_user_quota(username: str, default: int) -> Optional[int]:
    """Return the effective job quota for ``username``.

    Args:
        username: The submitting user as recorded on the request.
        default: Fallback quota applied when the user is neither an
            admin nor present in ``QUOTA_OVERRIDES``.

    Returns:
        ``None`` if the user has unlimited quota (admin or explicit
        override set to ``None``), otherwise the ``int`` maximum
        number of jobs the user may own concurrently across all
        statuses.
    """
    if username in ADMIN_USERNAMES:
        return None
    if username in QUOTA_OVERRIDES:
        return QUOTA_OVERRIDES[username]
    return default
