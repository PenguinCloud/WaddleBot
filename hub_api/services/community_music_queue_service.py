"""Music Station queue service -- per-community intermingled queue, policy, moderation.

Backs `blueprints/v1/community_music_queue.py`. New-feature service, not a
Node port: tables are owned outright by `config/postgres/migrations/
072_music_station.sql`, bound via `services.schema.bind_music_tables()`
(called once at startup from `app.py::_bind_reference_tables()`).

Every function takes `async_dal`/`dal` and an already-authorized caller
(`blueprints/v1/community_music_queue.py` calls
`services.community_authz.authorize_community()` before any of these run
-- this module never re-derives authorization, only tenant/community
scoping of the query itself, per security.md's "queries scoped to the
token's tenant" rule). Tracks are resolved via the provider contract in
`services/music_providers/__init__.py::resolve()` and deduplicated into
`music_tracks` by `(tenant_id, provider, external_id)`.

Category restriction ("song requests must come from the music category")
checks the community's LIVE Twitch category via the same `coordination`
JOIN `community_servers` query `services/stream_service.py` already uses
(`services.schema.bind_streaming_tables()` binds both tables, called
lazily here exactly like `blueprints/v1/music.py` already does, since
this module has no other dependency on that group's own tables).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from services.errors import bad_request, forbidden, not_found, unprocessable
from services.music_providers import ProviderUnavailable, Track, TrackNotFound, resolve
from services.schema import bind_streaming_tables

_LIVE_PLATFORM = "twitch"
_MUSIC_CATEGORY_NAMES = frozenset({"music"})


# ---------------------------------------------------------------------------
# Wire DTOs -- camelCase field names deliberately break PEP8 snake_case
# convention (see hub_api/PORTING.md "DTO casing"); this is a new API
# surface, not a Node port, but every other v1 blueprint in this repo pins
# its JSON contract in camelCase, so Music Station matches that convention
# for consistency rather than inventing a second casing style.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class TrackDTO:
    """Wire shape of a resolved `Track` -- mirrors `services.music_providers.track.Track`."""

    provider: str
    externalId: str
    title: str
    artist: str
    durationMs: int
    artworkUrl: str | None
    url: str


@dataclass(slots=True, frozen=True)
class QueueItemDTO:
    """One `music_station_queue` row, with its resolved track embedded.

    `etaSeconds`: seconds until this item is expected to start playing --
    the sum of `track.durationMs` for every currently-`queued` item ahead
    of this one (by `position`), plus the remaining playtime of whatever's
    currently `playing`, if anything. `None` when not computed for this
    call site (only `enqueue_request()` populates it today -- see
    `_compute_eta_seconds()`); `0` means "next up".
    """

    id: int
    communityId: int
    track: TrackDTO
    position: int
    status: str
    source: str
    playlistId: str | None
    requestedBy: int | None
    addedAt: str | None
    startedAt: str | None
    endedAt: str | None
    etaSeconds: int | None


@dataclass(slots=True, frozen=True)
class PolicyDTO:
    """One community's Music Station policy."""

    communityId: int
    songRequestsAllowed: bool
    requestsCategoryRestricted: bool
    updatedBy: int | None
    updatedAt: str | None


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _track_dto(row: Any) -> TrackDTO:
    return TrackDTO(
        provider=row.provider,
        externalId=row.external_id,
        title=row.title,
        artist=row.artist,
        durationMs=row.duration_ms,
        artworkUrl=row.artwork_url,
        url=row.url,
    )


async def _get_track_row(async_dal: Any, dal: Any, *, track_id: int) -> Any:
    rows = await async_dal.select_async(dal(dal.music_tracks.id == track_id))
    if not rows:
        raise not_found(f"Track {track_id} not found")
    return rows.first()


def _queue_item_dto(
    queue_row: Any, track_row: Any, *, eta_seconds: int | None = None
) -> QueueItemDTO:
    return QueueItemDTO(
        id=queue_row.id,
        communityId=queue_row.community_id,
        track=_track_dto(track_row),
        position=queue_row.position,
        status=queue_row.status,
        source=queue_row.source,
        playlistId=queue_row.playlist_id,
        requestedBy=queue_row.requested_by,
        addedAt=_iso(queue_row.added_at),
        startedAt=_iso(queue_row.started_at),
        endedAt=_iso(queue_row.ended_at),
        etaSeconds=eta_seconds,
    )


