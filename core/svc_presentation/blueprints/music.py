"""Music Station: the browser-source player page + its JSON queue-state read/advance.

    GET  /overlay/<community>/music          -- render the player page
    GET  /overlay/<community>/music/queue    -- JSON now-playing + upcoming queue
    POST /overlay/<community>/music/advance  -- advance the queue past a finished track

The queue JSON is read through hub-api's internal music-queue endpoint
(`services/queue_reader.py`) -- see that module's own docstring for the
DTO mapping decision and why this no longer reads Valkey directly.
"""

from __future__ import annotations

from typing import Any

from quart import Blueprint, current_app, jsonify, request

from services.presentation_config_service import get_theme_config, is_surface_enabled
from services.queue_reader import (
    MusicQueueReader,
    PlaybackState,
    QueueSnapshot,
    QueueTrack,
    RequestedBy,
)
from services.render import render_music
from services.surfaces import is_valid_community, resolve_community_id

music_bp = Blueprint("music_overlay", __name__, url_prefix="/overlay")


def _dal() -> tuple[Any, Any]:
    """Return `(async_dal, dal)` from app config -- set at startup, see `app.py`."""
    return current_app.config["async_dal"], current_app.config["dal"]


def _queue_reader() -> MusicQueueReader:
    """Return this process's `MusicQueueReader` -- set at startup, see `app.py`."""
    return current_app.config["MUSIC_QUEUE_READER"]  # type: ignore[no-any-return]


def _requested_by_dict(requested_by: RequestedBy | None) -> dict[str, str] | None:
    if requested_by is None:
        return None
    return {"display_name": requested_by.display_name, "platform": requested_by.platform}


def _track_dict(track: QueueTrack) -> dict[str, Any]:
    """Explicit wire-schema for one queue track (security.md Output Validation).

    Named fields only -- never a raw `dataclasses.asdict()`/`**__dict__`
    dump, so `QueueTrack` can grow internal-only fields later without
    silently widening this response.
    """
    return {
        "queue_id": track.queue_id,
        "position": track.position,
        "status": track.status,
        "provider": track.provider,
        "external_id": track.external_id,
        "name": track.name,
        "artist": track.artist,
        "album_art_url": track.album_art_url,
        "duration_ms": track.duration_ms,
        "uri": track.uri,
        "eta_seconds": track.eta_seconds,
        "started_at": track.started_at,
        "requested_by": _requested_by_dict(track.requested_by),
    }


def _playback_dict(playback: PlaybackState) -> dict[str, Any]:
    """Explicit wire-schema for `playback` (security.md Output Validation) -- named fields only."""
    return {
        "paused": playback.paused,
        "paused_since": playback.paused_since,
        "position_ms": playback.position_ms,
    }


#: Same default `_snapshot_payload` renders for a never-paused snapshot -- reused by
#: `_unavailable_payload` so every response carries the same `playback` shape.
_DEFAULT_PLAYBACK_DICT: dict[str, Any] = {
    "paused": False,
    "paused_since": None,
    "position_ms": None,
}


def _snapshot_payload(community: str, snapshot: QueueSnapshot) -> dict[str, Any]:
    """Wire payload for a successful queue read -- `available: true`, no reason."""
    return {
        "community": community,
        "now_playing": _track_dict(snapshot.now_playing) if snapshot.now_playing else None,
        "upcoming": [_track_dict(t) for t in snapshot.upcoming],
        "stale": snapshot.stale,
        "available": True,
        "unavailable_reason": None,
        "playback": _playback_dict(snapshot.playback),
    }


def _unavailable_payload(community: str, *, reason: str) -> dict[str, Any]:
    """Wire payload when the queue can't be resolved at all (config/community-resolution gap).

    Still 200 with an honestly-empty queue, never a 500 -- the overlay
    page distinguishes this from "no tracks queued" via `available`/
    `unavailable_reason` (`services/render.py`'s player JS).
    """
    return {
        "community": community,
        "now_playing": None,
        "upcoming": [],
        "stale": False,
        "available": False,
        "unavailable_reason": reason,
        "playback": _DEFAULT_PLAYBACK_DICT,
    }


@music_bp.route("/<community>/music")
async def render_music_surface(community: str) -> Any:
    """Render the Music Station browser-source player page."""
    if not is_valid_community(community):
        return "invalid community", 400

    async_dal, dal = _dal()
    if not await is_surface_enabled(async_dal, dal, community=community, surface="music"):
        return "surface disabled for this community", 404
    theme = await get_theme_config(async_dal, dal, community=community)

    body = render_music(
        community,
        primary_color=theme.primary_color,
        secondary_color=theme.secondary_color,
        font_family=theme.font_family,
    )
    return body, 200, {"Content-Type": "text/html; charset=utf-8"}


@music_bp.route("/<community>/music/queue")
async def get_queue(community: str) -> Any:
    """Return `{now_playing, upcoming, ...}` for `community`'s music queue, JSON.

    Never a traceback: a missing `SERVICE_API_KEY` or an unresolvable
    (non-numeric) `community` both return `available: false` with a
    specific `unavailable_reason` instead of calling hub-api at all; a
    reachable-but-failing hub-api is handled inside `MusicQueueReader`
    itself (stale-cache-or-empty, never raises).
    """
    if not is_valid_community(community):
        return jsonify({"error": "invalid community"}), 400

    cfg = current_app.config["APP_CONFIG"]
    if not cfg.service_api_key:
        return jsonify(_unavailable_payload(community, reason="service_key_not_configured"))

    community_id = resolve_community_id(community)
    if community_id is None:
        return jsonify(_unavailable_payload(community, reason="community_not_resolvable"))

    snapshot = await _queue_reader().get_queue(community_id)
    return jsonify(_snapshot_payload(community, snapshot))


@music_bp.route("/<community>/music/advance", methods=["POST"])
async def advance_queue(community: str) -> Any:
    """Advance the queue past `item_id`, proxying to hub-api's internal advance endpoint.

    The `X-Service-Key` shared secret never reaches the browser -- this
    server-side proxy is the only thing that ever attaches it, matching
    the push endpoint's own posture (`blueprints/overlay.py::push`) for
    keeping service credentials out of client-facing responses.
    """
    if not is_valid_community(community):
        return jsonify({"error": "invalid community"}), 400

    async_dal, dal = _dal()
    if not await is_surface_enabled(async_dal, dal, community=community, surface="music"):
        return jsonify({"error": "surface disabled for this community"}), 404

    cfg = current_app.config["APP_CONFIG"]
    if not cfg.service_api_key:
        return jsonify({"error": "service key not configured"}), 503

    community_id = resolve_community_id(community)
    if community_id is None:
        return jsonify({"error": "community not resolvable"}), 400

    body = await request.get_json(force=True, silent=True)
    item_id = body.get("item_id") if isinstance(body, dict) else None
    if not isinstance(item_id, int) or isinstance(item_id, bool):
        return jsonify({"error": "item_id (int) is required"}), 400

    advanced, snapshot = await _queue_reader().advance(community_id, item_id)
    if snapshot is None:
        return jsonify({"error": "hub-api unavailable"}), 502

    payload = _snapshot_payload(community, snapshot)
    payload["advanced"] = advanced
    return jsonify(payload)


BLUEPRINTS: list[Blueprint] = [music_bp]
