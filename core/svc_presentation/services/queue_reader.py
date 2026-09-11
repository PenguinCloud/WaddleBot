"""Read a community's music queue from hub-api's internal music-queue endpoint.

hub-api's `GET /api/v1/internal/music/queue?community_id=<int>` (built
concurrently alongside this task -- see `hub_api/blueprints/v1/
community_music_queue.py`'s own `music_internal_bp`) is the real, current
queue-state source: it lazily auto-starts/auto-advances the queue on read,
so this reader never has to run its own advance-on-timer loop -- polling
the endpoint IS how the queue moves forward for any community nobody has
explicitly advanced yet. A prior version of this module read a Valkey key
(`UnifiedQueue`'s own `{namespace}:{community_id}:queue`) directly --
retired in favor of this real endpoint, matching this service's own
documented posture that direct storage reads across a container boundary
were a stopgap, not the destination.

DTO mapping decision: this module's `QueueTrack` renames hub-api's wire
fields to this service's own pre-existing, shorter names where a direct
synonym exists (`id`->`queue_id`, `title`->`name`, `artwork_url`->
`album_art_url`, `url`->`uri`) so `services/render.py`'s player JS keeps
its original field vocabulary and only needs new fields added, not a
wholesale rename -- and adds the genuinely new fields this task's advance/
attribution requirements need (`position`, `eta_seconds`, `started_at`,
`requested_by`). The old `votes` field is dropped: hub-api's `QueueItem`
has no such concept (this queue has no voting), so keeping a permanently-
zero `votes` field would misrepresent a removed feature as still live
(security.md Output Validation: an explicit wire schema, not a stale one).

Community resolution (slug vs numeric `community_id`) lives in
`services/surfaces.py::resolve_community_id`, shared with
`presentation_config_service.py`'s own pre-existing local-DB lookups.

`QueueSnapshot.playback` (`PlaybackState`) carries hub-api's server-side
pause/resume/seek state through unchanged (`paused`, `paused_since`,
`position_ms`) -- absent on the wire defaults to "playing"
(`_DEFAULT_PLAYBACK`), matching this task's contract for a field that may
not exist on an older hub-api build.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

#: Providers with a real, documented client-side embed today (task scope:
#: YouTube IFrame API + Spotify embed). SoundCloud tracks still render in
#: the queue/now-playing list -- just without a player embed (no fake
#: player, an honestly-absent one).
EMBEDDABLE_PROVIDERS: frozenset[str] = frozenset({"youtube", "spotify"})

_QUEUE_PATH = "/api/v1/internal/music/queue"
_ADVANCE_PATH = "/api/v1/internal/music/queue/advance"

#: Task-specified fixed values -- HTTP call budget and in-process cache
#: freshness window. Kept as module constants (matching `services/
#: reputation_gate_client.py`'s own `_TIMEOUT_SECONDS` pattern) rather than
#: config/env-driven: this task pinned exact numbers, not a tunable.
_TIMEOUT_SECONDS = 3.0
_CACHE_TTL_SECONDS = 2.0


@dataclass(slots=True, frozen=True)
class RequestedBy:
    """Who requested a queued track -- `QueueItem.requested_by` on the wire."""

    display_name: str
    platform: str


@dataclass(slots=True, frozen=True)
class PlaybackState:
    """Server-side pause/resume/seek control -- hub-api's `QueueItem.playback` on the wire.

    Drives `services/render.py`'s player JS: `paused` pauses/resumes the
    embed, `position_ms` is the authoritative seek target on resume, and
    `paused_since` is display-only (unused today, carried through for a
    future "paused Xs ago" affordance). Absent on the wire -- an older
    hub-api build, or a race before the first pause -- means "playing":
    see `_DEFAULT_PLAYBACK`.
    """

    paused: bool
    paused_since: str | None
    position_ms: int | None


#: The wire contract's documented default when `playback` is missing entirely.
_DEFAULT_PLAYBACK = PlaybackState(paused=False, paused_since=None, position_ms=None)


@dataclass(slots=True, frozen=True)
class QueueTrack:
    """One normalized queue entry as rendered to the Music Station overlay."""

    queue_id: int
    position: int
    status: str
    provider: str
    external_id: str
    name: str
    artist: str
    album_art_url: str
    duration_ms: int
    uri: str
    eta_seconds: int | None
    started_at: str | None
    requested_by: RequestedBy | None


@dataclass(slots=True, frozen=True)
class QueueSnapshot:
    """One community's queue read -- `now_playing` + `upcoming`, plus cache freshness."""

    community_id: int
    now_playing: QueueTrack | None
    upcoming: list[QueueTrack]
    updated_at: str | None
    stale: bool
    playback: PlaybackState = _DEFAULT_PLAYBACK


