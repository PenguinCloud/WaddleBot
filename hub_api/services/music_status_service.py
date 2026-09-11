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

Never logs, prints, or returns the client secret or bearer token itself --
only a short, secret-free cause string on failure.
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

_TOKEN_URL = "https://accounts.spotify.com/api/token"  # noqa: S105 - URL, not a credential
_TIMEOUT_SECONDS = 10.0
_TOKEN_FILE = Path.home() / ".spotify.token"

#: Task requirement: "cached (>=60s)" -- avoids a real network round-trip to
#: Spotify on every `!sr status` invocation.
_CACHE_TTL_SECONDS = 60.0


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