def _policy_dto(row: Any, *, community_id: int) -> PolicyDTO:
    return PolicyDTO(
        communityId=community_id,
        songRequestsAllowed=bool(row.song_requests_allowed),
        requestsCategoryRestricted=bool(row.requests_category_restricted),
        updatedBy=row.updated_by,
        updatedAt=_iso(row.updated_at),
    )


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


async def get_policy(async_dal: Any, dal: Any, *, tenant_id: int, community_id: int) -> PolicyDTO:
    """Return the community's policy, creating the default (allowed, unrestricted) row if missing.

    The default row is inserted lazily on first read.
    """
    rows = await async_dal.select_async(dal(dal.music_policy.community_id == community_id))
    if rows:
        return _policy_dto(rows.first(), community_id=community_id)

    now = datetime.now(UTC)
    new_id = await async_dal.insert_async(
        dal.music_policy,
        tenant_id=tenant_id,
        community_id=community_id,
        song_requests_allowed=True,
        requests_category_restricted=False,
        updated_by=None,
        updated_at=now,
    )
    rows = await async_dal.select_async(dal(dal.music_policy.id == int(new_id)))
    return _policy_dto(rows.first(), community_id=community_id)


async def set_policy(
    async_dal: Any,
    dal: Any,
    *,
    tenant_id: int,
    community_id: int,
    song_requests_allowed: bool | None,
    requests_category_restricted: bool | None,
    updated_by: int | None,
) -> PolicyDTO:
    """Upsert the community's policy -- only the provided fields change."""
    if song_requests_allowed is None and requests_category_restricted is None:
        raise bad_request("No policy fields to update")

    existing = await async_dal.select_async(dal(dal.music_policy.community_id == community_id))
    now = datetime.now(UTC)

    if not existing:
        default_requests_allowed = (
            song_requests_allowed if song_requests_allowed is not None else True
        )
        default_category_restricted = (
            requests_category_restricted if requests_category_restricted is not None else False
        )
        new_id = await async_dal.insert_async(
            dal.music_policy,
            tenant_id=tenant_id,
            community_id=community_id,
            song_requests_allowed=default_requests_allowed,
            requests_category_restricted=default_category_restricted,
            updated_by=updated_by,
            updated_at=now,
        )
        rows = await async_dal.select_async(dal(dal.music_policy.id == int(new_id)))
        return _policy_dto(rows.first(), community_id=community_id)

    fields: dict[str, Any] = {"updated_by": updated_by, "updated_at": now}
    if song_requests_allowed is not None:
        fields["song_requests_allowed"] = song_requests_allowed
    if requests_category_restricted is not None:
        fields["requests_category_restricted"] = requests_category_restricted

    query = dal.music_policy.community_id == community_id
    await async_dal.update_async(query, **fields)
    rows = await async_dal.select_async(dal(query))
    return _policy_dto(rows.first(), community_id=community_id)


# ---------------------------------------------------------------------------
# Category restriction
# ---------------------------------------------------------------------------


async def _is_live_music_category(async_dal: Any, dal: Any, *, community_id: int) -> bool:
    """True iff the community is live on Twitch under a "Music" category right now.

    Read-only reuse of `services/stream_service.py`'s own `coordination`
    JOIN `community_servers` query shape -- see this module's own
    docstring for why `bind_streaming_tables()` is called lazily here.
    """
    bind_streaming_tables(dal)
    query = (
        (dal.community_servers.community_id == community_id)
        & (dal.community_servers.platform == dal.coordination.platform)
        & (dal.community_servers.platform_server_id == dal.coordination.server_id)
        & (dal.coordination.platform == _LIVE_PLATFORM)
        & (dal.coordination.is_live == True)  # noqa: E712 - pydal Field comparison
    )
    rows = await async_dal.select_async(dal(query), dal.coordination.ALL)
    for row in rows:
        game = (row.game_name or "").strip().lower()
        if game in _MUSIC_CATEGORY_NAMES:
            return True
    return False