def _requested_by_from_dto(raw: Any) -> RequestedBy | None:
    if not isinstance(raw, dict):
        return None
    return RequestedBy(
        display_name=str(raw.get("display_name") or ""),
        platform=str(raw.get("platform") or ""),
    )


def _queue_track_from_dto(raw: Any) -> QueueTrack | None:
    """Parse one `QueueItem` DTO entry. `None` on a malformed entry -- skipped, never raised."""
    if not isinstance(raw, dict):
        return None
    try:
        queue_id = int(raw["id"])
    except (KeyError, TypeError, ValueError):
        return None
    eta_raw = raw.get("eta_seconds")
    eta_seconds = int(eta_raw) if isinstance(eta_raw, int | float) else None
    started_at = raw.get("started_at")
    return QueueTrack(
        queue_id=queue_id,
        position=int(raw.get("position", 0) or 0),
        status=str(raw.get("status") or "queued"),
        provider=str(raw.get("provider") or ""),
        external_id=str(raw.get("external_id") or ""),
        name=str(raw.get("title") or "Unknown Track"),
        artist=str(raw.get("artist") or "Unknown Artist"),
        album_art_url=str(raw.get("artwork_url") or ""),
        duration_ms=int(raw.get("duration_ms", 0) or 0),
        uri=str(raw.get("url") or ""),
        eta_seconds=eta_seconds,
        started_at=str(started_at) if started_at else None,
        requested_by=_requested_by_from_dto(raw.get("requested_by")),
    )


def _playback_from_dto(raw: Any) -> PlaybackState:
    """Parse hub-api's `QueueItem.playback` DTO -- missing/malformed defaults to "playing"."""
    if not isinstance(raw, dict):
        return _DEFAULT_PLAYBACK
    paused_since = raw.get("paused_since")
    position_raw = raw.get("position_ms")
    position_ms = int(position_raw) if isinstance(position_raw, int | float) else None
    return PlaybackState(
        paused=bool(raw.get("paused", False)),
        paused_since=str(paused_since) if paused_since else None,
        position_ms=position_ms,
    )


def _snapshot_from_dto(community_id: int, data: dict[str, Any]) -> QueueSnapshot:
    """Parse hub-api's `{community_id, now_playing, queue, updated_at, playback}` `data` object."""
    now_playing = _queue_track_from_dto(data.get("now_playing"))
    upcoming: list[QueueTrack] = []
    raw_queue = data.get("queue")
    if isinstance(raw_queue, list):
        for raw_item in raw_queue:
            track = _queue_track_from_dto(raw_item)
            if track is not None:
                upcoming.append(track)
    updated_at = data.get("updated_at")
    return QueueSnapshot(
        community_id=community_id,
        now_playing=now_playing,
        upcoming=upcoming,
        updated_at=str(updated_at) if updated_at else None,
        stale=False,
        playback=_playback_from_dto(data.get("playback")),
    )


def _stale_or_empty(
    community_id: int, cache_entry: tuple[float, QueueSnapshot] | None
) -> QueueSnapshot:
    """A failed/unavailable read: the last cached snapshot marked stale, else an empty queue."""
    if cache_entry is not None:
        return dataclasses.replace(cache_entry[1], stale=True)
    return QueueSnapshot(
        community_id=community_id,
        now_playing=None,
        upcoming=[],
        updated_at=None,
        stale=False,
        playback=_DEFAULT_PLAYBACK,
    )


