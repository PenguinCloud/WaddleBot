"""Tests for `services/youtube_oauth.py` -- refresh-token exchange, cache, scope lookup.

Mirrors `hub_api/tests/test_music_providers_youtube_oauth.py`'s own
conventions (mocked `httpx.MockTransport`, module-level cache reset via an
autouse fixture) adapted to this module's explicit `http_client` parameter
shape (it never builds its own client, unlike the `hub_api` module).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import pytest

from services import youtube_oauth as oauth_mod
from services.youtube_oauth import (
    YOUTUBE_FORCE_SSL_SCOPE,
    YouTubeOAuthError,
    get_access_token,
    get_access_token_for_community,
    token_has_scope,
)


@pytest.fixture(autouse=True)
def _reset_caches() -> Any:
    """Both in-process caches are module-level state -- isolate every test."""
    oauth_mod._token_cache.clear()
    oauth_mod._scope_cache.clear()
    yield
    oauth_mod._token_cache.clear()
    oauth_mod._scope_cache.clear()


def _client(handler) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _token_payload(
    access_token: str = "test-access-token",  # noqa: S107 -- fixture default, not a real secret
    expires_in: int = 3600,
) -> dict[str, Any]:
    return {"access_token": access_token, "expires_in": expires_in, "token_type": "Bearer"}


class TestGetAccessTokenRefresh:
    """`get_access_token()` -- the real refresh-token exchange request shape."""

    async def test_sends_refresh_token_grant(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = request.content
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            token = await get_access_token(client, "cid", "csecret", "rtoken")

        assert token == "test-access-token"
        assert captured["url"] == "https://oauth2.googleapis.com/token"
        body = httpx.QueryParams(captured["body"].decode())
        assert body["client_id"] == "cid"
        assert body["client_secret"] == "csecret"
        assert body["refresh_token"] == "rtoken"
        assert body["grant_type"] == "refresh_token"

    async def test_response_missing_access_token_raises(self) -> None:
        async with _client(lambda r: httpx.Response(200, json={"expires_in": 3600})) as client:
            with pytest.raises(YouTubeOAuthError, match="missing access_token"):
                await get_access_token(client, "cid", "csecret", "rtoken")

    async def test_non_200_raises_with_google_error_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"error": "invalid_grant", "error_description": "Token expired"}
            )

        async with _client(handler) as client:
            with pytest.raises(
                YouTubeOAuthError,
                match=r"youtube oauth refresh failed: HTTP 400 invalid_grant: Token expired",
            ):
                await get_access_token(client, "cid", "csecret", "rtoken")

    async def test_network_error_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        async with _client(handler) as client:
            with pytest.raises(YouTubeOAuthError, match="youtube oauth refresh failed"):
                await get_access_token(client, "cid", "csecret", "rtoken")


class TestGetAccessTokenCaching:
    """In-process cache, keyed on `(client_id, refresh_token)`."""

    async def test_second_call_is_cached_no_second_request(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            first = await get_access_token(client, "cid", "csecret", "rtoken")
            second = await get_access_token(client, "cid", "csecret", "rtoken")

        assert first == second == "test-access-token"
        assert calls == 1

    async def test_different_credential_sets_do_not_share_a_cache_entry(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload(access_token=f"token-{calls}"))

        async with _client(handler) as client:
            first = await get_access_token(client, "cid-a", "csecret", "rtoken-a")
            second = await get_access_token(client, "cid-b", "csecret", "rtoken-b")

        assert first != second
        assert calls == 2

    async def test_expired_cache_entry_triggers_a_fresh_refresh(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            await get_access_token(client, "cid", "csecret", "rtoken")
            cache_key = oauth_mod._CacheKey(client_id="cid", refresh_token="rtoken")
            oauth_mod._token_cache[cache_key].expires_at = time.monotonic() - 1
            await get_access_token(client, "cid", "csecret", "rtoken")

        assert calls == 2

    async def test_force_refresh_bypasses_a_valid_cache_entry(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            await get_access_token(client, "cid", "csecret", "rtoken")
            await get_access_token(client, "cid", "csecret", "rtoken", force_refresh=True)

        assert calls == 2


class TestTokenHasScope:
    """`token_has_scope()` -- `tokeninfo` lookup, cached per access-token value."""

    async def test_scope_present_returns_true(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.params["access_token"] == "at-1"
            return httpx.Response(200, json={"scope": f"{YOUTUBE_FORCE_SSL_SCOPE} openid"})

        async with _client(handler) as client:
            result = await token_has_scope(client, "at-1", YOUTUBE_FORCE_SSL_SCOPE)

        assert result is True

    async def test_scope_absent_returns_false(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"scope": "openid email"})

        async with _client(handler) as client:
            result = await token_has_scope(client, "at-2", YOUTUBE_FORCE_SSL_SCOPE)

        assert result is False

    async def test_result_cached_per_access_token(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"scope": YOUTUBE_FORCE_SSL_SCOPE})

        async with _client(handler) as client:
            await token_has_scope(client, "at-3", YOUTUBE_FORCE_SSL_SCOPE)
            await token_has_scope(client, "at-3", YOUTUBE_FORCE_SSL_SCOPE)

        assert calls == 1

    async def test_different_access_token_is_not_cached_together(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={"scope": YOUTUBE_FORCE_SSL_SCOPE})

        async with _client(handler) as client:
            await token_has_scope(client, "at-4", YOUTUBE_FORCE_SSL_SCOPE)
            await token_has_scope(client, "at-5", YOUTUBE_FORCE_SSL_SCOPE)

        assert calls == 2

    async def test_non_200_raises(self) -> None:
        async with _client(lambda r: httpx.Response(400)) as client:
            with pytest.raises(YouTubeOAuthError, match="tokeninfo lookup failed"):
                await token_has_scope(client, "at-6", YOUTUBE_FORCE_SSL_SCOPE)

    async def test_missing_scope_field_raises(self) -> None:
        async with _client(lambda r: httpx.Response(200, json={})) as client:
            with pytest.raises(YouTubeOAuthError, match="missing scope"):
                await token_has_scope(client, "at-7", YOUTUBE_FORCE_SSL_SCOPE)

    async def test_network_error_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        async with _client(handler) as client:
            with pytest.raises(YouTubeOAuthError, match="tokeninfo lookup failed"):
                await token_has_scope(client, "at-8", YOUTUBE_FORCE_SSL_SCOPE)


@dataclass(slots=True, frozen=True)
class _FakeCommunityTokens:
    """Local stand-in for `waddle_transports.community_credentials.CommunityTokens`.

    Not imported from `waddle_transports` -- that module is landing
    concurrently (gh-320) and may not exist on disk yet; this mirrors the
    contract's documented field shape exactly enough for
    `get_access_token_for_community`'s own `tokens.source`/
    `tokens.access_token` attribute reads.
    """

    access_token: str | None
    refresh_token: str | None
    expires_at: datetime | None
    scopes: list[str]
    source: str


class TestGetAccessTokenForCommunity:
    """`get_access_token_for_community()` -- community-token-first, env-refresh fallback."""

    async def test_community_source_returns_its_token_without_refresh_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        refresh_called = False

        async def fake_resolve(community_id: int | None, provider: str) -> _FakeCommunityTokens:
            assert community_id == 42
            assert provider == "youtube"
            return _FakeCommunityTokens(
                access_token="community-access-token",
                refresh_token=None,
                expires_at=None,
                scopes=[YOUTUBE_FORCE_SSL_SCOPE],
                source="community",
            )

        monkeypatch.setattr(oauth_mod, "resolve_community_tokens", fake_resolve)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal refresh_called
            refresh_called = True
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            token = await get_access_token_for_community(client, 42, "cid", "csecret", "rtoken")

        assert token == "community-access-token"
        assert refresh_called is False

    async def test_env_source_falls_through_to_refresh_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_resolve(community_id: int | None, provider: str) -> _FakeCommunityTokens:
            return _FakeCommunityTokens(
                access_token="env-side-token",
                refresh_token="rtoken",
                expires_at=None,
                scopes=[],
                source="env",
            )

        monkeypatch.setattr(oauth_mod, "resolve_community_tokens", fake_resolve)

        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            token = await get_access_token_for_community(client, 42, "cid", "csecret", "rtoken")

        assert token == "test-access-token"

    async def test_no_community_connection_falls_through_to_refresh_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_resolve(community_id: int | None, provider: str) -> None:
            return None

        monkeypatch.setattr(oauth_mod, "resolve_community_tokens", fake_resolve)

        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            token = await get_access_token_for_community(client, 42, "cid", "csecret", "rtoken")

        assert token == "test-access-token"

    async def test_resolver_unavailable_falls_through_to_refresh_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(oauth_mod, "resolve_community_tokens", None)

        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            token = await get_access_token_for_community(client, 42, "cid", "csecret", "rtoken")

        assert token == "test-access-token"

    async def test_resolver_failure_falls_through_to_refresh_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_resolve(community_id: int | None, provider: str) -> None:
            raise RuntimeError("hub-api unreachable")

        monkeypatch.setattr(oauth_mod, "resolve_community_tokens", fake_resolve)

        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            token = await get_access_token_for_community(client, 42, "cid", "csecret", "rtoken")

        assert token == "test-access-token"

    async def test_no_community_id_still_resolves_via_env_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_resolve(community_id: int | None, provider: str) -> None:
            assert community_id is None
            return None

        monkeypatch.setattr(oauth_mod, "resolve_community_tokens", fake_resolve)

        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            token = await get_access_token_for_community(client, None, "cid", "csecret", "rtoken")

        assert token == "test-access-token"

    async def test_force_refresh_is_forwarded_to_the_env_refresh_flow(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_resolve(community_id: int | None, provider: str) -> None:
            return None

        monkeypatch.setattr(oauth_mod, "resolve_community_tokens", fake_resolve)
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            await get_access_token_for_community(client, 42, "cid", "csecret", "rtoken")
            await get_access_token_for_community(
                client, 42, "cid", "csecret", "rtoken", force_refresh=True
            )

        assert calls == 2