async def _log_moderation(
    async_dal: Any,
    dal: Any,
    *,
    tenant_id: int,
    community_id: int,
    actor_user_id: int | None,
    action: str,
    target_queue_id: int | None = None,
    target_playlist_id: str | None = None,
    reason: str | None = None,
) -> None:
    await async_dal.insert_async(
        dal.music_moderation_log,
        tenant_id=tenant_id,
        community_id=community_id,
        actor_user_id=actor_user_id,
        action=action,
        target_queue_id=target_queue_id,
        target_playlist_id=target_playlist_id,
        reason=reason,
        created_at=datetime.now(UTC),
    )


async def _enforce_request_policy(
    async_dal: Any,
    dal: Any,
    *,
    tenant_id: int,
    community_id: int,
    actor_user_id: int | None,
    is_admin_override: bool,
) -> None:
    """Raise unless this specific request is allowed to enqueue right now.

    `is_admin_override=True` (caller already proved community-admin/mod
    scope in the blueprint) bypasses the category restriction only --
    `song_requests_allowed=False` is a hard stop for everyone, override
    included, since that policy switch means the community turned Music
    Station requests off entirely, not "off except for staff".
    """
    policy = await get_policy(async_dal, dal, tenant_id=tenant_id, community_id=community_id)
    if not policy.songRequestsAllowed:
        raise forbidden("Song requests are disabled for this community")

    if not policy.requestsCategoryRestricted:
        return

    live_music = await _is_live_music_category(async_dal, dal, community_id=community_id)
    if live_music:
        return

    if is_admin_override:
        await _log_moderation(
            async_dal,
            dal,
            tenant_id=tenant_id,
            community_id=community_id,
            actor_user_id=actor_user_id,
            action="category_override",
            reason="Category restriction overridden by community admin/moderator",
        )
        return

    raise unprocessable("Song requests are restricted to the live Music category right now")


# ---------------------------------------------------------------------------
# Track resolution + dedup
# ---------------------------------------------------------------------------


async def _resolve_track(url_or_query: str, provider: str | None) -> Track:
    """Resolve via `services.music_providers.resolve()` -- the shared, safe provider contract.

    `resolve()` auto-detects the provider from the URL host when possible
    (`youtube.com`/`youtu.be` -> youtube, `open.spotify.com` -> spotify);
    `provider` is only needed as a fallback for bare search text. Real
    network calls throughout (`services/music_providers/youtube.py`/
    `spotify.py`) -- `ProviderUnavailable`/`TrackNotFound` are the only
    non-`Track` outcomes, both converted to a clear 422 here, never a
    silent fake track.
    """
    try:
        return await resolve(url_or_query, provider)
    except ProviderUnavailable as exc:
        raise unprocessable(f"{exc.provider} provider is not available right now") from exc
    except TrackNotFound as exc:
        raise unprocessable(f"No track found for {exc.query!r}") from exc


async def _get_or_create_track_id(async_dal: Any, dal: Any, *, tenant_id: int, track: Track) -> int:
    query = (
        (dal.music_tracks.tenant_id == tenant_id)
        & (dal.music_tracks.provider == track.provider)
        & (dal.music_tracks.external_id == track.external_id)
    )
    rows = await async_dal.select_async(dal(query))
    if rows:
        return int(rows.first().id)

    new_id = await async_dal.insert_async(
        dal.music_tracks,
        tenant_id=tenant_id,
        provider=track.provider,
        external_id=track.external_id,
        title=track.title,
        artist=track.artist,
        duration_ms=track.duration_ms,
        artwork_url=track.artwork_url,
        url=track.url,
        created_at=datetime.now(UTC),
    )
    return int(new_id)


