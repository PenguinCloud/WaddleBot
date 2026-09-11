"""Tests for `services.twitch_helix.TwitchHelixClient` -- app-token mint/cache/refresh + 4 GETs."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from services.twitch_helix import TwitchHelixClient, TwitchHelixError

_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_HELIX_BASE = "https://api.twitch.tv/helix"


@pytest.fixture(autouse=True)
def _credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "test-client-secret")


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def _token_response(
    *,
    access_token: str = "app-token-1",  # noqa: S107 -- test fixture default, not a real credential
    expires_in: int = 3600,
) -> httpx.Response:
    return httpx.Response(200, json={"access_token": access_token, "expires_in": expires_in})


class TestAppTokenMintAndCache:
    async def test_missing_credentials_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TWITCH_CLIENT_ID", raising=False)
        monkeypatch.delenv("TWITCH_CLIENT_SECRET", raising=False)

        def _handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
            raise AssertionError("no HTTP call should happen without credentials")

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="twitch app credentials not configured"):
                await helix.get_user("shroud")

    async def test_token_mint_is_cached_across_calls(self) -> None:
        token_calls = 0
        helix_calls = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls, helix_calls
            if str(request.url).startswith(_TOKEN_URL):
                token_calls += 1
                return _token_response()
            helix_calls += 1
            return httpx.Response(200, json={"data": [{"id": "1", "login": "shroud"}]})

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            await helix.get_user("shroud")
            await helix.get_user("shroud")

        assert token_calls == 1
        assert helix_calls == 2

    async def test_token_endpoint_401_raises(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="invalid client")

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match=r"twitch oauth token didn't work \(401\)"):
                await helix.get_user("shroud")

    async def test_token_endpoint_non_200_non_401_raises(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal error")

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="HTTP 500"):
                await helix.get_user("shroud")

    async def test_token_response_malformed_raises(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="malformed"):
                await helix.get_user("shroud")

    async def test_token_request_network_error_wraps(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns failure", request=request)

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="token request failed"):
                await helix.get_user("shroud")


class TestHelixCallAuthHeaders:
    async def test_sends_client_id_and_bearer_headers(self) -> None:
        captured: dict[str, str] = {}

        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(_TOKEN_URL):
                return _token_response(access_token="app-token-xyz")
            captured["client_id"] = request.headers.get("Client-Id", "")
            captured["authorization"] = request.headers.get("Authorization", "")
            return httpx.Response(200, json={"data": [{"id": "1", "login": "shroud"}]})

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            await helix.get_user("shroud")

        assert captured["client_id"] == "test-client-id"
        assert captured["authorization"] == "Bearer app-token-xyz"


class TestHelix401RefreshOnce:
    async def test_single_401_triggers_one_refresh_then_succeeds(self) -> None:
        token_calls = 0
        helix_attempts = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls, helix_attempts
            if str(request.url).startswith(_TOKEN_URL):
                token_calls += 1
                return _token_response(access_token=f"token-{token_calls}")
            helix_attempts += 1
            if helix_attempts == 1:
                return httpx.Response(401, text="expired")
            return httpx.Response(200, json={"data": [{"id": "1", "login": "shroud"}]})

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            user = await helix.get_user("shroud")

        assert user["login"] == "shroud"
        assert token_calls == 2  # initial mint + one forced refresh
        assert helix_attempts == 2  # original 401 + the one retry

    async def test_persistent_401_raises_after_single_retry(self) -> None:
        token_calls = 0
        helix_attempts = 0

        def _handler(request: httpx.Request) -> httpx.Response:
            nonlocal token_calls, helix_attempts
            if str(request.url).startswith(_TOKEN_URL):
                token_calls += 1
                return _token_response(access_token=f"token-{token_calls}")
            helix_attempts += 1
            return httpx.Response(401, text="still expired")

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match=r"twitch oauth token didn't work \(401\)"):
                await helix.get_user("shroud")

        assert helix_attempts == 2  # never loops past one retry
        assert token_calls == 2


class TestHelixErrorStrings:
    async def test_rate_limited_429(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(_TOKEN_URL):
                return _token_response()
            return httpx.Response(429, text="rate limited")

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match=r"twitch api rate limited \(429\)"):
                await helix.get_user("shroud")

    async def test_user_not_found(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(_TOKEN_URL):
                return _token_response()
            return httpx.Response(200, json={"data": []})

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="twitch user 'ghostuser' not found"):
                await helix.get_user("ghostuser")

    async def test_generic_4xx_raises_with_status(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(_TOKEN_URL):
                return _token_response()
            return httpx.Response(400, text="bad request")

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="HTTP 400"):
                await helix.get_user("shroud")

    async def test_helix_response_malformed_raises(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(_TOKEN_URL):
                return _token_response()
            return httpx.Response(200, content=b"not json")

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="malformed"):
                await helix.get_user("shroud")

    async def test_helix_network_error_wraps(self) -> None:
        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(_TOKEN_URL):
                return _token_response()
            raise httpx.ConnectError("unreachable", request=request)

        async with _client(_handler) as http:
            helix = TwitchHelixClient(http)
            with pytest.raises(TwitchHelixError, match="helix request failed"):
                await helix.get_user("shroud")


class TestChannelStreamClipLookups:
    def _handler_for(
        self, path: str, data: list[dict[str, Any]]
    ) -> Callable[[httpx.Request], httpx.Response]:
        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(_TOKEN_URL):
                return _token_response()
            assert request.url.path == path
            return httpx.Response(200, json={"data": data})

        return _handler

    async def test_get_channel_returns_first_item(self) -> None:
        async with _client(
            self._handler_for("/helix/channels", [{"broadcaster_id": "1", "game_name": "Chess"}])
        ) as http:
            helix = TwitchHelixClient(http)
            channel = await helix.get_channel("1")

        assert channel is not None
        assert channel["game_name"] == "Chess"

    async def test_get_channel_returns_none_when_empty(self) -> None:
        async with _client(self._handler_for("/helix/channels", [])) as http:
            helix = TwitchHelixClient(http)
            assert await helix.get_channel("1") is None

    async def test_get_stream_returns_first_item_when_live(self) -> None:
        async with _client(
            self._handler_for(
                "/helix/streams", [{"user_id": "1", "game_name": "Chess", "viewer_count": 42}]
            )
        ) as http:
            helix = TwitchHelixClient(http)
            stream = await helix.get_stream("1")

        assert stream is not None
        assert stream["viewer_count"] == 42

    async def test_get_stream_returns_none_when_offline(self) -> None:
        async with _client(self._handler_for("/helix/streams", [])) as http:
            helix = TwitchHelixClient(http)
            assert await helix.get_stream("1") is None

    async def test_get_top_clip_returns_first_item(self) -> None:
        async with _client(
            self._handler_for(
                "/helix/clips",
                [
                    {
                        "id": "clip1",
                        "thumbnail_url": "https://x/thumb.jpg",
                        "embed_url": "https://x/e",
                    }
                ],
            )
        ) as http:
            helix = TwitchHelixClient(http)
            clip = await helix.get_top_clip("1")

        assert clip is not None
        assert clip["id"] == "clip1"

    async def test_get_top_clip_returns_none_when_no_clips(self) -> None:
        async with _client(self._handler_for("/helix/clips", [])) as http:
            helix = TwitchHelixClient(http)
            assert await helix.get_top_clip("1") is None


async def test_custom_token_url_and_api_base_are_honored() -> None:
    calls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "custom-token" in str(request.url):
            return _token_response()
        return httpx.Response(200, json={"data": [{"id": "1", "login": "shroud"}]})

    async with _client(_handler) as http:
        helix = TwitchHelixClient(
            http,
            token_url="https://custom-token.example.test/oauth2/token",
            api_base="https://custom-helix.example.test",
        )
        await helix.get_user("shroud")

    assert any("custom-token.example.test" in c for c in calls)
    assert any("custom-helix.example.test" in c for c in calls)


def test_json_serializable_sanity() -> None:
    """Smoke check that the fixture helper builds valid JSON (guards a typo'd fixture)."""
    response = _token_response()
    assert json.loads(response.content)["access_token"] == "app-token-1"
