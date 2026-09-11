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

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from services.errors import ApiError, bad_request, forbidden, not_found, unprocessable
from services.music_providers import ProviderUnavailable, Track, TrackNotFound, resolve
from services.schema import bind_streaming_tables

logger = logging.getLogger(__name__)

_LIVE_PLATFORM = "twitch"
_MUSIC_CATEGORY_NAMES = frozenset({"music"})

#: gh-313 `youtube_allowed_labels` write bounds -- kept small enough that the
#: validation-failure message stays a single short, human-readable line
#: (`core/svc_action` relays it verbatim to chat on a rejected policy update).
_MAX_YOUTUBE_ALLOWED_LABELS = 32
_MAX_YOUTUBE_ALLOWED_LABEL_LENGTH = 64
YOUTUBE_LABEL_VALIDATION_MESSAGE = "youtube-labels: up to 32 labels, 64 chars each"


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
    youtubeAllowedLabels: list[str]
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


def _decode_youtube_allowed_labels(raw: Any) -> list[str]:
    """JSON-decode `music_policy.youtube_allowed_labels` -- NULL/invalid/wrong-shape -> `[]`.

    Never raises: a NULL column (unrestricted, the default) and a
    corrupted or legacy value both degrade to "no restriction" on read
    rather than a 500.
    """
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        return []
    return decoded


def _normalize_youtube_allowed_labels(labels: list[str]) -> list[str]:
    """Validate + normalize a `youtube_allowed_labels` write -- lowercase/trim/dedupe, bounded.

    Raises `bad_request(YOUTUBE_LABEL_VALIDATION_MESSAGE)` on more than
    `_MAX_YOUTUBE_ALLOWED_LABELS` entries, a non-string entry, or any
    entry that's blank or over `_MAX_YOUTUBE_ALLOWED_LABEL_LENGTH` chars
    once trimmed -- length is checked AFTER trim/lowercase so incidental
    whitespace never trips the bound. Order of first appearance is kept;
    duplicates (post-normalization) are dropped silently.
    """
    if len(labels) > _MAX_YOUTUBE_ALLOWED_LABELS:
        raise bad_request(YOUTUBE_LABEL_VALIDATION_MESSAGE)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        if not isinstance(raw, str):
            raise bad_request(YOUTUBE_LABEL_VALIDATION_MESSAGE)
        cleaned = raw.strip().lower()
        if not cleaned or len(cleaned) > _MAX_YOUTUBE_ALLOWED_LABEL_LENGTH:
            raise bad_request(YOUTUBE_LABEL_VALIDATION_MESSAGE)
        if cleaned not in seen:
            seen.add(cleaned)
            normalized.append(cleaned)
    return normalized


