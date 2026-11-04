"""Microsoft 365 sign-in for the Graph calendar source (ADR 0001).

Browser sign-in with the authorization code flow and PKCE (MSAL does both),
redirecting to http://localhost. The token cache lives in the GNOME keyring.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, Protocol

from .source import CalendarUnavailable, SignInFailed, SignInRequired

log = logging.getLogger(__name__)

# Delegated, read-only. MSAL adds offline_access (and openid, profile) by itself.
SCOPES = ["Calendars.Read", "User.Read"]
# How long the browser sign-in waits for the user before giving up.
SIGN_IN_TIMEOUT_SECONDS = 600
KEYRING_SERVICE = "outlook-reminder"

# Errors that only an interactive sign-in can fix.
SIGN_IN_ERRORS = {"invalid_grant", "interaction_required", "login_required", "consent_required"}


class TokenStore(Protocol):
    """Where the serialized MSAL token cache is kept."""

    def load(self) -> str | None: ...
    def save(self, data: str) -> None: ...


class MemoryTokenStore:
    def __init__(self, data: str | None = None) -> None:
        self.data = data

    def load(self) -> str | None:
        return self.data

    def save(self, data: str) -> None:
        self.data = data


class KeyringTokenStore:
    """The GNOME keyring (Secret Service), through the keyring package."""

    def __init__(self, account: str) -> None:
        self._account = account

    def load(self) -> str | None:
        import keyring
        import keyring.errors

        try:
            return keyring.get_password(KEYRING_SERVICE, self._account)
        except keyring.errors.KeyringError as e:
            log.warning("Could not read the sign-in from the keyring: %s", e)
            return None

    def save(self, data: str) -> None:
        import keyring
        import keyring.errors

        try:
            keyring.set_password(KEYRING_SERVICE, self._account, data)
        except keyring.errors.KeyringError as e:
            log.warning("Could not save the sign-in to the keyring; you will be asked again next start: %s", e)


class MsalApp(Protocol):
    """The part of msal.PublicClientApplication we use (a fake stands in for tests)."""

    def get_accounts(self) -> list[dict[str, Any]]: ...
    def acquire_token_silent_with_error(
        self, scopes: list[str], account: dict[str, Any], force_refresh: bool = False
    ) -> dict[str, Any] | None: ...
    def acquire_token_interactive(self, scopes: list[str], **kwargs: Any) -> dict[str, Any]: ...


class TokenCache(Protocol):
    has_state_changed: bool

    def serialize(self) -> str: ...
    def deserialize(self, state: str) -> None: ...


AppFactory = Callable[[TokenCache], MsalApp]


def msal_app_factory(client_id: str, tenant_id: str) -> AppFactory:
    def make(cache: TokenCache) -> MsalApp:
        import msal

        app: Any = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=cache,
        )
        return app

    return make


def _new_cache() -> TokenCache:
    import msal

    cache: Any = msal.SerializableTokenCache()
    return cache


class GraphAuth:
    """Hands out Graph access tokens, refreshing them silently while it can."""

    def __init__(self, make_app: AppFactory, store: TokenStore, cache: TokenCache | None = None) -> None:
        self._make_app = make_app
        self._store = store
        self._cache = cache or _new_cache()
        self._app: MsalApp | None = None
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        saved = self._store.load()
        if saved:
            try:
                self._cache.deserialize(saved)
            except ValueError as e:
                log.warning("Ignoring the unreadable saved sign-in: %s", e)

    def _client(self) -> MsalApp:
        with self._lock:
            if self._app is None:
                try:
                    # Looks up the tenant's sign-in endpoints, so it needs the network.
                    self._app = self._make_app(self._cache)
                except ValueError as e:
                    # MSAL's error for an unknown tenant or a malformed authority.
                    raise CalendarUnavailable(f"could not set up the Microsoft sign-in: {e}") from e
                except Exception as e:
                    raise CalendarUnavailable(f"could not reach the Microsoft sign-in: {e}") from e
            return self._app

    def token(self, force_refresh: bool = False) -> str:
        """A valid access token. Never opens the browser.

        Raises SignInRequired when only an interactive sign-in can help, and
        CalendarUnavailable for passing problems (network down).
        """
        app = self._client()
        accounts = app.get_accounts()
        if not accounts:
            # Signed in since we started, e.g. with `outlook-reminder --sign-in`?
            self._load()
            accounts = app.get_accounts()
        if not accounts:
            raise SignInRequired("not signed in to Microsoft 365", never_signed_in=True)
        try:
            result = app.acquire_token_silent_with_error(SCOPES, accounts[0], force_refresh=force_refresh)
        except Exception as e:  # requests' network errors
            raise CalendarUnavailable(f"could not refresh the Microsoft sign-in: {e}") from e
        finally:
            self._save()
        if not result:
            raise SignInRequired("the Microsoft 365 sign-in has expired")
        if "access_token" in result:
            return str(result["access_token"])
        error = str(result.get("error", ""))
        message = str(result.get("error_description") or error or "unknown error")
        if error in SIGN_IN_ERRORS:
            raise SignInRequired(f"the Microsoft 365 sign-in has expired or was revoked: {message}")
        raise CalendarUnavailable(f"could not refresh the Microsoft sign-in: {message}")

    def sign_in(self) -> str:
        """Sign in through the system browser. Returns the signed-in user name.

        Blocks until the browser redirects back to http://localhost, or the
        sign-in times out. Raises SignInFailed when it does not complete.
        """
        try:
            app = self._client()
            result = app.acquire_token_interactive(
                SCOPES, prompt="select_account", timeout=SIGN_IN_TIMEOUT_SECONDS
            )
        except CalendarUnavailable as e:
            raise SignInFailed(str(e)) from e
        except Exception as e:
            raise SignInFailed(f"the browser sign-in failed: {e}") from e
        finally:
            self._save()
        if "access_token" not in result:
            message = result.get("error_description") or result.get("error") or "no token received"
            raise SignInFailed(f"the browser sign-in did not complete: {message}")
        claims = result.get("id_token_claims") or {}
        return str(claims.get("preferred_username") or claims.get("name") or "")

    def _save(self) -> None:
        with self._lock:
            if self._cache.has_state_changed:
                self._store.save(self._cache.serialize())
                self._cache.has_state_changed = False
