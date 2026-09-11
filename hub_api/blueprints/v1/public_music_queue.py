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

from services import community_music_queue_service as svc
from services.errors import ApiError, not_found

logger = logging.getLogger(__name__)

public_music_queue_bp = Blueprint("v1_public_music_queue", __name__, url_prefix="/api/v1/public")


def _dal() -> tuple[Any, Any]:
    """Return `(async_dal, dal)` from app config -- tables already bound at startup."""
    return current_app.config["async_dal"], current_app.config["dal"]


def _err(exc: ApiError) -> tuple[dict[str, object], int]:
    return cast(
        tuple[dict[str, object], int], error_response(exc.message, exc.status_code, exc.code)
    )


@dataclass(slots=True, frozen=True)
class PublicCommunitySummaryDTO:
    """Minimal community identity for the public queue page header."""

    id: int
    name: str


@dataclass(slots=True, frozen=True)
class PublicQueueResponse:
    """`{status, data, meta}`-enveloped data payload for the public queue read."""

    community: PublicCommunitySummaryDTO
    now_playing: svc.LiveQueueItemDTO | None
    queue: list[svc.LiveQueueItemDTO]


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

        now_playing, queue, _advanced = await svc.get_live_queue_state(
            async_dal, dal, community_id=community_id, auto_advance=False
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
        now_playing=now_playing,
        queue=queue,
    )
    response: Response = jsonify(
        {"status": "success", "data": asdict(payload), "meta": {"version": 1}}
    )
    response.headers["Cache-Control"] = "no-store"
    return response, 200


BLUEPRINTS: list[Blueprint] = [public_music_queue_bp]
