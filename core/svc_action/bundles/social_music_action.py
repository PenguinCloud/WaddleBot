"""Social music action bundle -- enqueues Music Station song requests and replies.

Action-stage bundle for `!sr`/`!songrequest` (process stage:
`bundles.social_music_process`, cross-app routed here per gh #298's
`PROCESS_TARGET_APP_ID_KEY` mechanism -- see that bundle's docstring).
Calls hub-api's service-key-gated internal Music Station enqueue endpoint
(`POST /api/v1/internal/music/queue/requests`,
`hub_api/blueprints/v1/community_music_queue.py`) -- never the
JWT/admin-scoped `POST /api/v1/admin/<community_id>/music-station/queue/
requests` endpoint, since the requester is a viewer typing a chat
command, not an authenticated hub-api user. Auth mirrors
`core/svc_process/services/reputation_gate_client.py`'s own
`X-Service-Key` pattern against `reputation_module`'s internal endpoint.

Reply-in-place: same channel-resolution (payload first, config fallback)
and Discord/Twitch dispatch as `bundles.social_quote_action`/
`bundles.discord_send_action`/`bundles.twitch_send_action` -- each
cross-app-routed feature action bundle owns its own outbound send, since
routing goes to the FEATURE's `:action` key, never the bot's own.

Graceful degradation (task requirement): an unreachable hub-api, a
provider failure, or no track match NEVER raises out of the enqueue step
-- `_enqueue()` converts every one of those into a friendly chat reply
instead, so the pipeline always has something to send. Only the actual
outbound chat SEND (Discord/Twitch) may raise
Retryable/NonRetryableTransportError, matching every sibling action
bundle's own contract.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any

import httpx
from flask_core import StageEnvelope
from waddle_transports import NonRetryableTransportError, RetryableTransportError, TransportResult
from waddle_transports.transports.irc_relay import RelayOutboundIrcTransport

logger = logging.getLogger(__name__)

_ENQUEUE_PATH = "/api/v1/internal/music/queue/requests"
_ENQUEUE_TIMEOUT_SECONDS = 5.0

_UNAVAILABLE_REPLY = "music requests aren't available right now \U0001f427"
_NOT_FOUND_REPLY = "couldn't find that track \U0001f3b5"

#: Lazily-built, process-wide Valkey client for IRC relay (same pattern as
#: twitch_send_action.py / social_quote_action.py).
_redis_client: Any | None = None


def _get_redis_client(config: Mapping[str, Any]) -> Any:
    """Build (once) or return the cached Valkey client for the outbound IRC relay."""
    global _redis_client
    if _redis_client is None:
        import redis.asyncio as redis

        url = (
            os.environ.get("VALKEY_URL")
            or os.environ.get("REDIS_URL")
            or "redis://localhost:6379/0"
        )
        _redis_client = redis.from_url(url, decode_responses=True)
    return _redis_client


async def _enqueue(
    http_client: httpx.AsyncClient,
    *,
    community_id: int,
    url_or_query: str,
    platform: str,
    platform_user_id: str | None,
    requested_by_display: str | None,
) -> str:
    """POST to hub-api's internal Music Station enqueue endpoint; never raises.

    Returns the chat reply text for every outcome -- success, provider
    unavailable, no track match, policy-disallowed, malformed response, or
    an unreachable hub-api -- so the caller always has a friendly reply to
    send instead of failing the whole action dispatch (task's graceful-
    degradation requirement).
    """
    hub_api_base = os.getenv("HUB_API_URL", "http://hub-api:8204")
    service_api_key = os.getenv("SERVICE_API_KEY", "")
    body = {
        "communityId": community_id,
        "urlOrQuery": url_or_query,
        "platform": platform,
        "platformUserId": platform_user_id,
        "requestedByDisplay": requested_by_display,
    }

    try:
        response = await http_client.post(
            f"{hub_api_base}{_ENQUEUE_PATH}",
            json=body,
            headers={"X-Service-Key": service_api_key},
            timeout=_ENQUEUE_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "social_music_action.hub_api_unreachable community_id=%s error=%s",
            community_id,
            exc,
        )
        return _UNAVAILABLE_REPLY

    if response.status_code >= 400:
        message = ""
        try:
            error_body = response.json()
            message = str((error_body.get("error") or {}).get("message", ""))
        except ValueError:
            pass
        logger.warning(
            "social_music_action.enqueue_rejected community_id=%s status=%s message=%s",
            community_id,
            response.status_code,
            message,
        )
        if "no track found" in message.lower():
            return _NOT_FOUND_REPLY
        return _UNAVAILABLE_REPLY

    try:
        data = response.json()
        item = data["item"]
        track = item["track"]
        title = str(track["title"])
        artist = str(track["artist"])
        position = int(item["position"])
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "social_music_action.malformed_response community_id=%s error=%s",
            community_id,
            exc,
        )
        return _UNAVAILABLE_REPLY

    return f"\U0001f3b5 Added {title} — {artist} (#{position} in queue)"


async def enqueue_song_request(
    envelope: StageEnvelope,
    config: Mapping[str, Any],
    *,
    http_client: httpx.AsyncClient,
) -> TransportResult:
    """Enqueue a `!sr`/`!songrequest` request via hub-api, then reply in-place.

    Expects `envelope.event.payload["music_query"]` (the url/search query
    from `bundles.social_music_process`). Requester identity is read from
    the SAME already-tokenized fields every other bundle uses --
    `event.payload["author_id"]` (platform-native user id, never raw PII)
    and `event.actor` (display name) -- never re-derived here.

    Raises `NonRetryableTransportError` for a config/payload error or an
    unresolvable reply channel; propagates `Retryable`/
    `NonRetryableTransportError` from the outbound chat send unchanged --
    see module docstring for why the enqueue step itself never raises.
    """
    payload = envelope.event.payload
    query = payload.get("music_query")
    if not isinstance(query, str) or not query.strip():
        raise NonRetryableTransportError("music action requires 'music_query'")

    if not envelope.community:
        raise NonRetryableTransportError(
            "social music bundle: envelope.community is None (tenant-wide activation unsupported)"
        )
    try:
        community_id = int(envelope.community)
    except (TypeError, ValueError) as exc:
        raise NonRetryableTransportError(
            f"social music bundle: community identifier {envelope.community!r} "
            "is not a valid integer"
        ) from exc

    platform = envelope.event.platform.lower() if envelope.event.platform else "discord"
    raw_author_id = payload.get("author_id")
    platform_user_id = str(raw_author_id) if raw_author_id is not None else None

    text = await _enqueue(
        http_client,
        community_id=community_id,
        url_or_query=query.strip(),
        platform=platform,
        platform_user_id=platform_user_id,
        requested_by_display=envelope.event.actor,
    )

    # Resolve channel for reply-in-place -- same precedence as
    # social_quote_action.py: payload channel first, config fallback.
    payload_channel_id = payload.get("channel_id")
    payload_channel_name = payload.get("channel_name")

    if platform == "twitch":
        channel = payload_channel_name if isinstance(payload_channel_name, str) else None
        if not channel:
            channel = config.get("channel")
    else:
        channel = payload_channel_id if isinstance(payload_channel_id, str) else None
        if not channel:
            channel = config.get("channel_id")

    channel = channel if isinstance(channel, str) and channel else None
    if not channel:
        raise NonRetryableTransportError(
            "social music bundle could not resolve a channel from either "
            "envelope.event.payload['channel_id'/'channel_name'] (reply-in-place) or "
            "config['channel'/'channel_id'] (fallback)"
        )

    if platform == "twitch":
        transport = RelayOutboundIrcTransport(
            provider="twitch", redis_client=_get_redis_client(config)
        )
        return await transport.send({"channel": channel}, {"text": text})

    # Discord via guarded_request -- imported lazily, same as social_quote_action.py.
    from waddle_transports.signing import SecretResolutionError, resolve_secret
    from waddle_transports.url_guard import SSRFError, guarded_request

    token_ref = config.get("bot_token_ref")
    if not isinstance(token_ref, str) or not token_ref:
        raise NonRetryableTransportError(
            "social music bundle config missing required 'bot_token_ref'"
        )

    try:
        token = resolve_secret(token_ref)
    except SecretResolutionError as exc:
        raise NonRetryableTransportError(f"discord token resolution failed: {exc}") from exc

    api_base = config.get("api_base", "https://discord.com/api/v10")
    url = f"{api_base}/channels/{channel}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"content": text}

    try:
        response = await guarded_request(http_client, "POST", url, headers=headers, json=body)
    except SSRFError as exc:
        raise NonRetryableTransportError(f"discord API URL rejected by SSRF guard: {exc}") from exc
    except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
        raise RetryableTransportError(f"discord API request failed: {exc}") from exc

    if response.status_code == 429:
        raise RetryableTransportError("discord API rate limited", http_status=429)
    if response.status_code in (401, 403):
        raise NonRetryableTransportError(
            f"discord API rejected auth: HTTP {response.status_code}",
            http_status=response.status_code,
        )
    if 400 <= response.status_code < 500:
        raise NonRetryableTransportError(
            f"discord API returned client error: HTTP {response.status_code}",
            http_status=response.status_code,
        )
    if response.status_code >= 500:
        raise RetryableTransportError(
            f"discord API returned server error: HTTP {response.status_code}",
            http_status=response.status_code,
        )

    return TransportResult(
        transport="bundle",
        detail=f"music request reply sent, channel={channel}",
        http_status=response.status_code,
    )
