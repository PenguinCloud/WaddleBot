"""Tests for `services/kick_oauth.py` -- stored-token mode, client-credentials exchange, cache."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from services import kick_oauth as oauth_mod
from services.kick_oauth import KickOAuthError, get_access_token


@pytest.fixture(autouse=True)
def _reset_cache() -> Any:
    """The client-credentials token cache is module-level state -- isolate every test."""
    oauth_mod._token_cache.clear()
    yield
    oauth_mod._token_cache.clear()


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _token_payload(
    access_token: str = "test-app-token",  # noqa: S107 -- fixture default, not a real secret
    expires_in: int = 3600,
) -> dict[str, Any]:
    return {"access_token": access_token, "expires_in": expires_in, "token_type": "Bearer"}


class TestStoredAccessTokenMode:
    """A stored access token is always returned as-is, no network call, never cached here."""

    async def test_stored_token_returned_directly(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no network call should happen in stored-token mode")

        async with _client(handler) as client:
            token = await get_access_token(client, stored_access_token="stored-tok-123")
        assert token == "stored-tok-123"

    async def test_stored_token_takes_precedence_over_client_credentials(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("client-credentials must not run when a stored token is set")

        async with _client(handler) as client:
            token = await get_access_token(
                client,
                stored_access_token="stored-tok-123",
                client_id="cid",
                client_secret="csecret",
            )
        assert token == "stored-tok-123"

    async def test_force_refresh_is_a_no_op_in_stored_token_mode(self) -> None:
        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            token = await get_access_token(
                client, stored_access_token="stored-tok-123", force_refresh=True
            )
        assert token == "stored-tok-123"


class TestNeitherModeUsable:
    async def test_no_stored_token_and_no_client_credentials_raises(self) -> None:
        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            with pytest.raises(KickOAuthError, match="stored access token or both"):
                await get_access_token(client)

    async def test_only_client_id_without_secret_raises(self) -> None:
        async with _client(lambda r: httpx.Response(200, json=_token_payload())) as client:
            with pytest.raises(KickOAuthError, match="stored access token or both"):
                await get_access_token(client, client_id="cid")


class TestClientCredentialsExchange:
    """`get_access_token()` -- the real `client_credentials` grant request shape."""

    async def test_sends_client_credentials_grant(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = request.content
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            token = await get_access_token(client, client_id="cid", client_secret="csecret")

        assert token == "test-app-token"
        assert captured["url"] == "https://id.kick.com/oauth/token"
        body = httpx.QueryParams(captured["body"].decode())
        assert body["client_id"] == "cid"
        assert body["client_secret"] == "csecret"
        assert body["grant_type"] == "client_credentials"

    async def test_response_missing_access_token_raises(self) -> None:
        async with _client(lambda r: httpx.Response(200, json={"expires_in": 3600})) as client:
            with pytest.raises(KickOAuthError, match="missing access_token"):
                await get_access_token(client, client_id="cid", client_secret="csecret")

    async def test_non_200_raises_with_kick_error_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"error": "invalid_client", "error_description": "Bad credentials"}
            )

        async with _client(handler) as client:
            with pytest.raises(
                KickOAuthError,
                match=r"kick oauth client-credentials exchange failed: HTTP 400 "
                r"invalid_client: Bad credentials",
            ):
                await get_access_token(client, client_id="cid", client_secret="csecret")

    async def test_network_error_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        async with _client(handler) as client:
            with pytest.raises(KickOAuthError, match="exchange failed"):
                await get_access_token(client, client_id="cid", client_secret="csecret")


class TestClientCredentialsCaching:
    """In-process cache, keyed on `(client_id, client_secret)`."""

    async def test_second_call_is_cached_no_second_request(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload())

        async with _client(handler) as client:
            token1 = await get_access_token(client, client_id="cid", client_secret="csecret")
            token2 = await get_access_token(client, client_id="cid", client_secret="csecret")

        assert token1 == token2
        assert calls == 1

    async def test_different_credential_pairs_are_cached_independently(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload(access_token=f"tok-{calls}"))

        async with _client(handler) as client:
            token1 = await get_access_token(client, client_id="cid1", client_secret="csecret1")
            token2 = await get_access_token(client, client_id="cid2", client_secret="csecret2")

        assert token1 != token2
        assert calls == 2

    async def test_force_refresh_bypasses_the_cache(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload(access_token=f"tok-{calls}"))

        async with _client(handler) as client:
            token1 = await get_access_token(client, client_id="cid", client_secret="csecret")
            token2 = await get_access_token(
                client, client_id="cid", client_secret="csecret", force_refresh=True
            )

        assert token1 != token2
        assert calls == 2

    async def test_expired_cache_entry_triggers_a_refresh(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json=_token_payload(expires_in=100))

        original_monotonic = time.monotonic
        async with _client(handler) as client:
            await get_access_token(client, client_id="cid", client_secret="csecret")
            # Fast-forward past expires_in - the 60s safety margin.
            monkeypatch.setattr(time, "monotonic", lambda: original_monotonic() + 1000)
            await get_access_token(client, client_id="cid", client_secret="csecret")

        assert calls == 2
