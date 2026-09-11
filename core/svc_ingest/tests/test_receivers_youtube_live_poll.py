"""Tests for `receivers.youtube_live_poll.YouTubeLivePollReceiver`.

The real Data API v3 / OAuth token endpoint calls are routed through an
`httpx.MockTransport` (injected via the constructor's `http_client`
param -- see that class's own docstring), never a live network call --
same "no real socket" precedent `test_receivers_twitch_irc.py`/
`test_discord_gateway.py` set for their own external dependency. The poll
loop's `await self._sleep(...)` calls are redirected to `_StopAfter`, a
fake that raises `asyncio.CancelledError` after `n` calls -- deterministic
loop termination without any real wait, mirroring `socket_lease.
LeasedReceiver`'s own `_sleep` field injection point.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Mapping

import httpx
import pytest
from waddle_transports import (
    Direction,
    NonRetryableTransportError,
    RetryableTransportError,
    Transport,
)

import receivers.youtube_live_poll as youtube_live_poll_module
from receivers.youtube_live_poll import (
    CONSUMES_TAG,
    YouTubeLivePollReceiver,
    _describe_403_reason,
    _describe_oauth_error,
)

_CONFIG_API_KEY: Mapping[str, object] = {
    "channel_id": "UCabc123",
    "api_key_ref": "YT_TEST_API_KEY",
}
_CONFIG_OAUTH: Mapping[str, object] = {
    "channel_id": "UCabc123",
    "client_id_ref": "YT_TEST_CLIENT_ID",
    "client_secret_ref": "YT_TEST_CLIENT_SECRET",
    "refresh_token_ref": "YT_TEST_REFRESH_TOKEN",
}


def _json_response(status_code: int, payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def _search_found(video_id: str = "vid123") -> httpx.Response:
    return _json_response(200, {"items": [{"id": {"videoId": video_id}, "snippet": {}}]})


def _search_empty() -> httpx.Response:
    return _json_response(200, {"items": []})


def _videos_with_chat(chat_id: str = "chat123") -> httpx.Response:
    return _json_response(200, {"items": [{"liveStreamingDetails": {"activeLiveChatId": chat_id}}]})


def _messages(
    items: list[dict[str, object]],
    *,
    next_page_token: str | None = None,
    polling_interval_ms: int = 5000,
) -> httpx.Response:
    body: dict[str, object] = {"items": items, "pollingIntervalMillis": polling_interval_ms}
    if next_page_token:
        body["nextPageToken"] = next_page_token
    return _json_response(200, body)


def _chat_message(
    text: str = "hello",
    *,
    author_id: str = "UCviewer1",
    display_name: str = "Viewer One",
    is_mod: bool = False,
    is_owner: bool = False,
    is_sponsor: bool = False,
    message_id: str = "msg-1",
    published_at: str = "2026-09-11T00:00:00Z",
) -> dict[str, object]:
    return {
        "id": message_id,
        "snippet": {"displayMessage": text, "publishedAt": published_at},
        "authorDetails": {
            "channelId": author_id,
            "displayName": display_name,
            "isChatModerator": is_mod,
            "isChatOwner": is_owner,
            "isChatSponsor": is_sponsor,
        },
    }


def _quota_403() -> httpx.Response:
    return _json_response(403, {"error": {"errors": [{"reason": "quotaExceeded"}]}})


def _chat_ended_403() -> httpx.Response:
    return _json_response(403, {"error": {"errors": [{"reason": "liveChatEnded"}]}})


def _oauth_token(
    token: str = "oauth-access-token",  # noqa: S107 - test fixture default, not a real secret
    expires_in: int = 3600,
) -> httpx.Response:
    return _json_response(200, {"access_token": token, "expires_in": expires_in})


class _Script:
    """Routes a `MockTransport` handler's calls to per-endpoint response queues, in order."""

    def __init__(self) -> None:
        self.search: deque[httpx.Response] = deque()
        self.videos: deque[httpx.Response] = deque()
        self.messages: deque[httpx.Response] = deque()
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/search"):
            self.calls.append("search")
            return self.search.popleft()
        if path.endswith("/videos"):
            self.calls.append("videos")
            return self.videos.popleft()
        if path.endswith("/liveChat/messages"):
            self.calls.append("messages")
            return self.messages.popleft()
        raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover - test bug


