"""Music Station provider-health probe -- backs `GET /api/v1/internal/music/status`.

Self-contained Spotify client-credentials token probe, deliberately NOT
reusing `services.music_providers.spotify`'s private `_get_bearer_token()`:
this task's edit scope is limited to `blueprints/v1/community_music_queue.py`
+ `services/community_music_queue_service.py` (+ new helper files), so
`spotify.py` stays untouched. That module also collapses every failure mode
(bad credentials, network error, 5xx) into a single `ProviderUnavailable`,
losing the specific-cause detail `!sr status` needs to tell a community admin
"credentials not configured" apart from "Spotify rejected the token (401)".
This module re-derives the same client-credentials flow independently, with
its own >=60s in-process cache, entirely separate from that module's cache.

`check_youtube_health()` probes YouTube alongside Spotify: `youtube_credentials_
source()` first (issue #320 -- community connection, then env, presence-only,
no network I/O), then -- unless `"none"` -- one cheap `videos.list?part=id`
call against a known-good video id, reusing that module's own credential
resolution/OAuth-token machinery (`_resolve_auth()`/`_get_oauth_access_token()`)
rather than duplicating the non-trivial OAuth refresh-token exchange. Unlike the
Spotify probe above, the status-code -> cause mapping IS this module's own --
the same rationale as the Spotify probe: `youtube.py`'s own `_parse_data_api_
response()` collapses 400/401/429/5xx into one generic `ProviderUnavailable(
"youtube")`, losing the "(401)" detail `!sr status` needs. Also >=60s
in-process cache, separate from both the Spotify cache above and `youtube.py`'s
own OAuth-token/community-auth caches -- keyed by `community_id` (`None` for the
env-only default every pre-issue-#320 caller uses) so one community's probe
result can never leak into another's `!sr status` response.

`check_youtube_health()`'s optional `db`/`community_id` kwargs (issue #320) are
plumbing for a future caller to pass a specific community's context through;
today's only caller (`blueprints/v1/community_music_queue.py`'s
`_internal_music_status` handler) still calls it with neither, which preserves
its pre-issue-#320 env-only behavior exactly.

Never logs, prints, or returns the client secret, API key, or bearer token
itself -- only a short, secret-free cause string on failure.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from services.music_providers import youtube as youtube_provider
from services.music_providers.errors import ProviderUnavailable

_TOKEN_URL = "https://accounts.spotify.com/api/token"  # noqa: S105 - URL, not a credential
_TIMEOUT_SECONDS = 10.0
_TOKEN_FILE = Path.home() / ".spotify.token"

#: Task requirement: "cached (>=60s)" -- avoids a real network round-trip to
#: Spotify/YouTube on every `!sr status` invocation.
_CACHE_TTL_SECONDS = 60.0

#: A stable, always-public video id (Rick Astley -- "Never Gonna Give You
#: Up") -- exists for as long as YouTube itself has, so `_probe_youtube()`'s
#: `videos.list?part=id` call fails only on a real credentials/quota/network
#: problem, never on the probe video going private/deleted.
_YOUTUBE_PROBE_VIDEO_ID = "dQw4w9WgXcQ"


@dataclass(slots=True, frozen=True)
class ProviderHealth:
    """One Spotify provider-health probe result -- `cause` is `None` iff `healthy`."""

    healthy: bool
    cause: str | None


@dataclass(slots=True)
class _CachedHealth:
    """In-process cache entry; `checked_at` is a `time.monotonic()` timestamp."""

    result: ProviderHealth
    checked_at: float


_health_cache: _CachedHealth | None = None
_health_lock = asyncio.Lock()


@dataclass(slots=True, frozen=True)
class YoutubeHealth:
    """One YouTube provider-health probe result.

    `state` is one of `"enabled"`/`"not_configured"`/`"error"` (unlike
    Spotify's plain `healthy: bool`, YouTube has a real third state -- no
    credentials configured at all, distinct from configured-but-failing)
    -- `cause` is `None` iff `state == "enabled"`. `source` (issue #320) is
    which credential mode is actually in use -- `"community"`/`"env"`/
    `"api_key"`/`"none"`, see `services.music_providers.youtube.
    youtube_credentials_source()`; `"none"` iff `state == "not_configured"`.
    """

    state: str
    cause: str | None
    source: str


@dataclass(slots=True)
class _CachedYoutubeHealth:
    """`check_youtube_health()` cache entry; `checked_at` is a `time.monotonic()` timestamp."""

    result: YoutubeHealth
    checked_at: float


#: Community id -> cached probe result; `None` is the env-only-probe slot (issue
#: #320) -- keyed so one community's result can never leak into another's.
_youtube_health_cache: dict[int | None, _CachedYoutubeHealth] = {}
_youtube_health_lock = asyncio.Lock()


def _load_credentials() -> tuple[str, str] | None:
    """Resolve `(client_id, client_secret)` from env or `~/.spotify.token` -- `None` if absent.

    Mirrors `services.music_providers.spotify._load_credentials()` --
    duplicated rather than imported, see module docstring for why.
    """
    env_id = os.getenv("SPOTIFY_CLIENT_ID")
    env_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if env_id and env_secret:
        return env_id, env_secret

    if not _TOKEN_FILE.exists():
        return None
    try:
        lines = _TOKEN_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None

    file_id, file_secret = lines[0].strip(), lines[1].strip()
    if not file_id or not file_secret:
        return None
    return file_id, file_secret


async def _probe_spotify(http_client: httpx.AsyncClient) -> ProviderHealth:
    """One real client-credentials token POST against Spotify; never raises."""
    credentials = _load_credentials()
    if credentials is None:
        return ProviderHealth(healthy=False, cause="spotify credentials not configured")
    client_id, client_secret = credentials

    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    try:
        response = await http_client.post(
            _TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return ProviderHealth(
            healthy=False, cause=f"spotify oauth unreachable: {type(exc).__name__}"
        )

    if response.status_code in (400, 401, 403):
        return ProviderHealth(
            healthy=False, cause=f"spotify oauth token didn't work ({response.status_code})"
        )
    if response.status_code >= 500:
        return ProviderHealth(
            healthy=False, cause=f"spotify oauth service error ({response.status_code})"
        )
    if response.status_code >= 400:
        return ProviderHealth(
            healthy=False, cause=f"spotify oauth rejected request ({response.status_code})"
        )

    payload: Any = response.json() if response.content else {}
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not token:
        return ProviderHealth(healthy=False, cause="spotify oauth response missing access_token")

    return ProviderHealth(healthy=True, cause=None)


async def check_spotify_health() -> ProviderHealth:
    """Return cached (>=60s) or freshly-probed Spotify client-credentials health."""
    global _health_cache
    async with _health_lock:
        if (
            _health_cache is not None
            and (time.monotonic() - _health_cache.checked_at) < _CACHE_TTL_SECONDS
        ):
            return _health_cache.result

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            result = await _probe_spotify(client)
        _health_cache = _CachedHealth(result=result, checked_at=time.monotonic())
        return result


async def _probe_youtube(
    http_client: httpx.AsyncClient, db: Any = None, community_id: int | None = None
) -> YoutubeHealth:
    """One real `videos.list?part=id` probe against YouTube; never raises.

    `db`/`community_id` (issue #320): passed straight through to `youtube_
    credentials_source()`/`_resolve_auth()` so a community-connected account is
    preferred/reported the same way `resolve()`/`search()` prefer it -- both
    default `None`, which preserves the pre-issue-#320 env-only probe. Reuses
    `services.music_providers.youtube`'s own credential resolution/OAuth-token
    machinery (see module docstring for why that machinery is reused rather than
    duplicated); only the response's status-code -> cause mapping below is this
    probe's own.
    """
    source = await youtube_provider.youtube_credentials_source(db, community_id)
    if source == "none":
        return YoutubeHealth(
            state="not_configured", cause="youtube credentials not configured", source=source
        )

    try:
        auth = await youtube_provider._resolve_auth(db, community_id)  # noqa: SLF001
    except ProviderUnavailable:
        return YoutubeHealth(
            state="not_configured", cause="youtube credentials not configured", source="none"
        )

    params: dict[str, str] = {"part": "id", "id": _YOUTUBE_PROBE_VIDEO_ID}
    headers: dict[str, str] = {}
    if isinstance(auth, youtube_provider._ApiKeyAuth):  # noqa: SLF001
        params["key"] = auth.api_key
    elif isinstance(auth, youtube_provider._CommunityAuth):  # noqa: SLF001
        headers["Authorization"] = f"Bearer {auth.access_token}"
    else:
        try:
            token = await youtube_provider._get_oauth_access_token(http_client, auth)  # noqa: SLF001
        except ProviderUnavailable as exc:
            return YoutubeHealth(
                state="error",
                cause=f"youtube oauth token didn't work: {exc.provider}",
                source=source,
            )
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = await http_client.get(
            f"{youtube_provider._API_BASE}/videos",  # noqa: SLF001
            params=params,
            headers=headers,
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return YoutubeHealth(
            state="error", cause=f"youtube unreachable: {type(exc).__name__}", source=source
        )

    if response.status_code == 401:
        return YoutubeHealth(
            state="error", cause="youtube oauth token didn't work (401)", source=source
        )
    if response.status_code == 403:
        reason = youtube_provider._describe_403_reason(response)  # noqa: SLF001
        return YoutubeHealth(
            state="error", cause=f"youtube quota/access error ({reason})", source=source
        )
    if response.status_code >= 400:
        return YoutubeHealth(
            state="error", cause=f"youtube api error ({response.status_code})", source=source
        )

    return YoutubeHealth(state="enabled", cause=None, source=source)


async def check_youtube_health(db: Any = None, community_id: int | None = None) -> YoutubeHealth:
    """Return cached (>=60s) or freshly-probed YouTube health.

    `db`/`community_id` (issue #320) -- see `_probe_youtube()`'s own docstring;
    cached per `community_id` (`None` slot for the env-only default) so results
    for different communities never mix.
    """
    async with _youtube_health_lock:
        cached = _youtube_health_cache.get(community_id)
        if cached is not None and (time.monotonic() - cached.checked_at) < _CACHE_TTL_SECONDS:
            return cached.result

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            result = await _probe_youtube(client, db, community_id)
        _youtube_health_cache[community_id] = _CachedYoutubeHealth(
            result=result, checked_at=time.monotonic()
        )
        return result
