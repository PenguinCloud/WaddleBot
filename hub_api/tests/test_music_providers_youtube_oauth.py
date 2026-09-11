"""Tests for `services/music_providers/youtube.py`'s OAuth refresh-token credential mode.

Split out of `test_music_providers.py` -- these exercise a second, independent credential
path (`YOUTUBE_CLIENT_ID`+`YOUTUBE_CLIENT_SECRET`+`YOUTUBE_REFRESH_TOKEN`) on top of the
existing `YOUTUBE_API_KEY` mode that file already covers, so it gets its own self-contained
fixtures rather than importing from a sibling test module. Same mocked-transport approach as
`test_music_providers.py`: `httpx.MockTransport` swapped in for `httpx.AsyncClient`, so
request building/param encoding/JSON parsing all run for real.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from services.music_providers import ProviderUnavailable
from services.music_providers import youtube as youtube_mod

_RealAsyncClient = httpx.AsyncClient

_YT_VIDEO_ITEM = {
    "id": "dQw4w9WgXcQ",
    "snippet": {
        "title": "Rick Astley - Never Gonna Give You Up",
        "channelTitle": "Rick Astley",
        "thumbnails": {"default": {"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/default.jpg"}},
    },
    "contentDetails": {"duration": "PT3M33S"},
}

_WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

_NOT_CONFIGURED_MESSAGE = (
    "youtube credentials not configured: set YOUTUBE_API_KEY or "
    "YOUTUBE_CLIENT_ID+YOUTUBE_CLIENT_SECRET+YOUTUBE_REFRESH_TOKEN"
)


def _client_factory(transport: httpx.MockTransport) -> Callable[..., httpx.AsyncClient]:
    """Build a replacement for `httpx.AsyncClient` that always uses `transport`."""

    def factory(*_args: Any, **_kwargs: Any) -> httpx.AsyncClient:
        return _RealAsyncClient(transport=transport)

    return factory


def _token_payload(
    access_token: str = "test-access-token", expires_in: int = 3600
) -> dict[str, Any]:
    return {"access_token": access_token, "expires_in": expires_in, "token_type": "Bearer"}


@pytest.fixture(autouse=True)
def _no_real_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test controls its own credential source explicitly; no real `~/.youtube.token`."""
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REFRESH_TOKEN", raising=False)
    monkeypatch.setattr(
        youtube_mod, "_TOKEN_FILE", youtube_mod._TOKEN_FILE.parent / "__nope__.token"
    )


@pytest.fixture(autouse=True)
def _reset_oauth_token_cache() -> Any:
    """YouTube's OAuth access-token cache is module-level state -- isolate every test."""
    youtube_mod._oauth_token_cache = None
    yield
    youtube_mod._oauth_token_cache = None


def _set_oauth_trio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "test-refresh-token")


class TestOAuthModeSelection:
    """`_resolve_auth_mode()` -- API key wins, OAuth trio is the fallback."""

    async def test_oauth_used_when_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_oauth_trio(monkeypatch)
        seen_auth_header = None
        seen_key_param = "unset"

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_auth_header, seen_key_param
            if request.url.host == "oauth2.googleapis.com":
                return httpx.Response(200, json=_token_payload())
            seen_auth_header = request.headers.get("Authorization")
            seen_key_param = request.url.params.get("key")
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        track = await youtube_mod.resolve(_WATCH_URL)

        assert track.external_id == "dQw4w9WgXcQ"
        assert seen_auth_header == "Bearer test-access-token"
        assert seen_key_param is None

    async def test_api_key_wins_over_oauth_trio_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        _set_oauth_trio(monkeypatch)
        oauth_token_endpoint_called = False
        seen_key_param = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal oauth_token_endpoint_called, seen_key_param
            if request.url.host == "oauth2.googleapis.com":
                oauth_token_endpoint_called = True
                return httpx.Response(200, json=_token_payload())
            seen_key_param = request.url.params.get("key")
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        track = await youtube_mod.resolve(_WATCH_URL)

        assert track.external_id == "dQw4w9WgXcQ"
        assert seen_key_param == "test-key"
        assert oauth_token_endpoint_called is False

    @pytest.mark.parametrize(
        "missing_env",
        ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"],
    )
    async def test_partial_oauth_trio_raises_not_configured(
        self, monkeypatch: pytest.MonkeyPatch, missing_env: str
    ) -> None:
        _set_oauth_trio(monkeypatch)
        monkeypatch.delenv(missing_env, raising=False)

        def boom(_request: httpx.Request) -> httpx.Response:
            raise AssertionError("no network call should happen with incomplete credentials")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(boom)))

        with pytest.raises(ProviderUnavailable) as exc_info:
            await youtube_mod.resolve(_WATCH_URL)
        assert exc_info.value.provider == _NOT_CONFIGURED_MESSAGE


