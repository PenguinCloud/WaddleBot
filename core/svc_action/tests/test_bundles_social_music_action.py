"""Tests for `bundles.social_music_action.enqueue_song_request`.

Covers: the enqueue HTTP payload posted to hub-api's internal endpoint,
success reply-in-place via Twitch/Discord, friendly-reply graceful
degradation on a no-match/provider-unavailable/unreachable hub-api, and
input validation.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from flask_core import PlatformEvent, StageEnvelope
from waddle_transports import NonRetryableTransportError

from bundles.social_music_action import (
    _STATUS_CHECK_KEY,
    _STATUS_ENABLED_REPLY,
    _STATUS_OFFLINE_REPLY,
    _format_time_till_played,
    enqueue_song_request,
)

_ENQUEUE_URL_FRAGMENT = "/api/v1/internal/music/queue/requests"
_STATUS_URL_FRAGMENT = "/api/v1/internal/music/status"


def _hub_api_item(eta_seconds: int | None = 187) -> dict[str, Any]:
    return {
        "success": True,
        "item": {
            "id": 1,
            "communityId": 42,
            "track": {
                "provider": "youtube",
                "externalId": "dQw4w9WgXcQ",
                "title": "Never Gonna Give You Up",
                "artist": "Rick Astley",
                "durationMs": 213000,
                "artworkUrl": None,
                "url": "https://youtu.be/dQw4w9WgXcQ",
            },
            "position": 3,
            "status": "queued",
            "source": "request",
            "playlistId": None,
            "requestedBy": None,
            "addedAt": None,
            "startedAt": None,
            "endedAt": None,
            "etaSeconds": eta_seconds,
        },
    }


_HUB_API_ITEM: dict[str, Any] = _hub_api_item()
_SUCCESS_TEXT = "added to the queue: Never Gonna Give You Up - Rick Astley - ~3m 07s"


def _envelope(
    payload: dict[str, object] | None = None,
    *,
    platform: str = "twitch",
    community: str | None = "42",
    actor: str | None = "penguin",
) -> StageEnvelope:
    default_payload: dict[str, object] = {
        "music_query": "never gonna give you up",
        "channel_id": "123",
        "channel_name": "testchannel",
        "author_id": "platform-user-1",
    }
    return StageEnvelope(
        tenant="global",
        community=community,
        app_id="waddles.social.music.default",
        stage="action",
        event=PlatformEvent(
            platform=platform,
            event_type="message",
            actor=actor,
            payload=payload if payload is not None else default_payload,
            occurred_at="2026-09-09T00:00:00Z",
        ),
        ts="2026-09-09T00:00:00Z",
    )


def _config(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "bot_token_ref": "TEST_DISCORD_TOKEN",
        "api_base": "https://8.8.8.8/v1",
        "channel_id": "fallback-chan",
    }
    base.update(overrides)
    return base


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


def _relay_transport(sent: dict[str, Any]) -> AsyncMock:
    """A fake `RelayOutboundIrcTransport` recording the (target, message) it was sent."""
    transport = AsyncMock()

    async def _send(target: dict[str, object], message: dict[str, object]) -> MagicMock:
        sent["target"] = target
        sent["message"] = message
        return MagicMock(transport="relay", detail="sent", http_status=200)

    transport.send = _send
    return transport


class TestFormatTimeTillPlayed:
    """`_format_time_till_played()` -- the `<time-till-played>` field, every branch."""

    def test_next_up_when_eta_zero(self) -> None:
        assert _format_time_till_played(0, position=1) == "next up"

    def test_next_up_when_eta_negative(self) -> None:
        """Defensive: a clock-skew/stale `started_at` must never render a negative time."""
        assert _format_time_till_played(-5, position=1) == "next up"

    def test_seconds_only_under_a_minute(self) -> None:
        assert _format_time_till_played(45, position=2) == "~45s"

    def test_minutes_and_seconds(self) -> None:
        assert _format_time_till_played(220, position=3) == "~3m 40s"

    def test_hours_and_minutes_no_seconds(self) -> None:
        assert _format_time_till_played(3720, position=5) == "~1h 02m"

    def test_none_eta_falls_back_to_position_count(self) -> None:
        assert _format_time_till_played(None, position=4) == "3 ahead"

    def test_none_eta_position_one_is_zero_ahead(self) -> None:
        assert _format_time_till_played(None, position=1) == "0 ahead"


class TestEnqueuePayload:
    """The exact HTTP call made to hub-api's internal enqueue endpoint."""

    async def test_posts_correct_enqueue_payload_and_service_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SERVICE_API_KEY", "s3cr3t")
        monkeypatch.setenv("HUB_API_URL", "https://hub-api.internal")
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["service_key"] = request.headers.get("x-service-key")
            captured["body"] = json.loads(request.content)
            return httpx.Response(201, json=_HUB_API_ITEM)

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(_envelope(), _config(), http_client=client)

        assert captured["url"] == f"https://hub-api.internal{_ENQUEUE_URL_FRAGMENT}"
        assert captured["method"] == "POST"
        assert captured["service_key"] == "s3cr3t"
        assert captured["body"] == {
            "communityId": 42,
            "urlOrQuery": "never gonna give you up",
            "platform": "twitch",
            "platformUserId": "platform-user-1",
            "requestedByDisplay": "penguin",
        }


