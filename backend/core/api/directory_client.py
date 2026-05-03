"""Directory service clients for looking up network users.

Admin username autocomplete always falls back on previously-seen users
from the local job store. When ``AD_LDAP_*`` environment variables are
configured, the backend also queries LDAP/Active Directory for live
network users who have not yet signed in.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol

from ldap3 import ALL, SUBTREE, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

logger = logging.getLogger(__name__)

DEFAULT_AD_LDAP_USER_FILTER = "(&(objectCategory=person)(objectClass=user))"
DEFAULT_AD_LDAP_USERNAME_ATTR = "sAMAccountName"
DEFAULT_AD_LDAP_DISPLAY_NAME_ATTR = "displayName"
DEFAULT_AD_LDAP_EMAIL_ATTR = "mail"
LDAP_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class DirectoryUser:
    """Network user resolved from a directory lookup."""

    username: str
    display_name: str | None = None
    email: str | None = None


class DirectoryClient(Protocol):
    """Abstract provider for network-wide username search."""

    def search_users(self, query: str, *, limit: int = 10) -> list[DirectoryUser]:
        """Return network users matching ``query``.

        Args:
            query: Free-text fragment matched against username, display name, or email.
            limit: Maximum number of matches to return.

        Returns:
            Matching directory users, possibly empty.
        """
        ...


class NullDirectoryClient:
    """No-op directory client returning zero matches.

    Active whenever AD/LDAP credentials are absent. Keeps the admin
    autocomplete working against DB-known users only.
    """

    def search_users(self, query: str, *, limit: int = 10) -> list[DirectoryUser]:
        """Return an empty list — no directory configured.

        Args:
            query: Ignored.
            limit: Ignored.

        Returns:
            Always an empty list.
        """
        return []


@dataclass(frozen=True)
class LdapDirectoryClient:
    """LDAP-backed directory client for Active Directory user search."""

    url: str
    bind_dn: str
    bind_password: str
    search_base: str
    user_filter: str = DEFAULT_AD_LDAP_USER_FILTER
    username_attr: str = DEFAULT_AD_LDAP_USERNAME_ATTR
    display_name_attr: str = DEFAULT_AD_LDAP_DISPLAY_NAME_ATTR
    email_attr: str = DEFAULT_AD_LDAP_EMAIL_ATTR

    def search_users(self, query: str, *, limit: int = 10) -> list[DirectoryUser]:
        """Return LDAP users matching the query fragment.

        Args:
            query: Free-text fragment matched against username, display name,
                or email.
            limit: Maximum number of matches to return.

        Returns:
            Matching directory users, or an empty list when the directory is
            unreachable.
        """
        trimmed = query.strip()
        if not trimmed or limit <= 0:
            return []

        escaped_query = escape_filter_chars(trimmed)
        search_filter = (
            f"(&{self.user_filter}(|"
            f"({self.username_attr}=*{escaped_query}*)"
            f"({self.display_name_attr}=*{escaped_query}*)"
            f"({self.email_attr}=*{escaped_query}*)"
            "))"
        )
        attributes = [self.username_attr, self.display_name_attr, self.email_attr]
        connection: Connection | None = None

        try:
            server = Server(self.url, get_info=ALL, connect_timeout=LDAP_TIMEOUT_SECONDS)
            connection = Connection(
                server,
                user=self.bind_dn,
                password=self.bind_password,
                auto_bind=True,
                receive_timeout=LDAP_TIMEOUT_SECONDS,
                raise_exceptions=True,
            )
            connection.search(
                search_base=self.search_base,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=attributes,
                size_limit=limit,
            )
            return [user for entry in connection.entries if (user := self._entry_to_user(entry)) is not None][:limit]
        except (LDAPException, OSError) as exc:
            logger.warning("LDAP user search failed: %s", exc)
            return []
        finally:
            if connection is not None:
                connection.unbind()

    def _entry_to_user(self, entry: object) -> DirectoryUser | None:
        """Convert an LDAP entry object into a directory user.

        Args:
            entry: ldap3 entry-like object exposing ``entry_attributes_as_dict``.

        Returns:
            A populated DirectoryUser, or ``None`` when the username attribute
            is missing or empty.
        """
        attrs = getattr(entry, "entry_attributes_as_dict", {})
        username = _first_attr(attrs, self.username_attr)
        if not username:
            return None
        return DirectoryUser(
            username=username,
            display_name=_first_attr(attrs, self.display_name_attr),
            email=_first_attr(attrs, self.email_attr),
        )


def _first_attr(attrs: object, name: str) -> str | None:
    """Return the first non-empty string value for an LDAP attribute.

    Args:
        attrs: Mapping-like attribute container produced by ``ldap3``.
        name: Attribute name to read from ``attrs``.

    Returns:
        The first non-empty trimmed string value, or ``None`` when the
        attribute is missing, empty, or the container is not a dict.
    """
    if not isinstance(attrs, dict):
        return None
    raw_values = attrs.get(name)
    if raw_values is None:
        return None
    values = raw_values if isinstance(raw_values, (list, tuple)) else [raw_values]
    for value in values:
        text = str(value).strip()
        if text:
            return text
    return None


def _env(name: str) -> str:
    """Return a stripped environment variable value."""
    return os.environ.get(name, "").strip()


def build_directory_client() -> DirectoryClient:
    """Construct the configured directory client.

    Returns:
        A directory client suitable for the current environment.
    """
    url = _env("AD_LDAP_URL")
    bind_dn = _env("AD_LDAP_BIND_DN")
    bind_password = os.environ.get("AD_LDAP_BIND_PASSWORD", "")
    search_base = _env("AD_LDAP_SEARCH_BASE")
    if not all([url, bind_dn, bind_password, search_base]):
        return NullDirectoryClient()
    return LdapDirectoryClient(
        url=url,
        bind_dn=bind_dn,
        bind_password=bind_password,
        search_base=search_base,
        user_filter=_env("AD_LDAP_USER_FILTER") or DEFAULT_AD_LDAP_USER_FILTER,
        username_attr=_env("AD_LDAP_USERNAME_ATTR") or DEFAULT_AD_LDAP_USERNAME_ATTR,
    )