async def _sum_duration_ms_ahead(
    async_dal: Any, dal: Any, *, community_id: int, position: int
) -> int:
    """Sum `music_tracks.duration_ms` for every still-`queued` item ahead of `position`.

    Selects only `music_tracks.duration_ms` (a single table's field) even
    though the query joins `music_station_queue` -- mirrors
    `_is_live_music_category()`'s own single-table-select-with-join-filter
    pattern above, which keeps `Rows` flat (`row.duration_ms`, no per-table
    nesting) rather than depending on pydal's multi-table select row shape.
    """
    query = (
        (dal.music_station_queue.community_id == community_id)
        & (dal.music_station_queue.status == "queued")
        & (dal.music_station_queue.position < position)
        & (dal.music_station_queue.track_id == dal.music_tracks.id)
    )
    rows = await async_dal.select_async(dal(query), dal.music_tracks.duration_ms)
    return sum(int(row.duration_ms or 0) for row in rows)


async def _compute_eta_seconds(
    async_dal: Any, dal: Any, *, community_id: int, position: int
) -> int:
    """ETA (seconds) until `position` starts playing: queued-ahead durations + playing remainder.

    `0` means "next up" (nothing queued ahead AND nothing currently
    playing). The currently-`playing` item's remaining time is derived
    from `started_at` + its track's `duration_ms`, clamped to >=0 (a
    `playing` row with a stale/missing `started_at` degrades to counting
    its full duration rather than raising).
    """
    total_ms = await _sum_duration_ms_ahead(
        async_dal, dal, community_id=community_id, position=position
    )

    playing_query = (dal.music_station_queue.community_id == community_id) & (
        dal.music_station_queue.status == "playing"
    )
    playing_rows = await async_dal.select_async(dal(playing_query))
    if playing_rows:
        playing_row = playing_rows.first()
        track_row = await _get_track_row(async_dal, dal, track_id=playing_row.track_id)
        duration_ms = int(track_row.duration_ms or 0)
        started_at = playing_row.started_at
        if isinstance(started_at, datetime):
            elapsed_ms = max(0, int((datetime.now(UTC) - started_at).total_seconds() * 1000))
            remaining_ms = max(0, duration_ms - elapsed_ms)
        else:
            remaining_ms = duration_ms
        total_ms += remaining_ms

    return total_ms // 1000


async def queue_length(async_dal: Any, dal: Any, *, community_id: int) -> int:
    """Count of `queued` + `playing` items for a community -- backs `!sr status`."""
    query = (dal.music_station_queue.community_id == community_id) & (
        dal.music_station_queue.status.belongs(("queued", "playing"))
    )
    return int(await async_dal.count_async(query))


async def _next_queue_position(async_dal: Any, dal: Any, *, community_id: int) -> int:
    query = (dal.music_station_queue.community_id == community_id) & (
        dal.music_station_queue.status == "queued"
    )
    rows = await async_dal.select_async(
        dal(query), orderby=~dal.music_station_queue.position, limitby=(0, 1)
    )
    if not rows:
        return 1
    return int(rows.first().position) + 1


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


async def enqueue_request(
    async_dal: Any,
    dal: Any,
    *,
    tenant_id: int,
    community_id: int,
    url_or_query: str,
    provider: str | None,
    requested_by: int | None,
    is_admin_override: bool,
) -> QueueItemDTO:
    """Resolve `url_or_query` to a `Track` and enqueue it as a single song request."""
    if not url_or_query or not url_or_query.strip():
        raise bad_request("urlOrQuery is required")

    await _enforce_request_policy(
        async_dal,
        dal,
        tenant_id=tenant_id,
        community_id=community_id,
        actor_user_id=requested_by,
        is_admin_override=is_admin_override,
    )

    track = await _resolve_track(url_or_query, provider)
    track_id = await _get_or_create_track_id(async_dal, dal, tenant_id=tenant_id, track=track)
    position = await _next_queue_position(async_dal, dal, community_id=community_id)

    now = datetime.now(UTC)
    new_id = await async_dal.insert_async(
        dal.music_station_queue,
        tenant_id=tenant_id,
        community_id=community_id,
        track_id=track_id,
        position=position,
        status="queued",
        source="request",
        playlist_id=None,
        requested_by=requested_by,
        added_at=now,
    )
    queue_rows = await async_dal.select_async(dal(dal.music_station_queue.id == int(new_id)))
    track_row = await _get_track_row(async_dal, dal, track_id=track_id)
    eta_seconds = await _compute_eta_seconds(
        async_dal, dal, community_id=community_id, position=position
    )
    return _queue_item_dto(queue_rows.first(), track_row, eta_seconds=eta_seconds)


