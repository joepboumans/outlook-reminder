"""Microsoft 365 sign-in: silent refresh, the saved token cache, and when to ask again."""

from typing import Any

import pytest

from outlook_reminder.auth import SCOPES, GraphAuth, MemoryTokenStore
from outlook_reminder.source import CalendarUnavailable, SignInFailed, SignInRequired

ACCOUNT = {"username": "joep@example.com", "home_account_id": "1.2"}


class FakeCache:
    def __init__(self) -> None:
        self.state = ""
        self.has_state_changed = False

    def serialize(self) -> str:
        return self.state

    def deserialize(self, state: str) -> None:
        self.state = state

    def change(self, state: str) -> None:
        self.state = state
        self.has_state_changed = True


class FakeMsal:
    """Stands in for msal.PublicClientApplication."""

    def __init__(self, cache: FakeCache) -> None:
        self.cache = cache
        self.accounts: list[dict[str, Any]] = [ACCOUNT]
        self.silent: dict[str, Any] | None | Exception = {"access_token": "at-1"}
        self.interactive: dict[str, Any] | Exception = {
            "access_token": "at-2", "id_token_claims": {"preferred_username": "joep@example.com"},
        }
        self.interactive_calls: list[dict[str, Any]] = []
        self.forced = False

    def get_accounts(self) -> list[dict[str, Any]]:
        return self.accounts

    def acquire_token_silent_with_error(self, scopes, account, force_refresh=False):
        assert scopes == SCOPES and account == ACCOUNT
        self.forced = force_refresh
        if isinstance(self.silent, Exception):
            raise self.silent
        if self.silent and "access_token" in self.silent:
            self.cache.change("refreshed")
        return self.silent

    def acquire_token_interactive(self, scopes, **kwargs):
        assert scopes == SCOPES
        self.interactive_calls.append(kwargs)
        if isinstance(self.interactive, Exception):
            raise self.interactive
        if "access_token" in self.interactive:
            self.cache.change("signed in")
        return self.interactive


def make(saved: str | None = "saved") -> tuple[GraphAuth, FakeMsal, MemoryTokenStore, FakeCache]:
    cache = FakeCache()
    app = FakeMsal(cache)
    store = MemoryTokenStore(saved)
    return GraphAuth(lambda _cache: app, store, cache=cache), app, store, cache


def test_scopes_are_read_only():
    assert SCOPES == ["Calendars.Read", "User.Read"]


def test_the_saved_sign_in_is_loaded():
    _, _, _, cache = make("saved")
    assert cache.state == "saved"


def test_token_is_refreshed_silently_and_saved():
    auth, _, store, _ = make()
    assert auth.token() == "at-1"
    assert store.data == "refreshed"


def test_force_refresh_is_passed_on():
    auth, app, _, _ = make()
    auth.token(force_refresh=True)
    assert app.forced


def test_no_account_means_never_signed_in():
    auth, app, _, _ = make(None)
    app.accounts = []
    with pytest.raises(SignInRequired) as e:
        auth.token()
    assert e.value.never_signed_in


def test_an_expired_sign_in_needs_sign_in_again():
    auth, app, _, _ = make()
    app.silent = None
    with pytest.raises(SignInRequired) as e:
        auth.token()
    assert not e.value.never_signed_in


@pytest.mark.parametrize("error", ["invalid_grant", "interaction_required"])
def test_a_revoked_sign_in_needs_sign_in_again(error):
    auth, app, _, _ = make()
    app.silent = {"error": error, "error_description": "AADSTS50173: The provided grant has expired"}
    with pytest.raises(SignInRequired, match="AADSTS50173"):
        auth.token()


def test_a_passing_server_error_is_only_unavailable():
    auth, app, _, _ = make()
    app.silent = {"error": "temporarily_unavailable"}
    with pytest.raises(CalendarUnavailable) as e:
        auth.token()
    assert not isinstance(e.value, SignInRequired)


def test_network_down_is_only_unavailable():
    auth, app, _, _ = make()
    app.silent = ConnectionError("no route to host")
    with pytest.raises(CalendarUnavailable) as e:
        auth.token()
    assert not isinstance(e.value, SignInRequired)


def test_unreachable_sign_in_server_is_only_unavailable():
    def offline(_cache):
        raise ConnectionError("offline")

    auth = GraphAuth(offline, MemoryTokenStore(), cache=FakeCache())
    with pytest.raises(CalendarUnavailable) as e:
        auth.token()
    assert not isinstance(e.value, SignInRequired)


def test_sign_in_opens_the_browser_and_saves_the_result():
    auth, app, store, _ = make(None)
    assert auth.sign_in() == "joep@example.com"
    assert store.data == "signed in"
    assert app.interactive_calls[0]["prompt"] == "select_account"


def test_cancelled_sign_in_fails():
    auth, app, _, _ = make()
    app.interactive = {"error": "access_denied", "error_description": "The user cancelled"}
    with pytest.raises(SignInFailed, match="cancelled"):
        auth.sign_in()


def test_sign_in_that_breaks_fails():
    auth, app, _, _ = make()
    app.interactive = OSError("no browser")
    with pytest.raises(SignInFailed):
        auth.sign_in()


def test_nothing_is_saved_when_nothing_changed():
    auth, app, store, _ = make("saved")
    app.silent = None
    with pytest.raises(SignInRequired):
        auth.token()
    assert store.data == "saved"


def test_a_sign_in_made_elsewhere_is_picked_up():
    auth, app, store, cache = make(None)
    app.accounts = []
    with pytest.raises(SignInRequired):
        auth.token()
    # `outlook-reminder --sign-in` saved a sign-in to the keyring meanwhile.
    store.data = "from the command line"
    original = app.get_accounts

    def accounts():
        return [ACCOUNT] if cache.state == "from the command line" else original()

    app.get_accounts = accounts  # type: ignore[method-assign]
    assert auth.token() == "at-1"