@dataclass(slots=True)
class MusicQueueReader:
    """HTTP client for hub-api's internal music-queue endpoints, with a short read-through cache.

    `connected` reflects configuration readiness (a non-empty
    `service_api_key`), not live reachability -- an unreachable hub-api is
    a per-call, logged, gracefully-degraded outcome (`get_queue`/
    `advance` never raise), while a missing service key is a startup-time
    misconfiguration this reader refuses to even attempt calls against
    (`blueprints/music.py` surfaces this as `queue unavailable: service
    key not configured` rather than silently trying and failing every
    poll).
    """

    hub_api_url: str
    service_api_key: str
    timeout_seconds: float = _TIMEOUT_SECONDS
    cache_ttl_seconds: float = _CACHE_TTL_SECONDS
    connected: bool = field(default=False, init=False)
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)
    _cache: dict[int, tuple[float, QueueSnapshot]] = field(
        default_factory=dict, init=False, repr=False
    )

    async def start(self) -> None:
        """Build the HTTP client. Never raises -- a missing service key just disables reads."""
        self._client = httpx.AsyncClient(base_url=self.hub_api_url, timeout=self.timeout_seconds)
        if not self.service_api_key:
            logger.warning(
                "music_queue_reader.no_service_key -- SERVICE_API_KEY not configured, "
                "queue reads will report unavailable until it is set"
            )
            self.connected = False
            return
        self.connected = True
        logger.info("music_queue_reader.ready hub_api_url=%s", self.hub_api_url)

    async def stop(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()

    async def get_queue(self, community_id: int) -> QueueSnapshot:
        """Return `community_id`'s queue snapshot. Never raises -- degrades to stale/empty.

        Read-through: a hit inside `cache_ttl_seconds` of the last real
        fetch (per community) skips the network call entirely -- this is
        an in-process cache only (per worker process), matching the
        5-second overlay poll interval this exists to absorb, not a
        cross-process/Valkey-backed cache.
        """
        cache_entry = self._cache.get(community_id)
        now = time.monotonic()
        if cache_entry is not None and (now - cache_entry[0]) < self.cache_ttl_seconds:
            logger.debug("music_queue_reader.cache_hit community_id=%d", community_id)
            return cache_entry[1]

        if not self.connected or self._client is None:
            logger.debug(
                "music_queue_reader.skipped community_id=%d reason=not_connected", community_id
            )
            return _stale_or_empty(community_id, cache_entry)

        try:
            response = await self._client.get(
                _QUEUE_PATH,
                params={"community_id": community_id},
                headers={"X-Service-Key": self.service_api_key},
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "music_queue_reader.unreachable community_id=%d error=%s", community_id, exc
            )
            return _stale_or_empty(community_id, cache_entry)

        if response.status_code >= 400:
            logger.warning(
                "music_queue_reader.rejected community_id=%d status=%d",
                community_id,
                response.status_code,
            )
            return _stale_or_empty(community_id, cache_entry)

        try:
            body = response.json()
        except ValueError as exc:
            logger.warning(
                "music_queue_reader.invalid_json community_id=%d error=%s", community_id, exc
            )
            return _stale_or_empty(community_id, cache_entry)

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            logger.warning("music_queue_reader.malformed_payload community_id=%d", community_id)
            return _stale_or_empty(community_id, cache_entry)

        snapshot = _snapshot_from_dto(community_id, data)
        self._cache[community_id] = (now, snapshot)
        logger.debug(
            "music_queue_reader.fetched community_id=%d has_now_playing=%s upcoming=%d",
            community_id,
            snapshot.now_playing is not None,
            len(snapshot.upcoming),
        )
        return snapshot

    async def advance(self, community_id: int, item_id: int) -> tuple[bool, QueueSnapshot | None]:
        """POST advance for `item_id`; refresh this community's cache from the response.

        Returns `(advanced, snapshot)` -- `advanced=False` (only advances
        if `item_id` is still the current playing item, per hub-api's own
        contract) still carries a fresh `snapshot` (the response's `data`
        reflects whatever is actually playing now). `snapshot=None` only
        on a total failure (unreachable/non-2xx/malformed) -- never
        raises.
        """
        if not self.connected or self._client is None:
            logger.debug(
                "music_queue_reader.advance_skipped community_id=%d reason=not_connected",
                community_id,
            )
            return False, None

        try:
            response = await self._client.post(
                _ADVANCE_PATH,
                json={"community_id": community_id, "item_id": item_id},
                headers={"X-Service-Key": self.service_api_key},
            )
        except httpx.HTTPError as exc:
            logger.warning(
                "music_queue_reader.advance_unreachable community_id=%d error=%s",
                community_id,
                exc,
            )
            return False, None

        if response.status_code >= 400:
            logger.warning(
                "music_queue_reader.advance_rejected community_id=%d status=%d",
                community_id,
                response.status_code,
            )
            return False, None

        try:
            body = response.json()
        except ValueError as exc:
            logger.warning(
                "music_queue_reader.advance_invalid_json community_id=%d error=%s",
                community_id,
                exc,
            )
            return False, None

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            logger.warning(
                "music_queue_reader.advance_malformed_payload community_id=%d", community_id
            )
            return False, None

        snapshot = _snapshot_from_dto(community_id, data)
        self._cache[community_id] = (time.monotonic(), snapshot)
        advanced = bool(body.get("advanced", False)) if isinstance(body, dict) else False
        logger.debug(
            "music_queue_reader.advanced community_id=%d item_id=%d advanced=%s",
            community_id,
            item_id,
            advanced,
        )
        return advanced, snapshot
