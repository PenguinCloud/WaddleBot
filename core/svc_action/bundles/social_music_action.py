"""Social music action bundle -- enqueues Music Station song requests, `!sr status`, and replies.

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

`enqueue_song_request()` is also `!sr status`'s entry point -- the SAME
`PROCESS_TARGET_APP_ID_KEY` routing sends BOTH subcommands to this app's
`:action` key, and the entry-point name itself is pinned by `alembic/
versions/0009_music_catalog.py`'s `app_catalog` seed row, so it can't be
renamed/split into two bindings without a migration (out of scope here).
A `music_status_check` payload flag (set by `social_music_process.py`
when the flag is enabled) distinguishes the two at the top of the
function; `_check_status()` calls hub-api's `GET /api/v1/internal/music/
status` and maps the result to one of `!sr status`'s four exact replies.

Reply-in-place: same channel-resolution (payload first, config fallback)
and Discord/Twitch dispatch as `bundles.social_quote_action`/
`bundles.discord_send_action`/`bundles.twitch_send_action` -- each
cross-app-routed feature action bundle owns its own outbound send, since
routing goes to the FEATURE's `:action` key, never the bot's own. Shared
by both subcommands via `_send_reply()`.

Graceful degradation (task requirement): an unreachable hub-api, a
provider failure, or no track match NEVER raises out of the enqueue/
status-check step -- `_enqueue()`/`_check_status()` convert every one of
those into a friendly chat reply instead, so the pipeline always has
something to send. Only the actual outbound chat SEND (Discord/Twitch)
may raise Retryable/NonRetryableTransportError, matching every sibling
action bundle's own contract.
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
_STATUS_PATH = "/api/v1/internal/music/status"
_ENQUEUE_TIMEOUT_SECONDS = 5.0
_STATUS_TIMEOUT_SECONDS = 5.0

_UNAVAILABLE_REPLY = "music requests aren't available right now \U0001f427"
_NOT_FOUND_REPLY = "couldn't find that track \U0001f3b5"

#: Payload flag `social_music_process.py` sets (same string literal convention
#: as `music_query` -- no shared import between the two bundle processes) to
#: route an `!sr status` invocation here instead of the enqueue path.
_STATUS_CHECK_KEY = "music_status_check"

#: `!sr status`'s four exact allowed replies (task requirement -- every
#: error path must land on one of these, never silence). `enabled`/`error -
#: <cause>` come from hub-api's own `state`/`cause`; `offline` is this
#: bundle's own interpretation of an unreachable/non-2xx/malformed hub-api
#: response -- see `_check_status()`.
_STATUS_ENABLED_REPLY = "song requests: enabled"
_STATUS_OFFLINE_REPLY = "song requests: offline"

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


def _format_time_till_played(eta_seconds: int | None, position: int) -> str:
    """Render the third `<time-till-played>` field of the enqueue reply.

    `eta_seconds is None` -- hub-api couldn't compute one, see
    `community_music_queue_service._compute_eta_seconds()`'s own docstring
    for when that happens -- falls back to a bare queue-position count
    (`"<N> ahead"`). `eta_seconds <= 0` means "next up": nothing queued
    ahead of this item and nothing currently playing. Otherwise renders
    `~Xh YYm` (hours, no seconds) or `~Xm YYs` (minutes+seconds) or `~Xs`.
    """
    if eta_seconds is None:
        ahead = max(0, position - 1)
        return f"{ahead} ahead"
    if eta_seconds <= 0:
        return "next up"

    hours, remainder = divmod(eta_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"~{hours}h {minutes:02d}m"
    if minutes > 0:
        return f"~{minutes}m {seconds:02d}s"
    return f"~{seconds}s"


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

    logger.debug(
        "social_music_action.enqueue_request community_id=%s platform=%s", community_id, platform
    )

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

    logger.debug(
        "social_music_action.enqueue_response community_id=%s status=%s",
        community_id,
        response.status_code,
    )

    if response.status_code >= 400:
        message = ""
        try:
            error_body = response.json()
            message = str((error_body.get("error") or {}).get("message", ""))
        except ValueError:
            pass
        logger.warning(
            "social_music_action.enqueue_rejected community_id=%s status=%s message=%s "
            "url=%s body=%s",
            community_id,
            response.status_code,
            message,
            response.request.url
            if response.request is not None
            else f"{hub_api_base}{_ENQUEUE_PATH}",
            response.text[:300],
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
        eta_raw = item.get("etaSeconds")
        eta_is_number = isinstance(eta_raw, (int, float)) and not isinstance(eta_raw, bool)
        eta_seconds = int(eta_raw) if eta_is_number else None
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "social_music_action.malformed_response community_id=%s error=%s",
            community_id,
            exc,
        )
        return _UNAVAILABLE_REPLY

    time_till_played = _format_time_till_played(eta_seconds, position)
    logger.debug(
        "social_music_action.enqueue_reply_chosen community_id=%s position=%s eta_seconds=%s",
        community_id,
        position,
        eta_seconds,
    )
    return f"added to the queue: {title} - {artist} - {time_till_played}"


async def _check_status(http_client: httpx.AsyncClient, *, community_id: int) -> str:
    """GET hub-api's internal music-status endpoint; maps it to one of `!sr status`'s 4 replies.

    Never raises, never returns anything other than the four allowed
    reply strings (task requirement). `offline` covers an unreachable
    hub-api, a non-2xx response, AND a malformed 2xx body -- hub-api's
    own `state` is only ever `"enabled"`/`"error"`, see that endpoint's
    own docstring for why `"offline"` is entirely this function's call.
    """
    hub_api_base = os.getenv("HUB_API_URL", "http://hub-api:8204")
    service_api_key = os.getenv("SERVICE_API_KEY", "")

    logger.debug("social_music_action.status_check_request community_id=%s", community_id)

    try:
        response = await http_client.get(
            f"{hub_api_base}{_STATUS_PATH}",
            params={"community_id": community_id},
            headers={"X-Service-Key": service_api_key},
            timeout=_STATUS_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning(
            "social_music_action.status_hub_api_unreachable community_id=%s error=%s",
            community_id,
            exc,
        )
        return _STATUS_OFFLINE_REPLY

    logger.debug(
        "social_music_action.status_response community_id=%s status=%s",
        community_id,
        response.status_code,
    )

    if response.status_code >= 400:
        logger.warning(
            "social_music_action.status_rejected community_id=%s status=%s body=%s",
            community_id,
            response.status_code,
            response.text[:300],
        )
        return _STATUS_OFFLINE_REPLY

    try:
        payload = response.json()
        data = payload["data"]
        state = str(data["state"])
        cause = data.get("cause")
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "social_music_action.status_malformed_response community_id=%s error=%s",
            community_id,
            exc,
        )
        return _STATUS_OFFLINE_REPLY

    logger.debug(
        "social_music_action.status_reply_chosen community_id=%s state=%s", community_id, state
    )
    if state == "enabled":
        return _STATUS_ENABLED_REPLY
    if state == "error":
        cause_text = str(cause) if cause else "unknown error"
        return f"song requests: error - {cause_text}"
    # Unknown/unexpected state from hub-api -- safest reply is offline, never silence.
    return _STATUS_OFFLINE_REPLY


async def _send_reply(
    text: str,
    *,
    community_id: int,
    platform: str,
    payload: Mapping[str, Any],
    config: Mapping[str, Any],
    http_client: httpx.AsyncClient,
) -> TransportResult:
    """Reply-in-place: resolve the channel, then dispatch via Discord/Twitch.

    Shared by both `enqueue_song_request()`'s subcommand paths (enqueue,
    status check) -- same precedence as `social_quote_action.py`: payload
    channel first, config fallback.
    """
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

    logger.debug(
        "social_music_action.reply_channel_resolved community_id=%s platform=%s channel=%s",
        community_id,
        platform,
        channel,
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
    # Discord's Bot API requires the `Bot` auth scheme, never `Bearer` (that
    # scheme is for OAuth2 user access tokens) -- a valid bot token sent as
    # `Bearer` is rejected with 401 even though the token itself is fine.
    # Matches discord_send_action.py:send_message's own header, the platform's
    # other Discord-reply bundle.
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
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
        logger.warning(
            "social_music_action.discord_send_rejected community_id=%s bot_token_ref=%s "
            "channel=%s status=%s",
            community_id,
            token_ref,
            channel,
            response.status_code,
        )
        raise NonRetryableTransportError(
            f"discord API rejected auth for bot_token_ref={token_ref!r}: "
            f"HTTP {response.status_code}",
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


async def enqueue_song_request(
    envelope: StageEnvelope,
    config: Mapping[str, Any],
    *,
    http_client: httpx.AsyncClient,
) -> TransportResult:
    """Dispatch `!sr`/`!songrequest` action work -- enqueue a song, or `!sr status`.

    Entry point name is pinned by `alembic/versions/0009_music_catalog.py`'s
    `app_catalog` seed row (`"entrypoint": "bundles.social_music_action:
    enqueue_song_request"`) -- kept unchanged (module docstring) even
    though a `music_status_check` payload flag now routes some events to
    `_check_status()` instead of `_enqueue()`.

    Requester identity is read from the SAME already-tokenized fields
    every other bundle uses -- `event.payload["author_id"]` (platform-
    native user id, never raw PII) and `event.actor` (display name) --
    never re-derived here.

    Raises `NonRetryableTransportError` for a config/payload error or an
    unresolvable reply channel; propagates `Retryable`/
    `NonRetryableTransportError` from the outbound chat send unchanged --
    see module docstring for why the enqueue/status-check step itself
    never raises.
    """
    payload = envelope.event.payload

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

    if payload.get(_STATUS_CHECK_KEY):
        logger.debug("social_music_action.dispatch_status_check community_id=%s", community_id)
        text = await _check_status(http_client, community_id=community_id)
    else:
        query = payload.get("music_query")
        if not isinstance(query, str) or not query.strip():
            raise NonRetryableTransportError("music action requires 'music_query'")
        raw_author_id = payload.get("author_id")
        platform_user_id = str(raw_author_id) if raw_author_id is not None else None
        logger.debug("social_music_action.dispatch_enqueue community_id=%s", community_id)
        text = await _enqueue(
            http_client,
            community_id=community_id,
            url_or_query=query.strip(),
            platform=platform,
            platform_user_id=platform_user_id,
            requested_by_display=envelope.event.actor,
        )

    return await _send_reply(
        text,
        community_id=community_id,
        platform=platform,
        payload=payload,
        config=config,
        http_client=http_client,
    )
