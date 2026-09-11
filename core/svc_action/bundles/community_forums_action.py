"""Community forums action bundle -- persists forum posts/replies and relays.

Handles creation of forum posts and replies with best-effort relay to
bridged channels. Reads structured forum commands from process stage,
writes to hub_forum_posts/hub_forum_replies tables, and notifies relay
service for cross-platform propagation.

DB access uses `flask_core.get_bundle_dal()` per docs/APP_BUNDLE_AUTHORING.md
Accessing the database / shared state -- the runner binds the real,
env-sourced DAL at startup via `set_bundle_dal()` (`core/svc_action/app.py`),
same as every other action bundle (`community_announcements_action.py`,
`social_quote_action.py`).

`hub_channels`/`hub_forum_posts`/`hub_forum_replies` are never bound
anywhere else on this service's `dal` (svc-action's own startup only
binds `tenants`/`communities`/`app_catalog`/`action_dispatch_log`), so
this bundle binds its own minimal stubs (`_ensure_forum_tables`,
idempotent, `migrate=False` -- schema owned by `config/postgres/
migrations/057_community_interaction.sql`), same convention
`twitch_shoutout_action.py::_ensure_shoutout_tables` establishes.
`select_async` runs `query.select()`/`query.db.commit()` directly
(`flask_core/database.py`) -- it requires a pydal `Set`
(`dal.dal(query)`), not a bare `Query` (gh #298); a bare `Query` has no
`.select()`/`.db` in this pydal version.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from flask_core import StageEnvelope, get_bundle_dal
from waddle_transports import NonRetryableTransportError, TransportResult

logger = logging.getLogger(__name__)


def _ensure_forum_tables(dal: Any) -> None:
    """Idempotently bind `hub_channels`/`hub_forum_posts`/`hub_forum_replies`.

    Only the columns this bundle actually touches -- mirrors
    `twitch_shoutout_action.py::_ensure_shoutout_tables`'s own
    "minimal stub, no DDL" convention, `migrate=False` throughout.
    Must run on a `dal` that already has `communities` defined
    (svc-action's own `app.py` startup binds it before
    `set_bundle_dal()`).
    """
    if "hub_channels" not in dal.tables:
        dal.define_table(
            "hub_channels",
            dal.Field("community_id", "reference communities", notnull=True),
            # Plain integer, not "reference community_server_channels" --
            # that table is never bound here, only this column's presence
            # (relay target) is ever read.
            dal.Field("community_server_channel_id", "integer"),
            migrate=False,
        )
    if "hub_forum_posts" not in dal.tables:
        dal.define_table(
            "hub_forum_posts",
            dal.Field("hub_channel_id", "integer"),
            dal.Field("community_id", "reference communities", notnull=True),
            dal.Field("title", "string", notnull=True),
            dal.Field("body", "text"),
            dal.Field("tags", "json", default=[]),
            dal.Field("author_hub_user_id", "integer"),
            dal.Field("author_platform", "string"),
            dal.Field("author_username", "string"),
            dal.Field("author_avatar_url", "string"),
            dal.Field("is_locked", "boolean", default=False),
            dal.Field("reply_count", "integer", default=0),
            dal.Field("last_reply_at", "datetime"),
            dal.Field("created_at", "datetime", default=lambda: datetime.now(UTC)),
            dal.Field("updated_at", "datetime", default=lambda: datetime.now(UTC)),
            migrate=False,
        )
    if "hub_forum_replies" not in dal.tables:
        dal.define_table(
            "hub_forum_replies",
            dal.Field("post_id", "reference hub_forum_posts", notnull=True),
            dal.Field("author_hub_user_id", "integer"),
            dal.Field("author_platform", "string"),
            dal.Field("author_username", "string"),
            dal.Field("author_avatar_url", "string"),
            dal.Field("content", "text", notnull=True),
            dal.Field("created_at", "datetime", default=lambda: datetime.now(UTC)),
            migrate=False,
        )


def _resolve_channel_id(config: Mapping[str, Any]) -> int | None:
    """Resolve the target `hub_channel_id` from the bundle's per-activation config.

    `channel_id` (migration 091's `required_config`) is supplied when a
    community activates the forums app (migration 069's 3-tier install ->
    tenant -> community-activation precedence) -- never from `event.
    payload`, which a `!forum create` typed in chat never populates and
    which is untrusted platform data besides. A community that has
    activated forums without configuring a channel gets `None` here: the
    post still persists (`hub_channel_id` is nullable), just without a
    relay target.
    """
    raw = config.get("channel_id")
    if raw is None:
        return None
    if not isinstance(raw, (str, int)) or isinstance(raw, bool):
        raise NonRetryableTransportError("channel_id config must be an integer")
    try:
        return int(raw)
    except ValueError:
        raise NonRetryableTransportError("channel_id config must be an integer") from None


async def create_forum_post(
    envelope: StageEnvelope,
    config: Mapping[str, Any],
    *,
    http_client: httpx.AsyncClient,  # noqa: ARG001 -- follows action entrypoint contract
) -> TransportResult:
    """Create a forum post and relay it to bridged channels.

    Expects envelope.event.payload to contain:
      - forum_action: "create"
      - forum_title: post title
      - forum_body: post body
      - author_id: (optional) hub user id

    The target `hub_channel_id` comes from the bundle's own `config`
    (`_resolve_channel_id`), not the payload -- see that helper's
    docstring.
    """
    payload = envelope.event.payload
    title = payload.get("forum_title")
    body = payload.get("forum_body")

    if not isinstance(title, str) or not title:
        raise NonRetryableTransportError("forum post requires 'forum_title'")
    if not isinstance(body, str):
        raise NonRetryableTransportError("forum post requires 'forum_body'")

    channel_id_int = _resolve_channel_id(config)

    dal = get_bundle_dal()
    _ensure_forum_tables(dal)
    try:
        # Fetch the channel to verify it exists and get relay info -- only
        # when a channel was actually configured for this activation.
        channel = None
        if channel_id_int is not None:
            channel_query = dal.hub_channels.id == channel_id_int
            # select_async requires a pydal Set (dal.dal(query)), not a
            # bare Query -- see module docstring.
            channels = await dal.select_async(dal.dal(channel_query))
            channel = channels[0] if channels else None
            if not channel:
                raise NonRetryableTransportError(f"channel {channel_id_int} not found")

        # Create the forum post
        post_id = await dal.insert_async(
            dal.hub_forum_posts,
            hub_channel_id=channel_id_int,
            community_id=envelope.community,
            title=title,
            body=body,
            tags=payload.get("tags") or [],
            author_hub_user_id=payload.get("author_id"),
            author_platform="hub",
            author_username=payload.get("author") or "anonymous",
            author_avatar_url=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Relay to bridged channels if configured -- no relay target when
        # this activation has no channel configured (channel is None).
        # FLAG: relay_message async helper not yet implemented -- logged so
        # the gap is visible, never raised (best-effort, don't fail dispatch).
        if channel is not None and channel.community_server_channel_id:
            logger.debug(
                "community_forums_action.relay_not_implemented "
                "community_server_channel_id=%s",
                channel.community_server_channel_id,
            )

        return TransportResult(
            transport="bundle",
            detail=f"forum post created, post_id={post_id}, channel={channel_id_int}",
            http_status=201,
        )
    except Exception as exc:
        if isinstance(exc, NonRetryableTransportError):
            raise
        raise NonRetryableTransportError(f"forum post creation failed: {exc}") from exc


async def create_forum_reply(
    envelope: StageEnvelope,
    config: Mapping[str, Any],
    *,
    http_client: httpx.AsyncClient,  # noqa: ARG001 -- follows action entrypoint contract
) -> TransportResult:
    """Create a forum reply and relay it to bridged channels.

    Expects envelope.event.payload to contain:
      - forum_action: "reply"
      - forum_post_id: id of the post being replied to
      - forum_content: reply text
      - author_id: (optional) hub user id
    """
    payload = envelope.event.payload
    post_id = payload.get("forum_post_id")
    content = payload.get("forum_content")

    if not isinstance(post_id, int) or post_id < 1:
        raise NonRetryableTransportError("forum reply requires 'forum_post_id' (integer > 0)")
    if not isinstance(content, str) or not content:
        raise NonRetryableTransportError("forum reply requires 'forum_content'")

    dal = get_bundle_dal()
    _ensure_forum_tables(dal)
    try:
        # Verify post exists and check if locked
        post_query = dal.hub_forum_posts.id == post_id
        # select_async requires a pydal Set (dal.dal(query)), not a bare
        # Query -- see module docstring.
        posts = await dal.select_async(dal.dal(post_query))
        post = posts[0] if posts else None
        if not post:
            raise NonRetryableTransportError(f"post {post_id} not found")
        if post.is_locked:
            raise NonRetryableTransportError(f"post {post_id} is locked")

        # Create the reply
        reply_id = await dal.insert_async(
            dal.hub_forum_replies,
            post_id=post_id,
            author_hub_user_id=payload.get("author_id"),
            author_platform="hub",
            author_username=payload.get("author") or "anonymous",
            author_avatar_url=None,
            content=content,
            created_at=datetime.now(UTC),
        )

        # Update post's reply counter and last_reply_at
        update_query = dal.hub_forum_posts.id == post_id
        await dal.update_async(
            update_query,
            reply_count=post.reply_count + 1,
            last_reply_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Relay to bridged channels if configured
        channel_query = dal.hub_channels.id == post.hub_channel_id
        # select_async requires a pydal Set (dal.dal(query)), not a bare
        # Query -- see module docstring.
        channels = await dal.select_async(dal.dal(channel_query))
        channel = channels[0] if channels else None
        # FLAG: relay_message async helper not yet implemented -- logged so
        # the gap is visible, never raised (best-effort, don't fail dispatch).
        if channel and channel.community_server_channel_id:
            logger.debug(
                "community_forums_action.relay_not_implemented "
                "community_server_channel_id=%s",
                channel.community_server_channel_id,
            )

        return TransportResult(
            transport="bundle",
            detail=f"forum reply created, reply_id={reply_id}, post_id={post_id}",
            http_status=201,
        )
    except Exception as exc:
        if isinstance(exc, NonRetryableTransportError):
            raise
        raise NonRetryableTransportError(f"forum reply creation failed: {exc}") from exc