async def enqueue_playlist(
    async_dal: Any,
    dal: Any,
    *,
    tenant_id: int,
    community_id: int,
    items: list[str],
    provider: str | None,
    requested_by: int | None,
    is_admin_override: bool,
) -> tuple[str, list[QueueItemDTO]]:
    """Resolve every entry in `items` and enqueue them together under one playlist id."""
    cleaned = [item for item in (items or []) if item and item.strip()]
    if not cleaned:
        raise bad_request("items must contain at least one URL or query")

    await _enforce_request_policy(
        async_dal,
        dal,
        tenant_id=tenant_id,
        community_id=community_id,
        actor_user_id=requested_by,
        is_admin_override=is_admin_override,
    )

    playlist_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    position = await _next_queue_position(async_dal, dal, community_id=community_id)

    created: list[QueueItemDTO] = []
    for raw_item in cleaned:
        track = await _resolve_track(raw_item, provider)
        track_id = await _get_or_create_track_id(async_dal, dal, tenant_id=tenant_id, track=track)
        new_id = await async_dal.insert_async(
            dal.music_station_queue,
            tenant_id=tenant_id,
            community_id=community_id,
            track_id=track_id,
            position=position,
            status="queued",
            source="playlist",
            playlist_id=playlist_id,
            requested_by=requested_by,
            added_at=now,
        )
        queue_rows = await async_dal.select_async(dal(dal.music_station_queue.id == int(new_id)))
        track_row = await _get_track_row(async_dal, dal, track_id=track_id)
        created.append(_queue_item_dto(queue_rows.first(), track_row))
        position += 1

    return playlist_id, created


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def list_queue(
    async_dal: Any, dal: Any, *, community_id: int
) -> tuple[QueueItemDTO | None, list[QueueItemDTO]]:
    """Return `(now_playing, upcoming)` for a community -- upcoming ordered by position."""
    playing_rows = await async_dal.select_async(
        dal(
            (dal.music_station_queue.community_id == community_id)
            & (dal.music_station_queue.status == "playing")
        )
    )
    now_playing: QueueItemDTO | None = None
    if playing_rows:
        row = playing_rows.first()
        track_row = await _get_track_row(async_dal, dal, track_id=row.track_id)
        now_playing = _queue_item_dto(row, track_row)

    upcoming_rows = await async_dal.select_async(
        dal(
            (dal.music_station_queue.community_id == community_id)
            & (dal.music_station_queue.status == "queued")
        ),
        orderby=dal.music_station_queue.position | dal.music_station_queue.added_at,
    )
    upcoming: list[QueueItemDTO] = []
    for row in upcoming_rows:
        track_row = await _get_track_row(async_dal, dal, track_id=row.track_id)
        upcoming.append(_queue_item_dto(row, track_row))

    return now_playing, upcoming


# ---------------------------------------------------------------------------
# Moderation: kick / reorder / advance
# ---------------------------------------------------------------------------


async def kick_song(
    async_dal: Any,
    dal: Any,
    *,
    tenant_id: int,
    community_id: int,
    queue_id: int,
    actor_user_id: int,
    reason: str | None,
) -> None:
    """Remove one queue entry (any status) and record the moderation action."""
    query = (dal.music_station_queue.id == queue_id) & (
        dal.music_station_queue.community_id == community_id
    )
    rows = await async_dal.select_async(dal(query))
    if not rows:
        raise not_found(f"Queue item {queue_id} not found in this community")

    await async_dal.update_async(query, status="removed", ended_at=datetime.now(UTC))
    await _log_moderation(
        async_dal,
        dal,
        tenant_id=tenant_id,
        community_id=community_id,
        actor_user_id=actor_user_id,
        action="kick_song",
        target_queue_id=queue_id,
        reason=reason,
    )


