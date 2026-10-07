"""LDAP/Active Directory authentication helper."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class LdapAuthError(Exception):
    pass


class LdapClient:
    """Thin wrapper around ldap3 for synchronous LDAP bind + user search."""

    def __init__(self, url: str, bind_dn: str, bind_password: str, search_base: str) -> None:
        self._url = url
        self._bind_dn = bind_dn
        self._bind_password = bind_password
        self._search_base = search_base

    def authenticate(self, email: str, password: str) -> dict[str, str]:
        """
        Returns dict with display_name and email if auth succeeds.
        Raises LdapAuthError on failure.
        Requires the `ldap3` package.
        """
        try:
            import ldap3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise LdapAuthError("ldap3 is not installed") from exc

        server = ldap3.Server(self._url, get_info=ldap3.ALL)

        # Search bind to find user DN
        conn = ldap3.Connection(server, self._bind_dn, self._bind_password, auto_bind=True)
        conn.search(
            self._search_base,
            f"(mail={email})",
            attributes=["cn", "mail", "distinguishedName"],
        )
        if not conn.entries:
            raise LdapAuthError("User not found in directory")

        entry = conn.entries[0]
        user_dn = str(entry.distinguishedName)
        display_name = str(entry.cn) if entry.cn else email

        # Verify password by binding as the user
        user_conn = ldap3.Connection(server, user_dn, password)
        if not user_conn.bind():
            raise LdapAuthError("Invalid LDAP credentials")

        return {"email": email, "display_name": display_name}