class TestEnqueueSuccess:
    """Successful enqueue -> chat reply with title/artist/position."""

    async def test_success_reply_sent_via_twitch(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json=_HUB_API_ITEM)

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(
                    _envelope(platform="twitch"), _config(), http_client=client
                )

        assert sent["message"]["text"] == _SUCCESS_TEXT
        assert sent["target"] == {"channel": "testchannel"}

    async def test_success_reply_sent_via_discord(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_DISCORD_TOKEN", "tok")
        discord_call: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if _ENQUEUE_URL_FRAGMENT in str(request.url):
                return httpx.Response(201, json=_HUB_API_ITEM)
            discord_call["body"] = json.loads(request.content)
            discord_call["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"id": "999"})

        async with _client(handler) as client:
            result = await enqueue_song_request(
                _envelope(platform="discord"), _config(), http_client=client
            )

        assert result.transport == "bundle"
        assert discord_call["body"]["content"] == _SUCCESS_TEXT
        assert discord_call["auth"] == "Bot tok"

    async def test_success_reply_next_up_when_eta_zero(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json=_hub_api_item(eta_seconds=0))

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(
                    _envelope(platform="twitch"), _config(), http_client=client
                )

        assert sent["message"]["text"] == (
            "added to the queue: Never Gonna Give You Up - Rick Astley - next up"
        )

    async def test_success_reply_falls_back_to_position_count_when_eta_missing(self) -> None:
        """Schema/response gap: hub-api didn't/couldn't compute `etaSeconds` -> `<N> ahead`."""

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json=_hub_api_item(eta_seconds=None))

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(
                    _envelope(platform="twitch"), _config(), http_client=client
                )

        assert sent["message"]["text"] == (
            "added to the queue: Never Gonna Give You Up - Rick Astley - 2 ahead"
        )


class TestStatusCheck:
    """`!sr status` dispatch -- `music_status_check` payload flag routes here, not `_enqueue()`."""

    def _status_envelope(self, *, platform: str = "twitch") -> StageEnvelope:
        return _envelope(
            payload={
                _STATUS_CHECK_KEY: True,
                "channel_id": "123",
                "channel_name": "testchannel",
                "author_id": "platform-user-1",
            },
            platform=platform,
        )

    async def test_enabled_state_replies_enabled(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "state": "enabled",
                        "cause": None,
                        "provider": "spotify",
                        "queue_length": 2,
                    },
                    "meta": {"version": 1},
                },
            )

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(self._status_envelope(), _config(), http_client=client)

        assert sent["message"]["text"] == _STATUS_ENABLED_REPLY

    async def test_error_state_replies_with_cause(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "state": "error",
                        "cause": "spotify oauth token didn't work (401)",
                        "provider": "spotify",
                        "queue_length": 0,
                    },
                    "meta": {"version": 1},
                },
            )

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(self._status_envelope(), _config(), http_client=client)

        assert sent["message"]["text"] == (
            "song requests: error - spotify oauth token didn't work (401)"
        )

    async def test_hub_api_unreachable_replies_offline(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(self._status_envelope(), _config(), http_client=client)

        assert sent["message"]["text"] == _STATUS_OFFLINE_REPLY

    async def test_non_2xx_replies_offline(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"success": False, "error": {"message": "boom"}})

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(self._status_envelope(), _config(), http_client=client)

        assert sent["message"]["text"] == _STATUS_OFFLINE_REPLY

    async def test_malformed_response_replies_offline(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "success", "data": {}})

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(self._status_envelope(), _config(), http_client=client)

        assert sent["message"]["text"] == _STATUS_OFFLINE_REPLY

    async def test_status_check_requests_get_not_post(self) -> None:
        captured: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {
                        "state": "enabled",
                        "cause": None,
                        "provider": "spotify",
                        "queue_length": 0,
                    },
                    "meta": {"version": 1},
                },
            )

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(self._status_envelope(), _config(), http_client=client)

        assert captured["method"] == "GET"
        assert _STATUS_URL_FRAGMENT in captured["url"]
        assert "community_id=42" in captured["url"]


