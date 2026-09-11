"""Live-stream (HLS) browser-source surface: player page + polled status proxy.

    GET /overlay/<community>/live          -- render the HLS.js player page
    GET /overlay/<community>/live/status   -- JSON proxy: running-pipeline listing

`core/svc_streaming` (issue #287 S7) exposes `GET {STREAMING_URL}/live/
<community_id>` -- a cluster-internal listing of that community's running
HLS pipelines. The browser can't reach `STREAMING_URL` (internal-only
Service DNS), so this module's own `/live/status` endpoint proxies that
call server-side and rewrites each pipeline's playback URL onto
`PUBLIC_STREAMING_URL` (the externally-reachable host) before handing it to
the page's poll loop -- the same "server holds the internal URL, browser
gets a public one" shape `services/queue_reader.py` + `blueprints/music.py`'s
`/music/queue` already established for hub-api.

`STREAMING_URL`/`PUBLIC_STREAMING_URL` are read directly from the process
environment rather than through `config.py`'s `Config` dataclass -- this
task's owned file set is `services/render.py` + `blueprints/*.py` + tests
only (svc-streaming chunk S7's scope note), not `config.py`; folding these
into `Config` is a natural follow-up for whoever owns that file next.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from quart import Blueprint, current_app, jsonify

from services.presentation_config_service import get_theme_config
from services.render import render_live
from services.surfaces import is_valid_community, resolve_community_id

logger = logging.getLogger(__name__)

live_bp = Blueprint("live_stream", __name__, url_prefix="/overlay")

#: Cluster-internal svc-streaming base URL -- server-side proxy calls only,
#: never reaches the browser. Default matches the Helm Service DNS name for
#: `core/svc_streaming` (port 8208, that crate's `README.md` Ports table).
_STREAMING_URL_ENV = "STREAMING_URL"
_DEFAULT_STREAMING_URL = "http://svc-streaming:8208"

#: Externally-reachable svc-streaming base URL -- embedded into the
#: rendered page / status JSON for the browser's own HLS.js fetches. No
#: default: unset degrades to "offline" (never a broken/empty player src)
#: rather than guessing a public hostname.
_PUBLIC_STREAMING_URL_ENV = "PUBLIC_STREAMING_URL"

_TIMEOUT_SECONDS = 3.0

_UNAVAILABLE_STATUS: dict[str, Any] = {"live": False, "pipelines": []}


def _dal() -> tuple[Any, Any]:
    """Return `(async_dal, dal)` from app config -- set at startup, see `app.py`."""
    return current_app.config["async_dal"], current_app.config["dal"]


def _streaming_url() -> str:
    return os.environ.get(_STREAMING_URL_ENV, _DEFAULT_STREAMING_URL)


def _public_streaming_url() -> str:
    return os.environ.get(_PUBLIC_STREAMING_URL_ENV, "")


def _normalize_pipelines(raw_pipelines: list[Any]) -> list[dict[str, Any]]:
    """Validate + rewrite svc-streaming's `pipelines` DTO onto the public base URL.

    Skips (never raises on) a malformed entry -- an explicit wire schema,
    not a pass-through of whatever svc-streaming happens to send
    (security.md Output Validation).
    """
    public_base = _public_streaming_url()
    normalized: list[dict[str, Any]] = []
    for entry in raw_pipelines:
        if not isinstance(entry, dict):
            continue
        relative_url = entry.get("url")
        if not isinstance(relative_url, str) or not relative_url:
            continue
        public_url = f"{public_base}{relative_url}" if public_base else relative_url
        normalized.append(
            {
                "id": entry.get("id"),
                "profile": entry.get("profile"),
                "url": public_url,
                "started_at": entry.get("started_at"),
            }
        )
    return normalized


async def _fetch_live_status(community_id: int) -> dict[str, Any]:
    """`GET {STREAMING_URL}/live/<community_id>`, normalized to `{live, pipelines}`.

    Never raises: an unreachable/non-2xx/malformed svc-streaming response
    degrades to `{"live": False, "pipelines": []}` -- the same "proxy never
    500s" posture `services/queue_reader.py` established for hub-api.
    """
    url = f"{_streaming_url()}/live/{community_id}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        logger.warning("live_stream.unreachable community_id=%d error=%s", community_id, exc)
        return dict(_UNAVAILABLE_STATUS)

    if response.status_code != 200:
        logger.warning(
            "live_stream.rejected community_id=%d status=%d", community_id, response.status_code
        )
        return dict(_UNAVAILABLE_STATUS)

    try:
        body = response.json()
    except ValueError as exc:
        logger.warning("live_stream.invalid_json community_id=%d error=%s", community_id, exc)
        return dict(_UNAVAILABLE_STATUS)

    raw_pipelines = body.get("pipelines") if isinstance(body, dict) else None
    if not isinstance(raw_pipelines, list):
        logger.warning("live_stream.malformed_payload community_id=%d", community_id)
        return dict(_UNAVAILABLE_STATUS)

    pipelines = _normalize_pipelines(raw_pipelines)
    return {"live": bool(pipelines), "pipelines": pipelines}


@live_bp.route("/<community>/live")
async def render_live_surface(community: str) -> Any:
    """Render the HLS.js live-stream player page for `community`."""
    if not is_valid_community(community):
        return "invalid community", 400

    async_dal, dal = _dal()
    theme = await get_theme_config(async_dal, dal, community=community)

    community_id = resolve_community_id(community)
    status = (
        await _fetch_live_status(community_id)
        if community_id is not None
        else dict(_UNAVAILABLE_STATUS)
    )
    pipelines = status["pipelines"]
    first = pipelines[0] if pipelines else None

    body = render_live(
        community,
        live=bool(status["live"] and first),
        master_url=first["url"] if first else None,
        primary_color=theme.primary_color,
        secondary_color=theme.secondary_color,
        font_family=theme.font_family,
    )
    return body, 200, {"Content-Type": "text/html; charset=utf-8"}


@live_bp.route("/<community>/live/status")
async def get_live_status(community: str) -> Any:
    """JSON poll endpoint (client polls this every 10s) -- `{live, pipelines}`."""
    if not is_valid_community(community):
        return jsonify({"error": "invalid community"}), 400

    community_id = resolve_community_id(community)
    if community_id is None:
        return jsonify(dict(_UNAVAILABLE_STATUS))

    return jsonify(await _fetch_live_status(community_id))


BLUEPRINTS: list[Blueprint] = [live_bp]