async def kick_playlist(
    async_dal: Any,
    dal: Any,
    *,
    tenant_id: int,
    community_id: int,
    playlist_id: str,
    actor_user_id: int,
    reason: str | None,
) -> int:
    """Remove every still-queued entry from `playlist_id` and record one moderation action."""
    query = (
        (dal.music_station_queue.community_id == community_id)
        & (dal.music_station_queue.playlist_id == playlist_id)
        & (dal.music_station_queue.status == "queued")
    )
    rows = await async_dal.select_async(dal(query))
    if not rows:
        raise not_found(f"No queued items found for playlist {playlist_id!r} in this community")

    count = await async_dal.update_async(query, status="removed", ended_at=datetime.now(UTC))
    await _log_moderation(
        async_dal,
        dal,
        tenant_id=tenant_id,
        community_id=community_id,
        actor_user_id=actor_user_id,
        action="kick_playlist",
        target_playlist_id=playlist_id,
        reason=reason,
    )
    return int(count)


async def reorder_queue(
    async_dal: Any, dal: Any, *, community_id: int, ordered_queue_ids: list[int]
) -> list[QueueItemDTO]:
    """Reassign `position` for every currently-queued item to match `ordered_queue_ids` exactly."""
    if not ordered_queue_ids:
        raise bad_request("orderedQueueIds must not be empty")

    current_rows = await async_dal.select_async(
        dal(
            (dal.music_station_queue.community_id == community_id)
            & (dal.music_station_queue.status == "queued")
        )
    )
    current_ids = {int(row.id) for row in current_rows}
    requested_ids = [int(qid) for qid in ordered_queue_ids]

    if set(requested_ids) != current_ids or len(requested_ids) != len(current_ids):
        raise bad_request(
            "orderedQueueIds must contain exactly the community's currently-queued item ids"
        )

    for new_position, queue_id in enumerate(requested_ids, start=1):
        await async_dal.update_async(dal.music_station_queue.id == queue_id, position=new_position)

    _, upcoming = await list_queue(async_dal, dal, community_id=community_id)
    return upcoming


async def advance_queue(
    async_dal: Any, dal: Any, *, community_id: int
) -> tuple[QueueItemDTO | None, QueueItemDTO | None]:
    """Mark the current `playing` item `played`, promote the next `queued` item to `playing`."""
    now = datetime.now(UTC)

    playing_query = (dal.music_station_queue.community_id == community_id) & (
        dal.music_station_queue.status == "playing"
    )
    playing_rows = await async_dal.select_async(dal(playing_query))
    previous_dto: QueueItemDTO | None = None
    if playing_rows:
        row = playing_rows.first()
        track_row = await _get_track_row(async_dal, dal, track_id=row.track_id)
        previous_dto = _queue_item_dto(row, track_row)
        await async_dal.update_async(playing_query, status="played", ended_at=now)

    queued_query = (dal.music_station_queue.community_id == community_id) & (
        dal.music_station_queue.status == "queued"
    )
    next_rows = await async_dal.select_async(
        dal(queued_query),
        orderby=dal.music_station_queue.position | dal.music_station_queue.added_at,
        limitby=(0, 1),
    )
    next_dto: QueueItemDTO | None = None
    if next_rows:
        next_row = next_rows.first()
        await async_dal.update_async(
            dal.music_station_queue.id == next_row.id, status="playing", started_at=now
        )
        track_row = await _get_track_row(async_dal, dal, track_id=next_row.track_id)
        refreshed = await async_dal.select_async(dal(dal.music_station_queue.id == next_row.id))
        next_dto = _queue_item_dto(refreshed.first(), track_row)

    # Resequence remaining queued items to a clean 1..N run.
    remaining_rows = await async_dal.select_async(
        dal(queued_query),
        orderby=dal.music_station_queue.position | dal.music_station_queue.added_at,
    )
    for new_position, row in enumerate(remaining_rows, start=1):
        if row.position != new_position:
            await async_dal.update_async(
                dal.music_station_queue.id == row.id, position=new_position
            )

    return previous_dto, next_dto
