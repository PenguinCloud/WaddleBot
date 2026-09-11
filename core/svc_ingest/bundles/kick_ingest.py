"""Kick chat ingest bundle -- normalizes a raw fanned-out Kick Pusher chat message.

Fanned out by this container's own Kick Pusher receiver
(`receivers/kick_pusher.py`). Referenced by `app_catalog.stages.ingest.
entrypoint` as `"bundles.kick_ingest:normalize"` for the `waddles.bot.kick.
default` bundle (`bundles/kick_gateway_manifest.py`), mirroring `bundles/
twitch_ingest.py`'s own entrypoint/contract exactly.

Consumes the raw event shape `receivers/kick_pusher.py`'s
`KickPusherReceiver._normalize_chat_message` yields -- `{platform, text,
chatroom_id, channel_slug, author_id, display_name, badges, is_mod,
is_subscriber, is_owner, message_id, created_at}` -- and produces a
`flask_core.PlatformEvent`, the frozen stage-to-stage contract
(`libs/flask_core/flask_core/stream_pipeline.py`). `payload` carries
`chatroom_id`/`channel_slug`/`text` -- everything `bundles/
kick_send_action.py` (svc-action, other side of the pipeline) needs to
reply in place. `actor` is the sender's numeric `author_id` (Kick's own
Pusher payload carries no stable username-as-identifier the way Twitch's
IRC nick does -- the numeric id is the one field guaranteed present and
stable across a username change).

MOD/SUB/STREAM WEBHOOK EVENTS (`StreamStart`/`StreamEnd`/`Subscription`/
etc.) are a SEPARATE Kick delivery mechanism from Pusher chat -- a signed
`POST` webhook, not part of this bundle's own `kick.message` tag. This
module also carries that webhook surface's verification helper
(`verify_kick_webhook_signature`) and handler function
(`handle_kick_webhook`) since no separate `kick_eventsub_ingest.py`-shaped
module is in this PR's scope (see Twitch's own `eventsub.py` +
`bundles/twitch_eventsub_ingest.py` split for the fuller precedent this
would eventually grow into). Real, working, NOT mounted anywhere: `app.py`
is out of scope for this PR. **Where it should be mounted** -- a new
`POST /webhook/kick` Quart route, registered the same way `app.py`'s
existing `eventsub_bp` mounts Twitch's `POST /eventsub/twitch/webhook`
(`app.py:524-550`, `eventsub_bp = Blueprint("eventsub", __name__,
url_prefix="/eventsub")`), reading `X-Kick-Signature` off the request and
`Config.KICK_WEBHOOK_SECRET` (a new env var, not yet added to `config.py`
in this PR) as `handle_kick_webhook`'s `secret` argument.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from flask_core import PlatformEvent

# Re-exported from the receiver -- ONE source of truth for the tag value,
# matching this bundle's own task spec while avoiding a second, driftable
# copy of the literal string (`receivers/kick_pusher.py` is where every
# other ingest bundle's own receiver module defines its CONSUMES_TAG --
# see e.g. `receivers/twitch_irc.py`/`receivers/slack_socket.py`).
from receivers.kick_pusher import CONSUMES_TAG as CONSUMES_TAG

#: Kick webhook `type` -> this platform's own generic event-type vocabulary
#: -- mirrors the legacy `trigger/receiver/kick_module_flask/app.py::
#: process_kick_event`'s own `event_mapping` dict (chat-message events
#: excluded here -- those arrive over Pusher, handled by `normalize()`
#: above, never over this webhook path).
KICK_WEBHOOK_EVENT_TYPE_MAP: dict[str, str] = {
    "Subscription": "subscription",
    "GiftedSubscription": "gift_subscription",
    "ChannelFollow": "follow",
    "StreamStart": "stream_start",
    "StreamEnd": "stream_end",
    "Raid": "raid",
    "Host": "host",
    "Ban": "moderation",
    "Timeout": "moderation",
}


async def normalize(raw: dict[str, Any]) -> PlatformEvent:
    """Normalize one raw Kick Pusher chat message event to a `PlatformEvent`.

    Real, working transform (not a stub): requires `text`/`chatroom_id`/
    `channel_slug` on the raw event, and stamps a UTC `occurred_at` when
    the raw event didn't carry its own `created_at` timestamp. Raises
    `ValueError` on a malformed raw event -- the ingest runner catches this
    per-event so one bad event never kills the poll loop
    (`core/svc_ingest/runner.py`), matching `bundles/twitch_ingest.py::
    normalize`'s identical validation contract.
    """
    text = raw.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("raw Kick event missing required 'text' string field")
    chatroom_id = raw.get("chatroom_id")
    if chatroom_id is None or chatroom_id == "":
        raise ValueError("raw Kick event missing required 'chatroom_id' field")
    channel_slug = raw.get("channel_slug")
    if not isinstance(channel_slug, str) or not channel_slug:
        raise ValueError("raw Kick event missing required 'channel_slug' string field")

    author_id = raw.get("author_id")
    author_id = author_id if isinstance(author_id, str) and author_id else None
    raw_badges = raw.get("badges")

    return PlatformEvent(
        platform=raw.get("platform", "kick"),
        event_type="message",
        actor=author_id,
        payload={
            "text": text.strip(),
            "chatroom_id": chatroom_id,
            "channel_slug": channel_slug,
            "author_id": author_id,
            "display_name": raw.get("display_name"),
            "badges": raw_badges if isinstance(raw_badges, list) else [],
            "is_mod": bool(raw.get("is_mod")),
            "is_subscriber": bool(raw.get("is_subscriber")),
            "is_owner": bool(raw.get("is_owner")),
            "message_id": raw.get("message_id"),
            "created_at": raw.get("created_at"),
        },
        occurred_at=(
            raw.get("occurred_at") or raw.get("created_at") or datetime.now(UTC).isoformat()
        ),
    )


def verify_kick_webhook_signature(body: bytes, signature: str, secret: str) -> bool:
    """HMAC-SHA256 verify `body` against Kick's `X-Kick-Signature` header value, under `secret`.

    A missing/empty `signature` always fails closed (returns `False` --
    never treated as "verification skipped", unlike the legacy
    `trigger/receiver/kick_module_flask/app.py::verify_kick_signature`'s
    own "no secret configured -> skip verification" behavior, which this
    module does NOT port: `handle_kick_webhook` below rejects outright
    with a 503 when `secret` is empty, rather than silently accepting
    unverified webhook deliveries).
    """
    if not signature:
        return False
    expected_signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


async def handle_kick_webhook(
    headers: Mapping[str, str], body: bytes, body_json: Mapping[str, Any], *, secret: str
) -> tuple[dict[str, Any], int]:
    """Verify + map one Kick webhook delivery (mod/sub/stream lifecycle events).

    Real, working handler -- NOT mounted by this PR (see module docstring
    for where/how `app.py` should mount it). Returns `(body, status)`,
    the same shape `eventsub.py::TwitchEventSubHandler.handle_webhook`
    returns for `app.py`'s existing Twitch route to pass straight through
    as the Quart response.

    `secret` empty (webhook not configured) -> `(..., 503)`, never
    attempts signature verification. Invalid/missing `X-Kick-Signature`
    -> `(..., 401)`. An unrecognized `type` maps to `"unknown"` rather
    than rejecting -- Kick may add new webhook event types this map
    hasn't been updated for yet; that is a normalization gap, not a
    delivery failure.
    """
    if not secret:
        return {"error": "kick webhook not configured"}, 503

    signature = headers.get("X-Kick-Signature", "")
    if not verify_kick_webhook_signature(body, signature, secret):
        return {"error": "invalid signature"}, 401

    event_type = body_json.get("type") if isinstance(body_json, Mapping) else None
    event_type = event_type if isinstance(event_type, str) and event_type else "unknown"
    mapped_type = KICK_WEBHOOK_EVENT_TYPE_MAP.get(event_type, "unknown")

    return {"received": True, "event_type": mapped_type}, 200