def _policy_dto(row: Any, *, community_id: int) -> PolicyDTO:
    return PolicyDTO(
        communityId=community_id,
        songRequestsAllowed=bool(row.song_requests_allowed),
        requestsCategoryRestricted=bool(row.requests_category_restricted),
        youtubeAllowedLabels=_decode_youtube_allowed_labels(row.youtube_allowed_labels),
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
        youtube_allowed_labels=None,
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
    youtube_allowed_labels: list[str] | None,
    updated_by: int | None,
) -> PolicyDTO:
    """Upsert the community's policy -- only the provided fields change.

    `youtube_allowed_labels=None` means "leave unchanged", same
    partial-update convention as the two boolean fields above; pass `[]`
    explicitly to clear the allowlist back to unrestricted. Validated and
    normalized via `_normalize_youtube_allowed_labels()` before being
    JSON-encoded for storage.
    """
    if (
        song_requests_allowed is None
        and requests_category_restricted is None
        and youtube_allowed_labels is None
    ):
        raise bad_request("No policy fields to update")

    normalized_youtube_labels = (
        _normalize_youtube_allowed_labels(youtube_allowed_labels)
        if youtube_allowed_labels is not None
        else None
    )

    existing = await async_dal.select_async(dal(dal.music_policy.community_id == community_id))
    now = datetime.now(UTC)

    if not existing:
        default_requests_allowed = (
            song_requests_allowed if song_requests_allowed is not None else True
        )
        default_category_restricted = (
            requests_category_restricted if requests_category_restricted is not None else False
        )
        default_youtube_labels_json = (
            json.dumps(normalized_youtube_labels) if normalized_youtube_labels is not None else None
        )
        new_id = await async_dal.insert_async(
            dal.music_policy,
            tenant_id=tenant_id,
            community_id=community_id,
            song_requests_allowed=default_requests_allowed,
            requests_category_restricted=default_category_restricted,
            youtube_allowed_labels=default_youtube_labels_json,
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
    if normalized_youtube_labels is not None:
        fields["youtube_allowed_labels"] = json.dumps(normalized_youtube_labels)

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


def _youtube_label_match(allowed_labels: list[str], track_labels: tuple[str, ...]) -> str | None:
    """First `allowed_labels` entry satisfied by `track_labels`, or `None` (gh-313).

    Match iff an allowed label equals a track label outright, OR is a
    whole word inside a multi-word track label -- e.g. allowed `"music"`
    matches track label `"music video"` but not `"musical"`. Both sides
    are already lowercase by the time they reach here
    (`_normalize_youtube_allowed_labels()` on write, `Track.labels` at
    resolution), so this is a plain string/word comparison, not a second
    case-fold.
    """
    for allowed in allowed_labels:
        for label in track_labels:
            if allowed == label or allowed in label.split():
                return allowed
    return None


async def _enforce_youtube_label_gate(
    async_dal: Any, dal: Any, *, community_id: int, track: Track
) -> None:
    """Reject a YouTube track whose labels don't satisfy the community's allowlist (gh-313).

    No-op when the track isn't from YouTube (Spotify/other providers are
    never gated by this policy field) or the community's
    `youtube_allowed_labels` list is empty (unrestricted, the default).
    Always DEBUG-logs the match attempt, pass or reject, so an operator
    can trace why a specific video was accepted or rejected.
    """
    if track.provider != "youtube":
        return

    policy_rows = await async_dal.select_async(dal(dal.music_policy.community_id == community_id))
    allowed_labels = (
        _decode_youtube_allowed_labels(policy_rows.first().youtube_allowed_labels)
        if policy_rows
        else []
    )
    if not allowed_labels:
        return

    matched = _youtube_label_match(allowed_labels, track.labels)
    logger.debug(
        "music.label_gate community_id=%s video=%s allowed=%s labels=%s matched=%s",
        community_id,
        track.external_id,
        allowed_labels,
        list(track.labels),
        matched,
    )
    if matched is None:
        raise ApiError(
            f"that video isn't allowed here (allowed: {', '.join(allowed_labels)})",
            422,
            "youtube_label_not_allowed",
        )


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
    async_dal: Any, dal: Any, redis_client: Any, *, community_id: int, position: int
) -> int:
    """ETA (seconds) until `position` starts playing: queued-ahead durations + playing remainder.

    `0` means "next up" (nothing queued ahead AND nothing currently
    playing). The currently-`playing` item's remaining time is `duration_ms
    - elapsed_ms` (gh-315 `_elapsed_ms()` -- pause-aware, "as if resumed
    now" while paused, see that function's own docstring), clamped to >=0
    (a `playing` row with a stale/missing `started_at` degrades to
    counting its full duration rather than raising).
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
        started_at = _as_aware_utc(playing_row.started_at)
        if started_at is not None:
            playback = await _read_playback_state(redis_client, community_id=community_id)
            elapsed_ms = _elapsed_ms(
                started_at=started_at, now=datetime.now(UTC), playback=playback
            )
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
    redis_client: Any,
    *,
    tenant_id: int,
    community_id: int,
    url_or_query: str,
    provider: str | None,
    requested_by: int | None,
    is_admin_override: bool,
    enforce_youtube_labels: bool,
) -> QueueItemDTO:
    """Resolve `url_or_query` to a `Track` and enqueue it as a single song request.

    `enforce_youtube_labels` gates the community's `youtube_allowed_labels`
    allowlist (gh-313) behind the `waddles.social.music.youtube_labels`
    PostHog flag -- callers resolve the flag themselves (blueprint layer,
    same convention as every other `feature_enabled()` check in this
    port) and pass the result through, so this function stays a pure
    enqueue operation rather than a flag client itself.
    """
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
    if enforce_youtube_labels:
        await _enforce_youtube_label_gate(async_dal, dal, community_id=community_id, track=track)
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
        async_dal, dal, redis_client, community_id=community_id, position=position
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
    redis_client: Any,
    *,
    tenant_id: int,
    community_id: int,
    queue_id: int,
    actor_user_id: int,
    reason: str | None,
) -> None:
    """Remove one queue entry (any status) and record the moderation action.

    Kicking the currently-`playing` item resets `music:playback:
    {community_id}` (gh-315) -- whatever plays next must start unpaused.
    """
    query = (dal.music_station_queue.id == queue_id) & (
        dal.music_station_queue.community_id == community_id
    )
    rows = await async_dal.select_async(dal(query))
    if not rows:
        raise not_found(f"Queue item {queue_id} not found in this community")
    was_playing = rows.first().status == "playing"

    await async_dal.update_async(query, status="removed", ended_at=datetime.now(UTC))
    if was_playing:
        await _clear_playback_state(redis_client, community_id=community_id)
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
    async_dal: Any, dal: Any, redis_client: Any, *, community_id: int
) -> tuple[QueueItemDTO | None, QueueItemDTO | None]:
    """Mark the current `playing` item `played`, promote the next `queued` item to `playing`.

    Always resets `music:playback:{community_id}` (gh-315) at the end --
    an explicit admin advance is still "an advance" per that key's own
    reset contract, same as the lazy/live-queue auto-advance path.
    """
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

    await _clear_playback_state(redis_client, community_id=community_id)
    return previous_dto, next_dto


# ---------------------------------------------------------------------------
# Live queue read model -- backs the OBS overlay player (`core/svc_presentation`)
# and the public (unauthenticated) queue page via `blueprints/v1/
# community_music_queue.py`'s `music_internal_bp` (service-key) routes and
# `blueprints/v1/public_music_queue.py`. Deliberately a SEPARATE, snake_case
# wire contract from `QueueItemDTO` above (camelCase, admin-API-only) --
# this shape is pinned by concurrent work against it; do not merge the two.
#
# `requested_by` never carries a raw user id or email -- only a display
# name + platform, resolved at read time by joining `community_members`
# (which already carries a per-platform `display_name`, see
# `services/schema.py`'s own field list for that table) on the
# `requested_by` (`hub_users.id`) value this row was enqueued with. An
# unresolvable requester (anonymous/unlinked platform identity, or no
# active `community_members` row at all) falls back to a generic label,
# never a new PII column.
# ---------------------------------------------------------------------------

#: Grace period added on top of a `playing` track's own `duration_ms`
#: before the lazy auto-advance considers it expired -- absorbs normal
#: clock/poll-interval drift between "the track actually finished" and
#: "a reader happened to poll" without prematurely cutting a track short.
_ADVANCE_GRACE_SECONDS = 10
_DISPLAY_NAME_FALLBACK = "platform user"
_PLATFORM_FALLBACK = "unknown"


@dataclass(slots=True, frozen=True)
class RequestedByDTO:
    """Attribution for one live queue item -- a display name only, never an id/email."""

    display_name: str
    platform: str


@dataclass(slots=True, frozen=True)
class LiveQueueItemDTO:
    """One `music_station_queue` row in the overlay/public-page wire shape (snake_case)."""

    id: int
    position: int
    status: str
    title: str
    artist: str
    duration_ms: int
    artwork_url: str | None
    provider: str
    external_id: str
    url: str
    eta_seconds: int | None
    started_at: str | None
    requested_by: RequestedByDTO


def _as_aware_utc(value: Any) -> datetime | None:
    """Normalize a possibly-naive DB-read `datetime` to aware UTC for safe arithmetic.

    Every `datetime` column here is written via `datetime.now(UTC)`
    (aware), but read back NAIVE on both sqlite and Postgres (pydal's
    `"datetime"` Field type maps to `TIMESTAMP WITHOUT TIME ZONE` --
    confirmed empirically against `pydal.DAL("sqlite:memory")`).
    Subtracting a naive value from `datetime.now(UTC)` raises `TypeError:
    can't subtract offset-naive and offset-aware datetimes`; every value
    this DAL produces was written as UTC, so re-attaching `UTC` (never
    re-interpreting as local time) is the correct fix, not just a
    convenient one.
    """
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Playback (pause/resume) -- gh-315. State lives ENTIRELY in Valkey
# (`music:playback:{community_id}`, JSON `{paused_since, paused_total_ms,
# updated_at}`), never in `music_station_queue` itself -- a paused track is
# still `status="playing"` in the DB; pausing is a clock adjustment layered
# on top. Absence of the key means "playing" (the default), so a community
# that never touches pause/resume needs no Valkey write at all. Written by
# `set_playback()` below; read (and reset) by the live-queue read model.
# ---------------------------------------------------------------------------

_PLAYBACK_KEY_PREFIX = "music:playback:"
_VALID_PLAYBACK_ACTIONS = frozenset({"pause", "resume"})


@dataclass(slots=True, frozen=True)
class PlaybackStateDTO:
    """One community's current pause/resume state, read from Valkey.

    `paused` is `False` (and `paused_since`/`paused_total_ms` folded into
    the caller's own elapsed-time math as "no pause") whenever the Valkey
    key is absent, corrupt, wrong-shape, or Valkey itself is unreachable
    -- "playing" is always the fail-open default, never a 500. See
    `_read_playback_state()`'s own docstring.
    """

    paused: bool
    paused_since: datetime | None
    paused_total_ms: int


#: A community that's never paused (or was just reset by an advance/kick) --
#: the same value `_read_playback_state()` returns for an absent key.
_UNPAUSED_STATE = PlaybackStateDTO(paused=False, paused_since=None, paused_total_ms=0)


def _playback_key(community_id: int) -> str:
    return f"{_PLAYBACK_KEY_PREFIX}{community_id}"


def _parse_iso(value: Any) -> datetime | None:
    """Best-effort ISO-8601 parse -- `None` on anything not a valid, non-empty string."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


async def _read_playback_state(redis_client: Any, *, community_id: int) -> PlaybackStateDTO:
    """Best-effort read of `music:playback:{community_id}` -- never raises.

    A missing key, a Valkey error, or a corrupt/wrong-shape payload all
    collapse to `_UNPAUSED_STATE` -- see `PlaybackStateDTO`'s own
    docstring for why fail-open is correct here (a read must never 500
    the two queue-read endpoints that depend on it).
    """
    try:
        raw = await redis_client.get(_playback_key(community_id))
    except Exception:
        logger.warning("music.playback.read_failed community_id=%s", community_id, exc_info=True)
        return _UNPAUSED_STATE

    if not raw:
        return _UNPAUSED_STATE

    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return _UNPAUSED_STATE
    if not isinstance(data, dict):
        return _UNPAUSED_STATE

    paused_since = _parse_iso(data.get("paused_since"))
    raw_total = data.get("paused_total_ms")
    paused_total_ms = int(raw_total) if isinstance(raw_total, int | float) else 0
    return PlaybackStateDTO(
        paused=paused_since is not None, paused_since=paused_since, paused_total_ms=paused_total_ms
    )


async def _write_playback_state(
    redis_client: Any,
    *,
    community_id: int,
    paused_since: datetime | None,
    paused_total_ms: int,
    now: datetime,
) -> bool:
    """Best-effort write of the full playback JSON shape; returns success (never raises)."""
    payload = json.dumps(
        {
            "paused_since": paused_since.isoformat() if paused_since else None,
            "paused_total_ms": paused_total_ms,
            "updated_at": now.isoformat(),
        }
    )
    try:
        await redis_client.set(_playback_key(community_id), payload)
        return True
    except Exception:
        logger.warning("music.playback.write_failed community_id=%s", community_id, exc_info=True)
        return False


async def _clear_playback_state(redis_client: Any, *, community_id: int) -> None:
    """Best-effort delete -- swallow errors; a failed clear just leaves a stale key.

    Called on every advance (lazy or explicit) and on kicking the
    currently-`playing` item -- the NEXT track must always start unpaused.
    Never blocks the queue mutation that triggered it: that DB write
    already succeeded, so a Valkey hiccup here is a lesser evil than
    failing the whole advance/kick.
    """
    try:
        await redis_client.delete(_playback_key(community_id))
    except Exception:
        logger.warning("music.playback.clear_failed community_id=%s", community_id, exc_info=True)


def _elapsed_ms(*, started_at: datetime, now: datetime, playback: PlaybackStateDTO) -> int:
    """Milliseconds of actual playback elapsed since `started_at`, pause time excluded.

    `elapsed = (now - started_at) - paused_total_ms - (now - paused_since if
    currently paused)`. While paused this is CONSTANT -- the `now -
    paused_since` term grows in lockstep with `now - started_at`, canceling
    out -- which is exactly "pausing stops the clock": auto-advance can
    never fire mid-pause (`_sync_get_live_state`'s own expiry check uses
    this directly), and `duration_ms - elapsed_ms` is automatically the
    correct "ETA as if resumed right now" with no special-casing.
    """
    elapsed_ms = (now - started_at).total_seconds() * 1000
    elapsed_ms -= playback.paused_total_ms
    if playback.paused_since is not None:
        elapsed_ms -= (now - playback.paused_since).total_seconds() * 1000
    return max(0, int(elapsed_ms))


def _clamped_position_ms(elapsed_ms: int, duration_ms: int) -> int:
    """`elapsed_ms` clamped to `[0, duration_ms]` -- never past the end of the track."""
    return max(0, min(elapsed_ms, duration_ms))


def _sync_resolve_requested_by(
    dal: Any, *, community_id: int, requested_by: int | None
) -> RequestedByDTO:
    """Best-effort display-name lookup for a `music_station_queue.requested_by` value.

    Joins `community_members` on `(community_id, user_id=str(requested_by),
    is_active=True)` -- the same legacy-VARCHAR `user_id` column every
    other `community_members` lookup in this port compares as a string
    (see `services/community_authz.py`'s own note). `requested_by=None`
    (anonymous/unlinked chat requester -- see `_resolve_requester()`
    above) and "member row found but has no `display_name` set" both fall
    back to the same generic label -- never raises, never a new column.
    """
    if requested_by is None:
        return RequestedByDTO(display_name=_DISPLAY_NAME_FALLBACK, platform=_PLATFORM_FALLBACK)

    row = (
        dal(
            (dal.community_members.community_id == community_id)
            & (dal.community_members.user_id == str(requested_by))
            & (dal.community_members.is_active == True)  # noqa: E712 - pydal idiom
        )
        .select(orderby=dal.community_members.id, limitby=(0, 1))
        .first()
    )
    if row is None or not row.display_name:
        platform = row.platform if row is not None and row.platform else _PLATFORM_FALLBACK
        return RequestedByDTO(display_name=_DISPLAY_NAME_FALLBACK, platform=platform)
    return RequestedByDTO(
        display_name=row.display_name, platform=row.platform or _PLATFORM_FALLBACK
    )


def _sync_live_item_dto(
    dal: Any, row: Any, track: Any, *, community_id: int, eta_seconds: int | None
) -> LiveQueueItemDTO:
    return LiveQueueItemDTO(
        id=int(row.id),
        position=int(row.position),
        status=row.status,
        title=track.title,
        artist=track.artist,
        duration_ms=int(track.duration_ms or 0),
        artwork_url=track.artwork_url,
        provider=track.provider,
        external_id=track.external_id,
        url=track.url,
        eta_seconds=eta_seconds,
        started_at=_iso(row.started_at),
        requested_by=_sync_resolve_requested_by(
            dal, community_id=community_id, requested_by=row.requested_by
        ),
    )


def _sync_build_live_dtos(
    dal: Any,
    *,
    community_id: int,
    playing_row: Any,
    queued_rows: list[Any],
    now: datetime,
    playback: PlaybackStateDTO,
) -> tuple[LiveQueueItemDTO | None, list[LiveQueueItemDTO]]:
    """Build `(now_playing, queue)` DTOs from already-locked/committed rows.

    ETA for each queued item is the sum of every still-queued track ahead
    of it plus the currently-playing track's own remaining time -- same
    formula as `_compute_eta_seconds()` above, recomputed here from the
    rows already in hand (no extra query) since this always runs inside
    the same locked transaction that read them. `playback` (gh-315) makes
    the playing track's remaining time pause-aware via `_elapsed_ms()` --
    while paused, ETAs for everything queued behind it are naturally
    frozen too (computed "as if resumed now"). `now_playing` itself gets
    `eta_seconds=None` -- it's already playing, there's nothing to wait
    for.
    """
    track_ids = {int(row.track_id) for row in queued_rows}
    if playing_row is not None:
        track_ids.add(int(playing_row.track_id))
    tracks: dict[int, Any] = (
        {int(t.id): t for t in dal(dal.music_tracks.id.belongs(list(track_ids))).select()}
        if track_ids
        else {}
    )

    now_playing_dto: LiveQueueItemDTO | None = None
    running_ahead_ms = 0
    if playing_row is not None:
        track = tracks[int(playing_row.track_id)]
        now_playing_dto = _sync_live_item_dto(
            dal, playing_row, track, community_id=community_id, eta_seconds=None
        )
        duration_ms = int(track.duration_ms or 0)
        started_at = _as_aware_utc(playing_row.started_at)
        if started_at is not None:
            elapsed_ms = _elapsed_ms(started_at=started_at, now=now, playback=playback)
            running_ahead_ms = max(0, duration_ms - elapsed_ms)
        else:
            running_ahead_ms = duration_ms

    queue_dtos: list[LiveQueueItemDTO] = []
    for row in queued_rows:
        track = tracks[int(row.track_id)]
        queue_dtos.append(
            _sync_live_item_dto(
                dal, row, track, community_id=community_id, eta_seconds=running_ahead_ms // 1000
            )
        )
        running_ahead_ms += int(track.duration_ms or 0)

    return now_playing_dto, queue_dtos


def _sync_get_live_state(
    dal: Any,
    *,
    community_id: int,
    auto_advance: bool,
    now: datetime,
    playback: PlaybackStateDTO,
) -> tuple[LiveQueueItemDTO | None, list[LiveQueueItemDTO], bool]:
    """Single executor job: lock + (optionally) auto-advance/auto-start + build DTOs + commit.

    `AsyncDAL.transaction_async()`'s own docstring (`libs/flask_core/
    flask_core/database.py`) is explicit that every `*_async()` write
    method commits inside its OWN executor job, so nothing short of one
    synchronous function submitted as a SINGLE `run_in_executor()` job
    guarantees cross-statement atomicity here -- see that docstring's own
    "bundle an entire read-modify-write + `dal.commit()` into ONE
    synchronous function" guidance, which this follows directly rather
    than composing multiple awaited `*_async()` calls.

    `SELECT ... FOR UPDATE` locks the community's active (`playing`/
    `queued`) rows for the rest of this transaction wherever the adapter
    supports it (`dal._adapter.dbengine != "sqlite"` -- sqlite rejects the
    syntax outright at the driver level, and this port's own sqlite test
    fixtures are `pool_size=1` anyway, i.e. single-threaded-serialized
    regardless). Two callers racing the same expiry/auto-start window
    therefore always serialize on this lock in production: the second
    one's `SELECT ... FOR UPDATE` blocks until the first commits, then
    observes the ALREADY-advanced state and correctly no-ops -- never a
    double-advance.
    """
    q = dal.music_station_queue
    query = (q.community_id == community_id) & (q.status.belongs(("playing", "queued")))
    for_update = dal._adapter.dbengine != "sqlite"
    try:
        rows = dal(query).select(orderby=q.position | q.added_at, for_update=for_update)

        playing_row: Any = None
        queued_rows: list[Any] = []
        for row in rows:
            if row.status == "playing":
                playing_row = row
            else:
                queued_rows.append(row)

        advanced = False
        if auto_advance:
            if playing_row is not None:
                track = dal(dal.music_tracks.id == playing_row.track_id).select().first()
                duration_ms = int(track.duration_ms or 0) if track is not None else 0
                started_at = _as_aware_utc(playing_row.started_at)
                # gh-315: pause-aware elapsed -- `_elapsed_ms()` freezes while
                # `playback.paused`, so a track paused past its own duration
                # never expires here (the auto-advance-not-firing-while-paused
                # contract), with no separate `if playback.paused: skip` branch
                # needed.
                expired = started_at is not None and (
                    _elapsed_ms(started_at=started_at, now=now, playback=playback)
                    >= duration_ms + _ADVANCE_GRACE_SECONDS * 1000
                )
                if expired:
                    dal(q.id == playing_row.id).update(status="played", ended_at=now)
                    logger.debug(
                        "music.live_queue.auto_advance_expired community_id=%s queue_id=%s",
                        community_id,
                        playing_row.id,
                    )
                    playing_row = None
                    advanced = True

            if playing_row is None and queued_rows:
                head = queued_rows.pop(0)
                dal(q.id == head.id).update(status="playing", started_at=now)
                playing_row = dal(q.id == head.id).select().first()
                advanced = True
                logger.debug(
                    "music.live_queue.auto_start community_id=%s queue_id=%s",
                    community_id,
                    head.id,
                )
            elif playing_row is None:
                logger.debug(
                    "music.live_queue.auto_advance_noop_empty_queue community_id=%s",
                    community_id,
                )

        now_playing_dto, queue_dtos = _sync_build_live_dtos(
            dal,
            community_id=community_id,
            playing_row=playing_row,
            queued_rows=queued_rows,
            now=now,
            playback=playback,
        )
        dal.commit()
        return now_playing_dto, queue_dtos, advanced
    except Exception:
        dal.rollback()
        raise


def _sync_guarded_advance(
    dal: Any, *, community_id: int, item_id: int, now: datetime, playback: PlaybackStateDTO
) -> tuple[LiveQueueItemDTO | None, list[LiveQueueItemDTO], bool]:
    """Single executor job: advance ONLY if `item_id` is still the community's `playing` item.

    Same lock/atomicity rationale as `_sync_get_live_state()` above. A
    stale `item_id` (already advanced by a concurrent caller, or never
    the playing item at all) is a no-op -- `advanced=False`, current
    state returned unchanged, never an error: this is the expected
    outcome of losing the race, not a caller mistake.
    """
    q = dal.music_station_queue
    query = (q.community_id == community_id) & (q.status.belongs(("playing", "queued")))
    for_update = dal._adapter.dbengine != "sqlite"
    try:
        rows = dal(query).select(orderby=q.position | q.added_at, for_update=for_update)

        playing_row: Any = None
        queued_rows: list[Any] = []
        for row in rows:
            if row.status == "playing":
                playing_row = row
            else:
                queued_rows.append(row)

        advanced = False
        if playing_row is not None and int(playing_row.id) == int(item_id):
            dal(q.id == playing_row.id).update(status="played", ended_at=now)
            playing_row = None
            advanced = True
            if queued_rows:
                head = queued_rows.pop(0)
                dal(q.id == head.id).update(status="playing", started_at=now)
                playing_row = dal(q.id == head.id).select().first()
            logger.debug(
                "music.live_queue.guarded_advance community_id=%s item_id=%s",
                community_id,
                item_id,
            )
        else:
            logger.debug(
                "music.live_queue.guarded_advance_rejected community_id=%s item_id=%s "
                "current_playing_id=%s",
                community_id,
                item_id,
                playing_row.id if playing_row is not None else None,
            )

        now_playing_dto, queue_dtos = _sync_build_live_dtos(
            dal,
            community_id=community_id,
            playing_row=playing_row,
            queued_rows=queued_rows,
            now=now,
            playback=playback,
        )
        dal.commit()
        return now_playing_dto, queue_dtos, advanced
    except Exception:
        dal.rollback()
        raise


@dataclass(slots=True, frozen=True)
class LiveQueueSnapshot:
    """Bundled result of a live-queue read/advance -- avoids a 6-element return tuple (gh-315).

    `paused`/`paused_since` are the community's raw Valkey playback state
    (independent of what's playing); `position_ms` is `None` whenever
    `now_playing` is `None` -- there's nothing to report a position for.
    """

    now_playing: LiveQueueItemDTO | None
    queue: list[LiveQueueItemDTO]
    advanced: bool
    paused: bool
    paused_since: str | None
    position_ms: int | None


def _now_playing_position_ms(
    now_playing: LiveQueueItemDTO | None, playback: PlaybackStateDTO, now: datetime
) -> int | None:
    """`position_ms` for `now_playing`, or `None` if nothing's playing (gh-315).

    Reconstructs `started_at` from `LiveQueueItemDTO.started_at`'s own ISO
    string (produced by `_iso()` from an already-UTC-aware `datetime`, so
    `fromisoformat()` round-trips it exactly) rather than re-querying the
    DB -- this always runs right after the DTO was built, in the same
    async wrapper, from the exact `now` used for that build.
    """
    if now_playing is None or now_playing.started_at is None:
        return None
    started_at = _parse_iso(now_playing.started_at) or now
    elapsed_ms = _elapsed_ms(started_at=started_at, now=now, playback=playback)
    return _clamped_position_ms(elapsed_ms, now_playing.duration_ms)


async def get_live_queue_state(
    async_dal: Any, dal: Any, redis_client: Any, *, community_id: int, auto_advance: bool
) -> LiveQueueSnapshot:
    """Read a community's live queue; `auto_advance=True` also expires/promotes atomically.

    `auto_advance=False` (the public, unauthenticated page) is a pure
    read with no side effects -- runs through the same locking helper for
    one consistent code path, but never mutates anything itself (`_sync_
    get_live_state`'s own `if auto_advance:` guard).

    Playback state (gh-315) is read from Valkey BEFORE entering the locked
    executor job and used for that job's own auto-advance-expiry check and
    ETA math -- a pause/resume racing this call is accepted as a minor,
    documented staleness window (Valkey and the `music_station_queue`
    lock are two separate stores, never one transaction). If this call
    itself advances the queue (lazy expiry or auto-start), the playback
    key is reset (`_clear_playback_state`) and the returned snapshot
    reports the fresh, unpaused state for whatever's playing now.
    """
    loop = asyncio.get_event_loop()
    now = datetime.now(UTC)
    playback = await _read_playback_state(redis_client, community_id=community_id)
    now_playing, queue, advanced = await loop.run_in_executor(
        async_dal.executor,
        lambda: _sync_get_live_state(
            dal, community_id=community_id, auto_advance=auto_advance, now=now, playback=playback
        ),
    )
    if advanced:
        await _clear_playback_state(redis_client, community_id=community_id)
        playback = _UNPAUSED_STATE
    return LiveQueueSnapshot(
        now_playing=now_playing,
        queue=queue,
        advanced=advanced,
        paused=playback.paused,
        paused_since=_iso(playback.paused_since),
        position_ms=_now_playing_position_ms(now_playing, playback, now),
    )


async def advance_live_queue(
    async_dal: Any, dal: Any, redis_client: Any, *, community_id: int, item_id: int
) -> LiveQueueSnapshot:
    """Guarded advance: only if `item_id` is the community's current `playing` item.

    Resets `music:playback:{community_id}` (gh-315) whenever `advanced`
    ends up `True` -- see `LiveQueueSnapshot`'s own docstring for the
    returned shape.
    """
    loop = asyncio.get_event_loop()
    now = datetime.now(UTC)
    playback = await _read_playback_state(redis_client, community_id=community_id)
    now_playing, queue, advanced = await loop.run_in_executor(
        async_dal.executor,
        lambda: _sync_guarded_advance(
            dal, community_id=community_id, item_id=item_id, now=now, playback=playback
        ),
    )
    if advanced:
        await _clear_playback_state(redis_client, community_id=community_id)
        playback = _UNPAUSED_STATE
    return LiveQueueSnapshot(
        now_playing=now_playing,
        queue=queue,
        advanced=advanced,
        paused=playback.paused,
        paused_since=_iso(playback.paused_since),
        position_ms=_now_playing_position_ms(now_playing, playback, now),
    )


# ---------------------------------------------------------------------------
# Playback (pause/resume) mutation -- `POST /api/v1/internal/music/playback`
# (gh-315). Unlike the live-queue read model above, this needs no `SELECT
# ... FOR UPDATE` locked-transaction executor job: Valkey, not this table's
# own `status` column, is the resource being mutated, so it stays on the
# ordinary `async_dal.select_async()` path every other function in this
# module (outside the "Live queue read model" section) already uses.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class PlaybackActionResultDTO:
    """Response payload for `POST /api/v1/internal/music/playback`.

    `now_playing` is the same `LiveQueueItemDTO` shape the live-queue
    endpoints return (this is an internal, service-key-gated, overlay-
    adjacent endpoint, same family) -- `None` only when `reason ==
    "nothing_playing"`.
    """

    community_id: int
    paused: bool
    paused_since: str | None
    position_ms: int | None
    now_playing: LiveQueueItemDTO | None
    changed: bool
    reason: str


async def _async_resolve_requested_by(
    async_dal: Any, dal: Any, *, community_id: int, requested_by: int | None
) -> RequestedByDTO:
    """Async, non-blocking counterpart of `_sync_resolve_requested_by()` -- same lookup.

    `set_playback()` doesn't run inside `_sync_get_live_state()`'s locked
    executor job (see this section's own module comment), so it needs an
    `async_dal.select_async()`-based version rather than the sync `dal(
    ...).select()` the executor-only helper uses.
    """
    if requested_by is None:
        return RequestedByDTO(display_name=_DISPLAY_NAME_FALLBACK, platform=_PLATFORM_FALLBACK)

    query = (
        (dal.community_members.community_id == community_id)
        & (dal.community_members.user_id == str(requested_by))
        & (dal.community_members.is_active == True)  # noqa: E712 - pydal idiom
    )
    rows = await async_dal.select_async(
        dal(query), orderby=dal.community_members.id, limitby=(0, 1)
    )
    if not rows or not rows.first().display_name:
        platform = rows.first().platform if rows and rows.first().platform else _PLATFORM_FALLBACK
        return RequestedByDTO(display_name=_DISPLAY_NAME_FALLBACK, platform=platform)
    row = rows.first()
    return RequestedByDTO(
        display_name=row.display_name, platform=row.platform or _PLATFORM_FALLBACK
    )


async def _async_live_item_dto(
    async_dal: Any, dal: Any, row: Any, track: Any, *, community_id: int, eta_seconds: int | None
) -> LiveQueueItemDTO:
    """Async, non-blocking counterpart of `_sync_live_item_dto()` -- see that function's shape."""
    requested_by = await _async_resolve_requested_by(
        async_dal, dal, community_id=community_id, requested_by=row.requested_by
    )
    return LiveQueueItemDTO(
        id=int(row.id),
        position=int(row.position),
        status=row.status,
        title=track.title,
        artist=track.artist,
        duration_ms=int(track.duration_ms or 0),
        artwork_url=track.artwork_url,
        provider=track.provider,
        external_id=track.external_id,
        url=track.url,
        eta_seconds=eta_seconds,
        started_at=_iso(row.started_at),
        requested_by=requested_by,
    )


async def set_playback(
    async_dal: Any, dal: Any, redis_client: Any, *, community_id: int, action: str
) -> PlaybackActionResultDTO:
    """Pause or resume a community's currently-playing track (gh-315).

    Mutates ONLY `music:playback:{community_id}` -- never the
    `music_station_queue` row's own `status`/`started_at` (a paused track
    is still, in DB terms, `status="playing"`; pausing is purely a clock
    adjustment layered on top, see `_elapsed_ms()`'s own docstring).
    `reason="nothing_playing"` short-circuits before touching Valkey at
    all -- there's no clock to pause/resume with nothing in the `playing`
    slot. `already_paused`/`already_playing` are no-ops (`changed=False`,
    no Valkey write) -- idempotent by design, never an error.
    """
    if action not in _VALID_PLAYBACK_ACTIONS:
        raise bad_request("action must be 'pause' or 'resume'")

    playing_query = (dal.music_station_queue.community_id == community_id) & (
        dal.music_station_queue.status == "playing"
    )
    playing_rows = await async_dal.select_async(dal(playing_query))
    if not playing_rows:
        logger.debug(
            "music.playback.nothing_playing community_id=%s action=%s", community_id, action
        )
        return PlaybackActionResultDTO(
            community_id=community_id,
            paused=False,
            paused_since=None,
            position_ms=None,
            now_playing=None,
            changed=False,
            reason="nothing_playing",
        )

    playing_row = playing_rows.first()
    track_row = await _get_track_row(async_dal, dal, track_id=playing_row.track_id)
    duration_ms = int(track_row.duration_ms or 0)
    started_at = _as_aware_utc(playing_row.started_at)
    now = datetime.now(UTC)
    current = await _read_playback_state(redis_client, community_id=community_id)

    if action == "pause":
        if current.paused:
            new_state, changed, reason = current, False, "already_paused"
            logger.debug("music.playback.already_paused community_id=%s", community_id)
        else:
            ok = await _write_playback_state(
                redis_client,
                community_id=community_id,
                paused_since=now,
                paused_total_ms=current.paused_total_ms,
                now=now,
            )
            if not ok:
                raise ApiError(
                    "Unable to persist playback state", 503, "PLAYBACK_STORE_UNAVAILABLE"
                )
            new_state = PlaybackStateDTO(
                paused=True, paused_since=now, paused_total_ms=current.paused_total_ms
            )
            changed, reason = True, "paused"
            logger.debug(
                "music.playback.paused community_id=%s queue_id=%s", community_id, playing_row.id
            )
    else:  # resume
        if not current.paused:
            new_state, changed, reason = current, False, "already_playing"
            logger.debug("music.playback.already_playing community_id=%s", community_id)
        else:
            paused_since = current.paused_since
            assert paused_since is not None  # noqa: S101 - current.paused implies this
            additional_pause_ms = max(0, int((now - paused_since).total_seconds() * 1000))
            new_total = current.paused_total_ms + additional_pause_ms
            ok = await _write_playback_state(
                redis_client,
                community_id=community_id,
                paused_since=None,
                paused_total_ms=new_total,
                now=now,
            )
            if not ok:
                raise ApiError(
                    "Unable to persist playback state", 503, "PLAYBACK_STORE_UNAVAILABLE"
                )
            new_state = PlaybackStateDTO(paused=False, paused_since=None, paused_total_ms=new_total)
            changed, reason = True, "resumed"
            logger.debug(
                "music.playback.resumed community_id=%s queue_id=%s", community_id, playing_row.id
            )

    position_ms: int | None = None
    if started_at is not None:
        elapsed_ms = _elapsed_ms(started_at=started_at, now=now, playback=new_state)
        position_ms = _clamped_position_ms(elapsed_ms, duration_ms)

    now_playing_dto = await _async_live_item_dto(
        async_dal, dal, playing_row, track_row, community_id=community_id, eta_seconds=None
    )

    return PlaybackActionResultDTO(
        community_id=community_id,
        paused=new_state.paused,
        paused_since=_iso(new_state.paused_since),
        position_ms=position_ms,
        now_playing=now_playing_dto,
        changed=changed,
        reason=reason,
    )
