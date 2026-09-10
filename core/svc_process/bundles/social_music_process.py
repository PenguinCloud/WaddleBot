"""Social music process bundle -- parses `!sr`/`!songrequest` chat commands.

Normalizes a chat song-request command into a structured `PlatformEvent`
for the action stage (`bundles.social_music_action`), which enqueues the
resolved track into the hub-api Music Station queue
(`hub_api/blueprints/v1/community_music_queue.py`) and replies in-place.

Supports two aliases for the same command:
- `!sr <url or search query>`
- `!songrequest <url or search query>`

ROUTING (mirrors `bundles.community_forums_process`'s gh #298 mechanism):
a successful parse -- but not a usage-hint reply -- stamps
`PROCESS_TARGET_APP_ID_KEY` onto the returned event's payload with
`_MUSIC_APP_ID`. `bot_process.py` delegates `!sr`/`!songrequest` to this
bundle's `transform()` in-process and returns whatever it gets back
unmodified, so this key rides all the way to `core/svc_process/
runner.py`, which enqueues the event onto the music app's `:action` key
instead of the originating bot's -- see `PROCESS_TARGET_APP_ID_KEY`'s
docstring in `flask_core.stream_pipeline` for the full mechanism.

Requester identity: the requesting viewer's platform-native user id
(`event.payload["author_id"]`) and display name (`event.actor`) are
already tokenized, opaque platform identifiers set upstream by ingest --
never raw PII -- and this bundle never strips or overwrites them; they
ride through to the action stage untouched via `**event.payload`, same
as `channel_id`/`channel_name`.

Feature-gated (default OFF) via `flask_core.feature_flags.feature_enabled`
-- `waddles.social.music` -- following `services.moderation_gate`'s own
direct-call pattern (this command family predates any Feature-contract
registry entry for bot/social command bundles; `libs/core_platform_module/
features.py` covers a different, unrelated set of 14 Core/Platform
features and is not extended here). Flag OFF (or a PostHog/license-server
outage, which `feature_enabled` itself degrades to `default=False` for)
means `!sr`/`!songrequest` behaves like an unrecognized command: no
reply, same as any other disabled feature.
"""

from __future__ import annotations

import dataclasses
import re

from flask_core import PROCESS_TARGET_APP_ID_KEY, PlatformEvent, get_bundle_context
from flask_core.feature_flags import feature_enabled

#: Matches either alias, valid or not -- used to tell "this is a song
#: request command with a missing/blank query" (usage hint) apart from
#: "not a song request at all" (`None`, no reply).
_SR_PREFIX_RE = re.compile(r"^!(sr|songrequest)\b", re.IGNORECASE)

_SR_USAGE = "Usage: !sr <url or search query>  ·  !songrequest <url or search query>"

#: `app_catalog.app_id` this bundle's action stage is registered under
#: (alembic 0009_music_catalog). A successful parse routes to THIS app's
#: `:action` key instead of the originating bot's -- see module docstring.
_MUSIC_APP_ID = "waddles.social.music.default"

#: PostHog flag key, `waddles.<module>.<feature>` convention (see
#: `waddles.community.forums`/`waddles.social.quote`/`waddles.analytics.*`
#: elsewhere in this repo). Default OFF until validated for the demo.
_FEATURE_FLAG = "waddles.social.music"


def _usage_reply(event: PlatformEvent) -> PlatformEvent:
    """Build the `!sr`/`!songrequest` usage-hint reply, preserving every other payload field."""
    return dataclasses.replace(event, payload={**event.payload, "text": _SR_USAGE})


def _community_id(community: str | None) -> int | None:
    """Best-effort `int(community)` for the flag check; `None`/unparseable -> `None`."""
    if community is None:
        return None
    try:
        return int(community)
    except ValueError:
        return None


async def transform(event: PlatformEvent) -> PlatformEvent | None:
    """Parse `!sr`/`!songrequest` from chat text; return `None` for non-matching messages.

    A message starting with `!sr`/`!songrequest` but with a missing/blank
    query gets a usage-hint reply rather than silently doing nothing. Flag
    OFF (or the flag/license server is unreachable) also returns `None` --
    see module docstring.

    Raises `ValueError` on a malformed event -- the process runner catches
    this per-event so one bad event never kills the poll loop.
    """
    text = event.payload.get("text")
    if not isinstance(text, str):
        raise ValueError("event payload missing required 'text' string field")

    text = text.strip()
    if not text or not _SR_PREFIX_RE.match(text):
        return None  # not a song request command, skip

    ctx = get_bundle_context()
    enabled = await feature_enabled(
        _FEATURE_FLAG, tenant=ctx.tenant, community=_community_id(ctx.community), default=True
    )
    if not enabled:
        return None  # feature disabled -- behaves like an unrecognized command

    parts = text.split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""
    if not query:
        return _usage_reply(event)

    return dataclasses.replace(
        event,
        payload={
            **event.payload,
            "text": query,
            "music_query": query,
            PROCESS_TARGET_APP_ID_KEY: _MUSIC_APP_ID,
        },
    )