def _make_receiver(script: _Script) -> YouTubeLivePollReceiver:
    client = httpx.AsyncClient(transport=httpx.MockTransport(script.handler))
    return YouTubeLivePollReceiver(http_client=client)


class _StopAfter:
    """Fake `_sleep` raising `asyncio.CancelledError` after `n` calls -- deterministic loop exit."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if len(self.calls) >= self.n:
            raise asyncio.CancelledError


class TestTransportClassification:
    """`YouTubeLivePollReceiver` maps to `waddle_transports.Transport`.

    `name="youtube_live_poll"`, `directions={Direction.INBOUND}`.
    """

    def test_is_a_transport_subclass(self) -> None:
        assert isinstance(YouTubeLivePollReceiver(), Transport)

    def test_name_is_youtube_live_poll(self) -> None:
        assert YouTubeLivePollReceiver().name == "youtube_live_poll"

    def test_directions_is_inbound_only(self) -> None:
        assert YouTubeLivePollReceiver().directions == frozenset({Direction.INBOUND})

    def test_consumes_tag_matches_bundle_manifest(self) -> None:
        assert CONSUMES_TAG == "youtube.message"


class TestCredentialResolution:
    async def test_missing_channel_id_raises(self) -> None:
        receiver = YouTubeLivePollReceiver()
        with pytest.raises(NonRetryableTransportError, match="channel_id"):
            async for _item in receiver.receive({"api_key_ref": "X"}):
                pass  # pragma: no cover - no items yielded

    async def test_missing_all_credentials_raises(self) -> None:
        receiver = YouTubeLivePollReceiver()
        with pytest.raises(NonRetryableTransportError, match="credentials"):
            async for _item in receiver.receive({"channel_id": "UCabc123"}):
                pass  # pragma: no cover - no items yielded

    async def test_partial_oauth_trio_is_not_usable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two of the three OAuth env vars set (the third missing) -- never treated as usable."""
        receiver = YouTubeLivePollReceiver()
        monkeypatch.setenv("YT_PARTIAL_ID", "cid")
        monkeypatch.setenv("YT_PARTIAL_SECRET", "csecret")
        config = {
            "channel_id": "UCabc123",
            "client_id_ref": "YT_PARTIAL_ID",
            "client_secret_ref": "YT_PARTIAL_SECRET",
        }
        with pytest.raises(NonRetryableTransportError, match="credentials"):
            async for _item in receiver.receive(config):
                pass  # pragma: no cover - no items yielded

    async def test_oauth_trio_refs_present_but_one_env_var_itself_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All three ref keys are non-empty config strings, but one named env var is unset.

        Distinct from `test_partial_oauth_trio_is_not_usable` above (a
        ref key missing from `config` entirely) -- this exercises
        `resolve_secret` itself raising `SecretResolutionError` inside
        `_resolve_auth_mode`'s OAuth branch.
        """
        for name in ("YT_MISSING_ID_ENV", "YT_MISSING_SECRET_ENV", "YT_MISSING_REFRESH_ENV"):
            monkeypatch.delenv(name, raising=False)
        receiver = YouTubeLivePollReceiver()
        config = {
            "channel_id": "UCabc123",
            "client_id_ref": "YT_MISSING_ID_ENV",
            "client_secret_ref": "YT_MISSING_SECRET_ENV",
            "refresh_token_ref": "YT_MISSING_REFRESH_ENV",
        }
        with pytest.raises(NonRetryableTransportError, match="credentials"):
            async for _item in receiver.receive(config):
                pass  # pragma: no cover - no items yielded

    async def test_unresolvable_api_key_ref_falls_back_to_oauth_trio(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`api_key_ref` present but its env var unset -- precedence falls through to OAuth."""
        monkeypatch.delenv("YT_UNSET_KEY", raising=False)
        monkeypatch.setenv("YT_TEST_CLIENT_ID", "cid")
        monkeypatch.setenv("YT_TEST_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("YT_TEST_REFRESH_TOKEN", "rtoken")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return _oauth_token()
            if request.url.path.endswith("/search"):
                return _search_empty()
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001
        config = {"channel_id": "UCabc123", "api_key_ref": "YT_UNSET_KEY", **_CONFIG_OAUTH}

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(config):
                pass  # pragma: no cover - no items yielded


class TestReceive:
    async def test_finds_live_broadcast_and_yields_normalized_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found("vid123"))
        script.videos.append(_videos_with_chat("chat123"))
        script.messages.append(
            _messages([_chat_message("hello chat", author_id="UC1", display_name="Alice")])
        )

        receiver = _make_receiver(script)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        items = []
        with pytest.raises(asyncio.CancelledError):
            async for item in receiver.receive(_CONFIG_API_KEY):
                items.append(item)

        assert len(items) == 1
        item = items[0]
        assert item["platform"] == "youtube"
        assert item["channel_id"] == "UCabc123"
        assert item["video_id"] == "vid123"
        assert item["live_chat_id"] == "chat123"
        assert item["text"] == "hello chat"
        assert item["author_id"] == "UC1"
        assert item["display_name"] == "Alice"
        assert item["is_mod"] is False
        assert item["is_owner"] is False
        assert item["is_sponsor"] is False
        assert item["message_id"] == "msg-1"
        assert item["published_at"] == "2026-09-11T00:00:00Z"

    async def test_search_request_scopes_to_channel_live_events_and_sends_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                captured.update(dict(request.url.params))
                return _search_empty()
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

        assert captured["channelId"] == "UCabc123"
        assert captured["eventType"] == "live"
        assert captured["type"] == "video"
        assert captured["key"] == "key-abc"

    async def test_no_live_broadcast_backs_off_and_never_polls_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.extend([_search_empty(), _search_empty()])

        receiver = _make_receiver(script)
        stopper = _StopAfter(2)
        receiver._sleep = stopper  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

        assert stopper.calls == [30.0, 30.0]
        assert "messages" not in script.calls

    async def test_custom_no_broadcast_backoff_is_honored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_empty())
        receiver = _make_receiver(script)
        stopper = _StopAfter(1)
        receiver._sleep = stopper  # type: ignore[assignment]  # noqa: SLF001
        config = {**_CONFIG_API_KEY, "no_broadcast_backoff_s": 5.0}

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(config):
                pass  # pragma: no cover - no items yielded

        assert stopper.calls == [5.0]

    async def test_next_page_token_is_passed_to_the_next_poll(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        captured_tokens: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/search"):
                return _search_found()
            if path.endswith("/videos"):
                return _videos_with_chat()
            if path.endswith("/liveChat/messages"):
                captured_tokens.append(request.url.params.get("pageToken"))
                if len(captured_tokens) == 1:
                    return _messages([], next_page_token="tok-2")
                return _messages([_chat_message("second")])
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(2)  # type: ignore[assignment]  # noqa: SLF001

        items = []
        with pytest.raises(asyncio.CancelledError):
            async for item in receiver.receive(_CONFIG_API_KEY):
                items.append(item)

        assert captured_tokens == [None, "tok-2"]
        assert [i["text"] for i in items] == ["second"]

    async def test_polling_interval_from_api_is_converted_to_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found())
        script.videos.append(_videos_with_chat())
        script.messages.append(_messages([_chat_message("hi")], polling_interval_ms=8000))

        receiver = _make_receiver(script)
        stopper = _StopAfter(1)
        receiver._sleep = stopper  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

        assert stopper.calls == [8.0]

    async def test_polling_interval_floor_prevents_a_tight_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found())
        script.videos.append(_videos_with_chat())
        script.messages.append(_messages([_chat_message("hi")], polling_interval_ms=100))

        receiver = _make_receiver(script)
        stopper = _StopAfter(1)
        receiver._sleep = stopper  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

        assert stopper.calls == [2.0]

    async def test_chat_max_results_config_is_passed_to_the_messages_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/search"):
                return _search_found()
            if path.endswith("/videos"):
                return _videos_with_chat()
            if path.endswith("/liveChat/messages"):
                captured["maxResults"] = str(request.url.params.get("maxResults"))
                return _messages([])
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001
        config = {**_CONFIG_API_KEY, "chat_max_results": 50}

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(config):
                pass  # pragma: no cover - no items yielded

        assert captured["maxResults"] == "50"

    async def test_quota_error_backs_off_without_crashing_and_recovers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.extend([_quota_403(), _search_found()])
        script.videos.append(_videos_with_chat())
        script.messages.append(_messages([_chat_message("hi")]))

        receiver = _make_receiver(script)
        stopper = _StopAfter(2)
        receiver._sleep = stopper  # type: ignore[assignment]  # noqa: SLF001

        items = []
        with pytest.raises(asyncio.CancelledError):
            async for item in receiver.receive(_CONFIG_API_KEY):
                items.append(item)

        assert len(items) == 1
        assert stopper.calls[0] == 30.0

    async def test_stops_cleanly_after_max_consecutive_quota_errors(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.extend([_quota_403(), _quota_403(), _quota_403()])

        receiver = _make_receiver(script)
        stopper = _StopAfter(100)  # never reached -- generator ends on its own via `return`
        receiver._sleep = stopper  # type: ignore[assignment]  # noqa: SLF001
        config = {**_CONFIG_API_KEY, "max_consecutive_quota_errors": 3}

        with caplog.at_level(logging.WARNING, logger="receivers.youtube_live_poll"):
            items = [item async for item in receiver.receive(config)]

        assert items == []
        assert len(script.search) == 0  # all 3 scripted quota responses were consumed
        assert stopper.calls == [30.0, 30.0]  # backs off after error #1 and #2, stops on #3
        warn_logs = [r for r in caplog.records if "gateway.youtube_quota_exhausted" in r.message]
        assert len(warn_logs) == 1

    async def test_chat_ended_403_resets_state_and_rediscovers_broadcast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.extend([_search_found("vid1"), _search_found("vid2")])
        script.videos.extend([_videos_with_chat("chat1"), _videos_with_chat("chat2")])
        script.messages.extend([_chat_ended_403(), _messages([_chat_message("back again")])])

        receiver = _make_receiver(script)
        receiver._sleep = _StopAfter(2)  # type: ignore[assignment]  # noqa: SLF001

        items = []
        with pytest.raises(asyncio.CancelledError):
            async for item in receiver.receive(_CONFIG_API_KEY):
                items.append(item)

        assert len(items) == 1
        assert items[0]["video_id"] == "vid2"
        assert items[0]["live_chat_id"] == "chat2"

    async def test_message_without_display_message_is_skipped_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found())
        script.videos.append(_videos_with_chat())
        malformed = {"id": "msg-x", "snippet": {}, "authorDetails": {"channelId": "UC1"}}
        script.messages.append(_messages([malformed, _chat_message("real message")]))

        receiver = _make_receiver(script)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        items = []
        with pytest.raises(asyncio.CancelledError):
            async for item in receiver.receive(_CONFIG_API_KEY):
                items.append(item)

        assert len(items) == 1
        assert items[0]["text"] == "real message"

    async def test_missing_author_details_default_safely(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found())
        script.videos.append(_videos_with_chat())
        item = {"id": "msg-1", "snippet": {"displayMessage": "hi"}, "authorDetails": {}}
        script.messages.append(_messages([item]))

        receiver = _make_receiver(script)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        items = []
        with pytest.raises(asyncio.CancelledError):
            async for received in receiver.receive(_CONFIG_API_KEY):
                items.append(received)

        assert items[0]["author_id"] is None
        assert items[0]["display_name"] is None
        assert items[0]["is_mod"] is False
        assert items[0]["is_owner"] is False
        assert items[0]["is_sponsor"] is False

    async def test_oauth_mode_used_when_api_key_ref_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_CLIENT_ID", "cid")
        monkeypatch.setenv("YT_TEST_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("YT_TEST_REFRESH_TOKEN", "rtoken")
        captured_auth_headers: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return _oauth_token("access-1")
            if request.url.path.endswith("/search"):
                captured_auth_headers.append(request.headers.get("authorization"))
                return _search_empty()
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_OAUTH):
                pass  # pragma: no cover - no items yielded

        assert captured_auth_headers == ["Bearer access-1"]

    async def test_oauth_token_is_cached_across_search_and_videos_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_CLIENT_ID", "cid")
        monkeypatch.setenv("YT_TEST_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("YT_TEST_REFRESH_TOKEN", "rtoken")
        oauth_calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                oauth_calls["count"] += 1
                return _oauth_token("access-1")
            path = request.url.path
            if path.endswith("/search"):
                return _search_found()
            if path.endswith("/videos"):
                return _videos_with_chat()
            if path.endswith("/liveChat/messages"):
                return _messages([])
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_OAUTH):
                pass  # pragma: no cover - no items yielded

        assert oauth_calls["count"] == 1

    async def test_401_forces_one_oauth_refresh_and_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_CLIENT_ID", "cid")
        monkeypatch.setenv("YT_TEST_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("YT_TEST_REFRESH_TOKEN", "rtoken")
        oauth_calls = {"count": 0}
        search_calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                oauth_calls["count"] += 1
                return _oauth_token(f"access-{oauth_calls['count']}")
            if request.url.path.endswith("/search"):
                search_calls["count"] += 1
                if search_calls["count"] == 1:
                    return _json_response(401, {"error": "invalid_token"})
                return _search_empty()
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_OAUTH):
                pass  # pragma: no cover - no items yielded

        assert oauth_calls["count"] == 2
        assert search_calls["count"] == 2

    async def test_injected_http_client_is_used_as_is_and_not_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Caller-owned client lifecycle -- the receiver never calls `aclose()` on it."""
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_empty())

        client = httpx.AsyncClient(transport=httpx.MockTransport(script.handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

        assert client.is_closed is False
        await client.aclose()


class TestDescribe403Reason:
    """`_describe_403_reason` -- duplicated from `hub_api/services/music_providers/youtube.py`."""

    def test_invalid_json_body_returns_forbidden(self) -> None:
        response = httpx.Response(403, content=b"not json")
        assert _describe_403_reason(response) == "forbidden"

    def test_non_dict_error_returns_forbidden(self) -> None:
        response = httpx.Response(403, json={"error": "oops"})
        assert _describe_403_reason(response) == "forbidden"

    def test_empty_errors_list_falls_back_to_status(self) -> None:
        response = httpx.Response(
            403, json={"error": {"errors": [], "status": "PERMISSION_DENIED"}}
        )
        assert _describe_403_reason(response) == "PERMISSION_DENIED"

    def test_no_errors_falls_back_to_message(self) -> None:
        response = httpx.Response(403, json={"error": {"message": "Forbidden request"}})
        assert _describe_403_reason(response) == "Forbidden request"

    def test_completely_empty_error_returns_forbidden(self) -> None:
        response = httpx.Response(403, json={"error": {}})
        assert _describe_403_reason(response) == "forbidden"


class TestDescribeOAuthError:
    def test_invalid_json_body_returns_unknown_error(self) -> None:
        response = httpx.Response(400, content=b"not json")
        assert _describe_oauth_error(response) == "unknown error"

    def test_non_dict_payload_returns_unknown_error(self) -> None:
        response = httpx.Response(400, json=["not", "a", "dict"])
        assert _describe_oauth_error(response) == "unknown error"

    def test_error_and_description_are_combined(self) -> None:
        response = httpx.Response(
            400, json={"error": "invalid_grant", "error_description": "Token expired"}
        )
        assert _describe_oauth_error(response) == "invalid_grant: Token expired"

    def test_error_only_is_returned_as_is(self) -> None:
        response = httpx.Response(400, json={"error": "invalid_grant"})
        assert _describe_oauth_error(response) == "invalid_grant"

    def test_neither_field_returns_unknown_error(self) -> None:
        response = httpx.Response(400, json={})
        assert _describe_oauth_error(response) == "unknown error"


class TestReceiveErrorPaths:
    async def test_receive_without_injected_client_builds_and_closes_its_own(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No `http_client` given -- `receive()` takes the real `async with httpx.AsyncClient()`.

        Scripted to actually find a broadcast and yield one message, so
        this also exercises the item flowing through that branch's own
        `yield item` delegation line, not just client construction.
        """
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found())
        script.videos.append(_videos_with_chat())
        script.messages.append(_messages([_chat_message("hi")]))
        real_async_client = httpx.AsyncClient
        created_clients: list[httpx.AsyncClient] = []

        def _factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
            kwargs["transport"] = httpx.MockTransport(script.handler)
            client = real_async_client(*args, **kwargs)  # type: ignore[arg-type]
            created_clients.append(client)
            return client

        monkeypatch.setattr(youtube_live_poll_module.httpx, "AsyncClient", _factory)
        receiver = YouTubeLivePollReceiver()
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        items = []
        with pytest.raises(asyncio.CancelledError):
            async for item in receiver.receive(_CONFIG_API_KEY):
                items.append(item)

        assert [i["text"] for i in items] == ["hi"]
        assert len(created_clients) == 1
        assert created_clients[0].is_closed is True

    async def test_quota_ceiling_reached_while_polling_an_established_chat(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Quota errors on `liveChat/messages` (not `search`) also count toward the ceiling."""
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found())
        script.videos.append(_videos_with_chat())
        script.messages.extend([_quota_403(), _quota_403()])

        receiver = _make_receiver(script)
        stopper = _StopAfter(100)
        receiver._sleep = stopper  # type: ignore[assignment]  # noqa: SLF001
        config = {**_CONFIG_API_KEY, "max_consecutive_quota_errors": 2}

        with caplog.at_level(logging.WARNING, logger="receivers.youtube_live_poll"):
            items = [item async for item in receiver.receive(config)]

        assert items == []
        assert stopper.calls == [30.0]
        warn_logs = [r for r in caplog.records if "gateway.youtube_quota_exhausted" in r.message]
        assert len(warn_logs) == 1

    async def test_videos_list_with_no_items_yields_no_live_chat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_search_found("vid123"))
        script.videos.append(_json_response(200, {"items": []}))

        receiver = _make_receiver(script)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(asyncio.CancelledError):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

        assert script.calls == ["search", "videos"]

    async def test_oauth_token_network_failure_raises_retryable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_CLIENT_ID", "cid")
        monkeypatch.setenv("YT_TEST_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("YT_TEST_REFRESH_TOKEN", "rtoken")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                raise httpx.ConnectError("boom", request=request)
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(RetryableTransportError, match="oauth refresh failed"):
            async for _item in receiver.receive(_CONFIG_OAUTH):
                pass  # pragma: no cover - no items yielded

    async def test_oauth_token_non_200_response_raises_non_retryable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_CLIENT_ID", "cid")
        monkeypatch.setenv("YT_TEST_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("YT_TEST_REFRESH_TOKEN", "rtoken")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return _json_response(400, {"error": "invalid_grant"})
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(NonRetryableTransportError, match="oauth refresh failed"):
            async for _item in receiver.receive(_CONFIG_OAUTH):
                pass  # pragma: no cover - no items yielded

    async def test_oauth_token_response_missing_access_token_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_CLIENT_ID", "cid")
        monkeypatch.setenv("YT_TEST_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("YT_TEST_REFRESH_TOKEN", "rtoken")

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "oauth2.googleapis.com":
                return _json_response(200, {"expires_in": 3600})
            raise AssertionError(f"unexpected request: {request.url}")  # pragma: no cover

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(NonRetryableTransportError, match="missing access_token"):
            async for _item in receiver.receive(_CONFIG_OAUTH):
                pass  # pragma: no cover - no items yielded

    async def test_data_api_network_failure_raises_retryable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        receiver = YouTubeLivePollReceiver(http_client=client)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(RetryableTransportError, match="request failed"):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

    async def test_data_api_5xx_raises_retryable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_json_response(503, {}))

        receiver = _make_receiver(script)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(RetryableTransportError, match="HTTP 503"):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded

    async def test_data_api_bad_request_raises_non_retryable_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("YT_TEST_API_KEY", "key-abc")
        script = _Script()
        script.search.append(_json_response(400, {}))

        receiver = _make_receiver(script)
        receiver._sleep = _StopAfter(1)  # type: ignore[assignment]  # noqa: SLF001

        with pytest.raises(NonRetryableTransportError, match="HTTP 400"):
            async for _item in receiver.receive(_CONFIG_API_KEY):
                pass  # pragma: no cover - no items yielded
