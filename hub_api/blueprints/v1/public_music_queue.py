"""v1 public (unauthenticated) Music Station queue -- backs the public queue page.

New surface alongside `blueprints/v1/community_music_queue.py`'s
`music_internal_bp` (service-key, polled by the OBS overlay player) --
this route is the same read, but for an anonymous browser tab, not a
service. Deliberately its OWN blueprint (not added to `blueprints/v1/
public.py`'s existing `public_bp`) per this port's own edit-scope
boundary; auto-discovery (`routers/_discovery.py::discover_blueprints`)
picks up this module's `BLUEPRINTS` list the same way it does every other
`blueprints/v1/*.py` module, so no router file needs editing to wire it
in.

NO auth, NO tenant middleware -- there is no JWT for an anonymous page
view, same "pre-auth surface" precedent `blueprints/v1/public.py`'s own
module docstring documents. Rate limiting is `services.rate_limiting.
install_rate_limiting()`'s existing global `before_request` hook
(installed once in `app.py::create_app()` over every registered route,
standard tier, bucketed by client IP since there's no bearer token to key
on) -- no route-local limiter reinvented here.

Never auto-advances the queue itself (`auto_advance=False` on the shared
`services.community_music_queue_service.get_live_queue_state()` read) --
a burst of public page loads must never itself drive queue state; only
the internal (service-key) GET route the overlay polls does that,
lazily, on its own schedule.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, cast

from flask_core.api_utils import error_response
from quart import Blueprint, Response, current_app, jsonify

from config import HubAPIConfig
from services import community_music_queue_service as svc
from services.errors import ApiError, not_found
from services.rate_limiting import RATE_LIMITER_CONFIG_KEY

logger = logging.getLogger(__name__)

public_music_queue_bp = Blueprint("v1_public_music_queue", __name__, url_prefix="/api/v1/public")


def _dal() -> tuple[Any, Any]:
    """Return `(async_dal, dal)` from app config -- tables already bound at startup."""
    return current_app.config["async_dal"], current_app.config["dal"]


def _err(exc: ApiError) -> tuple[dict[str, object], int]:
    return cast(
        tuple[dict[str, object], int], error_response(exc.message, exc.status_code, exc.code)
    )


#: `app.config` key a lazily-opened raw Valkey client is cached under --
#: same rationale/duplicated helper as `blueprints/v1/community_music_
#: queue.py::_redis_client()` (see that module's own docstring); this
#: blueprint is deliberately independent (module docstring: own edit-scope
#: boundary), so the helper is duplicated rather than imported.
MUSIC_PLAYBACK_REDIS_CONFIG_KEY = "music_playback_redis"


def _redis_client() -> Any:
    """Resolve the async Valkey/Redis client used for `music:playback:*` state (gh-315).

    See `blueprints/v1/community_music_queue.py::_redis_client()`'s own
    docstring for the full reuse-vs-lazy-open rationale -- identical
    logic, duplicated per this module's own independence precedent.
    """
    limiter = current_app.config.get(RATE_LIMITER_CONFIG_KEY)
    existing = getattr(limiter, "_redis", None) if limiter is not None else None
    if existing is not None:
        return existing

    cached = current_app.config.get(MUSIC_PLAYBACK_REDIS_CONFIG_KEY)
    if cached is not None:
        return cached

    import redis.asyncio as redis_asyncio

    cfg = cast(HubAPIConfig, current_app.config["HUB_API_CONFIG"])
    client = redis_asyncio.from_url(
        cfg.valkey_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    current_app.config[MUSIC_PLAYBACK_REDIS_CONFIG_KEY] = client
    return client


@dataclass(slots=True, frozen=True)
class PublicCommunitySummaryDTO:
    """Minimal community identity for the public queue page header."""

    id: int
    name: str


@dataclass(slots=True, frozen=True)
class PublicPlaybackSnapshotDTO:
    """`data.playback` wire shape (gh-315) -- see `community_music_queue.PlaybackSnapshotDTO`.

    Duplicated (not imported) per this module's own independence
    precedent -- identical 3-field shape.
    """

    paused: bool
    paused_since: str | None
    position_ms: int | None


@dataclass(slots=True, frozen=True)
class PublicQueueResponse:
    """`{status, data, meta}`-enveloped data payload for the public queue read."""

    community: PublicCommunitySummaryDTO
    now_playing: svc.LiveQueueItemDTO | None
    queue: list[svc.LiveQueueItemDTO]
    playback: PublicPlaybackSnapshotDTO


@public_music_queue_bp.route("/communities/<int:community_id>/music-station/queue", methods=["GET"])
async def get_public_queue(community_id: int) -> Any:
    """Unauthenticated, rate-limited read of one community's live Music Station queue.

    `community_id` must resolve to an existing, active, non-deleted,
    PUBLIC community (`communities.is_public`) -- a private/inactive/
    deleted/unknown community all collapse to the same 404, never leaking
    which case applies. `Cache-Control: no-store` -- this is live queue
    state, never a cacheable response.
    """
    async_dal, dal = _dal()
    try:
        community_row = (
            dal(
                (dal.communities.id == community_id)
                & (dal.communities.is_active == True)  # noqa: E712 - pydal idiom
                & (dal.communities.deleted_at == None)  # noqa: E711 - pydal idiom
                & (dal.communities.is_public == True)  # noqa: E712 - pydal idiom
            )
            .select(dal.communities.id, dal.communities.name, dal.communities.display_name)
            .first()
        )
        if community_row is None:
            return _err(not_found("Community not found"))

        snapshot = await svc.get_live_queue_state(
            async_dal, dal, _redis_client(), community_id=community_id, auto_advance=False
        )
    except ApiError as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001 - last-resort 500 must still be JSON, never an empty body
        logger.exception("get_public_queue.unhandled_error", extra={"community_id": community_id})
        return error_response(f"Internal error: {exc}", 500, "INTERNAL_ERROR")

    payload = PublicQueueResponse(
        community=PublicCommunitySummaryDTO(
            id=int(community_row.id),
            name=community_row.display_name or community_row.name or "",
        ),
        now_playing=snapshot.now_playing,
        queue=snapshot.queue,
        playback=PublicPlaybackSnapshotDTO(
            paused=snapshot.paused,
            paused_since=snapshot.paused_since,
            position_ms=snapshot.position_ms,
        ),
    )
    response: Response = jsonify(
        {"status": "success", "data": asdict(payload), "meta": {"version": 1}}
    )
    response.headers["Cache-Control"] = "no-store"
    return response, 200


BLUEPRINTS: list[Blueprint] = [public_music_queue_bp]