class TestOAuthTokenCaching:
    """`_get_oauth_access_token()` -- in-process cache hit/miss/expiry behavior."""

    async def test_refresh_exchange_cached_across_two_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_oauth_trio(monkeypatch)
        token_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls
            if request.url.host == "oauth2.googleapis.com":
                token_calls += 1
                return httpx.Response(200, json=_token_payload())
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        await youtube_mod.resolve(_WATCH_URL)
        await youtube_mod.resolve(_WATCH_URL)

        assert token_calls == 1

    async def test_refresh_exchange_triggered_again_after_expiry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_oauth_trio(monkeypatch)
        token_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls
            if request.url.host == "oauth2.googleapis.com":
                token_calls += 1
                return httpx.Response(200, json=_token_payload())
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        await youtube_mod.resolve(_WATCH_URL)
        assert token_calls == 1

        assert youtube_mod._oauth_token_cache is not None
        youtube_mod._oauth_token_cache.expires_at = time.monotonic() - 1

        await youtube_mod.resolve(_WATCH_URL)
        assert token_calls == 2


class TestOAuth401RefreshAndRetry:
    """A 401 from the Data API forces one token refresh and one retry -- never more."""

    async def test_401_triggers_one_refresh_and_retry_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_oauth_trio(monkeypatch)
        token_calls = 0
        data_api_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls, data_api_calls
            if request.url.host == "oauth2.googleapis.com":
                token_calls += 1
                return httpx.Response(200, json=_token_payload())
            data_api_calls += 1
            if data_api_calls == 1:
                return httpx.Response(401, json={"error": {"message": "invalid credentials"}})
            return httpx.Response(200, json={"items": [_YT_VIDEO_ITEM]})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        track = await youtube_mod.resolve(_WATCH_URL)

        assert track.external_id == "dQw4w9WgXcQ"
        assert token_calls == 2  # initial mint + forced refresh after the 401
        assert data_api_calls == 2  # original request + the one retry

    async def test_401_retry_still_failing_raises_provider_unavailable_without_a_second_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_oauth_trio(monkeypatch)
        token_calls = 0
        data_api_calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls, data_api_calls
            if request.url.host == "oauth2.googleapis.com":
                token_calls += 1
                return httpx.Response(200, json=_token_payload())
            data_api_calls += 1
            return httpx.Response(401, json={"error": {"message": "invalid credentials"}})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable):
            await youtube_mod.resolve(_WATCH_URL)

        assert token_calls == 2  # initial mint + the one forced refresh
        assert data_api_calls == 2  # original request + the one retry, no third attempt


class TestOAuthRefreshFailure:
    """The refresh-token exchange itself failing -- distinct `ProviderUnavailable` message."""

    async def test_refresh_exchange_http_failure_raises_specific_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_oauth_trio(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "oauth2.googleapis.com"
            return httpx.Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "Token has been expired or revoked.",
                },
            )

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable) as exc_info:
            await youtube_mod.resolve(_WATCH_URL)

        assert exc_info.value.provider == (
            "youtube oauth refresh failed: HTTP 400 "
            "invalid_grant: Token has been expired or revoked."
        )

    async def test_refresh_exchange_network_error_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_oauth_trio(monkeypatch)

        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable) as exc_info:
            await youtube_mod.resolve(_WATCH_URL)
        assert exc_info.value.provider == "youtube oauth refresh failed: ConnectError"

    async def test_refresh_response_missing_access_token_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_oauth_trio(monkeypatch)

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.host == "oauth2.googleapis.com"
            return httpx.Response(200, json={"token_type": "Bearer", "expires_in": 3600})

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable) as exc_info:
            await youtube_mod.resolve(_WATCH_URL)
        assert exc_info.value.provider == (
            "youtube oauth refresh failed: response missing access_token"
        )


class TestDataApi403QuotaReason:
    """A 403 from the Data API surfaces Google's own error `reason` in the message."""

    @pytest.mark.parametrize("reason", ["quotaExceeded", "accessNotConfigured", "forbidden"])
    async def test_403_reason_surfaced_in_message(
        self, monkeypatch: pytest.MonkeyPatch, reason: str
    ) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": 403,
                        "message": "The request cannot be completed.",
                        "errors": [
                            {"reason": reason, "message": "The request cannot be completed."}
                        ],
                    }
                },
            )

        monkeypatch.setattr(httpx, "AsyncClient", _client_factory(httpx.MockTransport(handler)))

        with pytest.raises(ProviderUnavailable) as exc_info:
            await youtube_mod.resolve(_WATCH_URL)
        assert exc_info.value.provider == f"youtube quota/access error: {reason}"


class TestYoutubeCredentialsConfigured:
    """`youtube_credentials_configured()` -- presence-only truth table, no network I/O."""

    def test_api_key_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        assert youtube_mod.youtube_credentials_configured() is True

    def test_full_oauth_trio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_oauth_trio(monkeypatch)
        assert youtube_mod.youtube_credentials_configured() is True

    def test_api_key_and_oauth_trio_both_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
        _set_oauth_trio(monkeypatch)
        assert youtube_mod.youtube_credentials_configured() is True

    @pytest.mark.parametrize(
        "env",
        [
            {},
            {"YOUTUBE_CLIENT_ID": "id"},
            {"YOUTUBE_CLIENT_ID": "id", "YOUTUBE_CLIENT_SECRET": "secret"},
            {"YOUTUBE_CLIENT_SECRET": "secret", "YOUTUBE_REFRESH_TOKEN": "refresh"},
            {"YOUTUBE_CLIENT_ID": "id", "YOUTUBE_REFRESH_TOKEN": "refresh"},
        ],
    )
    def test_partial_or_absent_credentials_return_false(
        self, monkeypatch: pytest.MonkeyPatch, env: dict[str, str]
    ) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        assert youtube_mod.youtube_credentials_configured() is False