class TestEnqueueFriendlyReplies:
    """Graceful degradation: enqueue failures never raise, only produce a friendly reply."""

    async def test_no_track_found_returns_not_found_reply(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                422,
                json={
                    "success": False,
                    "error": {"message": "No track found for 'xyz'", "code": "UNPROCESSABLE"},
                },
            )

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(
                    _envelope(platform="twitch"), _config(), http_client=client
                )

        assert sent["message"]["text"] == "couldn't find that track \U0001f3b5"

    async def test_provider_unavailable_returns_generic_friendly_reply(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                422,
                json={
                    "success": False,
                    "error": {
                        "message": "youtube provider is not available right now",
                        "code": "UNPROCESSABLE",
                    },
                },
            )

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(
                    _envelope(platform="twitch"), _config(), http_client=client
                )

        assert sent["message"]["text"] == "music requests aren't available right now \U0001f427"

    async def test_hub_api_unreachable_returns_friendly_reply_pipeline_continues(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                result = await enqueue_song_request(
                    _envelope(platform="twitch"), _config(), http_client=client
                )

        assert sent["message"]["text"] == "music requests aren't available right now \U0001f427"
        assert result.detail == "sent"

    async def test_disabled_policy_returns_generic_friendly_reply(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "success": False,
                    "error": {
                        "message": "Song requests are disabled for this community",
                        "code": "FORBIDDEN",
                    },
                },
            )

        sent: dict[str, Any] = {}
        async with _client(handler) as client:
            with patch(
                "bundles.social_music_action.RelayOutboundIrcTransport",
                return_value=_relay_transport(sent),
            ):
                await enqueue_song_request(
                    _envelope(platform="twitch"), _config(), http_client=client
                )

        assert sent["message"]["text"] == "music requests aren't available right now \U0001f427"


class TestValidation:
    """Payload/config errors -- these DO raise (unlike enqueue failures above)."""

    async def test_missing_music_query_raises_non_retryable(self) -> None:
        async with _client(lambda _r: httpx.Response(200)) as client:
            with pytest.raises(NonRetryableTransportError, match="music_query"):
                await enqueue_song_request(
                    _envelope(payload={"channel_id": "1"}), _config(), http_client=client
                )

    async def test_blank_music_query_raises_non_retryable(self) -> None:
        async with _client(lambda _r: httpx.Response(200)) as client:
            with pytest.raises(NonRetryableTransportError, match="music_query"):
                await enqueue_song_request(
                    _envelope(payload={"music_query": "   "}), _config(), http_client=client
                )

    async def test_missing_community_raises_non_retryable(self) -> None:
        async with _client(lambda _r: httpx.Response(200)) as client:
            with pytest.raises(NonRetryableTransportError, match="community"):
                await enqueue_song_request(
                    _envelope(community=None), _config(), http_client=client
                )

    async def test_unresolvable_channel_raises_non_retryable(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json=_HUB_API_ITEM)

        async with _client(handler) as client:
            with pytest.raises(NonRetryableTransportError, match="channel"):
                await enqueue_song_request(
                    _envelope(payload={"music_query": "x"}, platform="twitch"),
                    _config(channel=None, channel_id=None),
                    http_client=client,
                )


class TestDiscordSendFailures:
    """Discord send-step failures -- regression coverage for gh live-incident 401.

    A valid bot token sent with the wrong `Authorization` scheme (`Bearer`
    instead of `Bot`) is rejected by Discord with a bare 401 that looks
    identical to an actually-invalid/missing token. These assert both the
    correct `Bot` scheme is used (see `TestEnqueueSuccess.
    test_success_reply_sent_via_discord`) and that a genuine 401 raises a
    specific, non-retryable error naming the `bot_token_ref` that failed --
    never a bare "HTTP 401".
    """

    async def test_discord_401_raises_non_retryable_naming_token_ref(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("TEST_DISCORD_TOKEN", "s3cr3tvalue12345")

        def handler(request: httpx.Request) -> httpx.Response:
            if _ENQUEUE_URL_FRAGMENT in str(request.url):
                return httpx.Response(201, json=_HUB_API_ITEM)
            return httpx.Response(401, json={"message": "401: Unauthorized"})

        async with _client(handler) as client:
            with (
                caplog.at_level("WARNING"),
                pytest.raises(
                    NonRetryableTransportError,
                    match=r"bot_token_ref='TEST_DISCORD_TOKEN'.*HTTP 401",
                ),
            ):
                await enqueue_song_request(
                    _envelope(platform="discord"), _config(), http_client=client
                )

        assert "social_music_action.discord_send_rejected" in caplog.text
        assert "TEST_DISCORD_TOKEN" in caplog.text
        # the resolved secret VALUE (not its env-var name) must never log
        assert "s3cr3tvalue12345" not in caplog.text

    async def test_missing_bot_token_ref_raises_specific_env_error(self) -> None:
        async with _client(lambda _r: httpx.Response(201, json=_HUB_API_ITEM)) as client:
            with pytest.raises(
                NonRetryableTransportError,
                match=r"secret_ref 'UNSET_DISCORD_TOKEN' is not set in the environment",
            ):
                await enqueue_song_request(
                    _envelope(platform="discord"),
                    _config(bot_token_ref="UNSET_DISCORD_TOKEN"),
                    http_client=client,
                )
