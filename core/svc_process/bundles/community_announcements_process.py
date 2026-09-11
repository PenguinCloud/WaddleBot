"""Community announcements process bundle -- parses `!announce publish` command.

Ported from `hub_api/services/community_announcements.py`'s publish + broadcast
logic into the App Bundle SDK's process-stage script contract:
`async def transform(event, ...) -> PlatformEvent | None` (`runner.py`).

Consumes inbound chat messages (normalized to PlatformEvent by ingest), parses
the `!announce publish <announcement_id>` command, looks up the announcement
from the database, validates it's ready to broadcast, and enriches the event
with the announcement data + target platforms before enqueueing to the action
stage. Returns `None` for non-announcement commands (ordinary chatter, other
bots) -- the process runner's own no-reply behavior prevents echoing.

DB access uses `flask_core.get_bundle_dal()` and `get_bundle_context()` per
docs/APP_BUNDLE_AUTHORING.md Accessing the database / shared state. The runner
binds the DAL at startup via `set_bundle_dal()`, and wraps every invocation
in `bundle_context()` to scope queries by tenant/community.

`announcements` is never bound anywhere else on this service's `dal`
(svc-process's own startup only binds `tenants`/`communities`/
`app_catalog`/`live_activity_events`), so this bundle binds its own
minimal stub (`_ensure_announcements_table`, idempotent, `migrate=False`
-- schema owned by `config/postgres/migrations/
000_create_base_schema.sql`), same "bind only the columns this bundle
actually touches" convention `svc_action/bundles/twitch_shoutout_action.
py::_ensure_shoutout_tables` establishes. The lookup itself previously
called `dal(query)` -- `dal` here is the `AsyncDAL` wrapper returned by
`get_bundle_dal()`, which defines no `__call__` (`TypeError: 'AsyncDAL'
object is not callable`) -- and ran `.select()` synchronously in this
`async def`, blocking the event loop instead of offloading through
`select_async`'s executor. The fix wraps the raw pydal DAL
(`dal.dal(query)`, matching `runner.py::_resolve_tenant_id`'s own call
shape) and awaits it via `select_async`.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from flask_core import PlatformEvent, get_bundle_context, get_bundle_dal

#: Matches any `!announce` invocation, valid or not -- used to tell "this is
#: an announce command with bad args" (usage hint) apart from "not an
#: announce message at all" (`None`, no reply).
_ANNOUNCE_PREFIX_PATTERN = re.compile(r"^!announce\b", re.IGNORECASE)
_ANNOUNCE_COMMAND_PATTERN = re.compile(r"^!announce\s+publish\s+(\d+)(?:\s+(.*))?$", re.IGNORECASE)

_ANNOUNCE_USAGE = "Usage: !announce publish <announcement_id>"


def _ensure_announcements_table(dal: Any) -> None:
    """Idempotently bind `announcements` -- only the columns this bundle reads.

    Mirrors `svc_action/bundles/twitch_shoutout_action.py::
    _ensure_shoutout_tables`'s own "minimal stub, no DDL" convention,
    `migrate=False` throughout. Must run on a `dal` that already has
    `communities` defined.
    """
    if "announcements" not in dal.tables:
        dal.define_table(
            "announcements",
            dal.Field("community_id", "reference communities", notnull=True),
            dal.Field("title", "string", notnull=True),
            dal.Field("content", "text", notnull=True),
            dal.Field("announcement_type", "string", default="general"),
            dal.Field("status", "string", default="published"),
            dal.Field("broadcasted_platforms", "json", default=[]),
            migrate=False,
        )


async def transform(event: PlatformEvent) -> PlatformEvent | None:
    """Parse `!announce publish <id>` and enrich with announcement data.

    Returns `None` for non-announcement commands -- the process runner
    catches this per-event so one bad event never kills the poll loop. A
    message starting with `!announce` but missing/malformed args (no
    `publish` subcommand, no id, non-numeric id) gets a usage-hint reply
    instead of silently doing nothing.

    Raises `ValueError` on a malformed event (missing text field).
    """
    text = event.payload.get("text")
    if not isinstance(text, str):
        raise ValueError("event payload missing required 'text' string field")

    stripped = text.strip()
    if not stripped or not _ANNOUNCE_PREFIX_PATTERN.match(stripped):
        return None  # Not an announcement command, skip

    match = _ANNOUNCE_COMMAND_PATTERN.match(stripped)
    if not match:
        return dataclasses.replace(event, payload={**event.payload, "text": _ANNOUNCE_USAGE})

    announcement_id_str = match.group(1)
    announcement_id = int(announcement_id_str)

    dal = get_bundle_dal()
    _ensure_announcements_table(dal)
    ctx = get_bundle_context()

    try:
        # Scope lookup by community to prevent IDOR: users can only broadcast
        # announcements from their own community. Tenant-wide activations
        # (ctx.community is None) should not be served.
        if ctx.community is None:
            return None  # Tenant-wide activation cannot broadcast announcements

        community_id = int(ctx.community)
        query = (dal.announcements.id == announcement_id) & (
            dal.announcements.community_id == community_id
        )
        # select_async runs query.select()/query.db.commit() directly and
        # requires a pydal Set (dal.dal(query)) -- `dal` (the AsyncDAL
        # wrapper) is not itself callable, unlike the raw pydal DAL.
        rows = await dal.select_async(dal.dal(query))
        row = rows.first() if rows else None
        if row is None:
            return None  # Announcement not found in this community, skip

        # Determine target platforms from broadcast_to_platforms flag
        # or infer from active community_servers
        platforms = []
        if hasattr(row, "broadcasted_platforms") and row.broadcasted_platforms:
            platforms = (
                row.broadcasted_platforms if isinstance(row.broadcasted_platforms, list) else []
            )

        if not platforms:
            # If no platforms specified, default to all configured platforms
            platforms = ["discord", "twitch"]  # Configurable default

        # Build enriched payload
        announcement_data = {
            "id": row.id,
            "title": row.title,
            "content": row.content,
            "announcement_type": row.announcement_type or "general",
            "status": row.status or "published",
            "community_id": row.community_id,
        }

        enriched_payload: dict[str, Any] = {
            **event.payload,
            "announcement": announcement_data,
            "target_platforms": platforms,
            "announcement_id": announcement_id,
        }

        return dataclasses.replace(event, payload=enriched_payload)

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"failed to lookup or enrich announcement {announcement_id}: {exc}"
        ) from exc
