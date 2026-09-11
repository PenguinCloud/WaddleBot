"""YouTube Data API v3 OAuth helper -- refresh-token to access-token, in-process cache.

Small, deliberately-copied helper (not an import of `hub_api`) mirroring
`hub_api/services/music_providers/youtube.py`'s OAuth mode
(`_get_oauth_access_token`/`_describe_oauth_error`): `POST
https://oauth2.googleapis.com/token` with `grant_type=refresh_token`,
cache the resulting access token in-process until `expires_in - 60s`, and
support exactly one forced refresh on a caller-observed 401 -- same
semantics, same safety margin, same Google OAuth error-body shape. Copied
rather than imported because `hub_api` and `core/svc_action` are separate
deployable services with no shared runtime dependency between them (same
reasoning `bundles/discord_send_action.py`'s own module docstring gives
for not adding a new third-party SDK dependency instead of reusing
`waddle_transports` primitives already in scope) -- this module is
intentionally small enough that copying it is cheaper than introducing a
cross-service import.

Also provides `token_has_scope()`, which the `hub_api` module has no
equivalent of: `bundles/youtube_send_action.py` needs to distinguish "the
refresh token itself doesn't carry chat-send permission" (a permanent
error, unfixable without reissuing OAuth consent) from a transient/real
403 API error body, so it can surface the specific, actionable message
before ever attempting the send. `GET https://oauth2.googleapis.com/
tokeninfo?access_token=` returns the token's granted `scope` string; the
answer is cached per-access-token (a token's scopes never change during
its own lifetime) so a `tokeninfo` round trip only happens once per
access token, not once per chat message sent.

Never logs, prints, or otherwise surfaces the client secret, refresh
token, or access token value itself -- only cache hit/miss/refresh and
which error class a refresh failure falls into.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 -- URL, not a secret
_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

#: Refresh this many seconds before the OAuth access token's reported
#: expiry, to avoid a request racing an about-to-expire token -- same
#: margin as `hub_api/services/music_providers/youtube.py`'s
#: `_OAUTH_EXPIRY_SAFETY_MARGIN_SECONDS`.
_EXPIRY_SAFETY_MARGIN_SECONDS = 60

#: The OAuth scope `liveChatMessages.insert` requires.
YOUTUBE_FORCE_SSL_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


class YouTubeOAuthError(Exception):
    """Raised when a refresh-token exchange or a `tokeninfo` scope lookup fails."""


@dataclass(slots=True)
class _CachedToken:
    """In-process OAuth access-token cache entry; `expires_at` is a `time.monotonic()` deadline."""

    value: str
    expires_at: float


@dataclass(slots=True, frozen=True)
class _CacheKey:
    """Cache key for a refresh-token's access-token cache entry -- one entry per credential set."""

    client_id: str
    refresh_token: str


_token_cache: dict[_CacheKey, _CachedToken] = {}
_token_cache_lock = asyncio.Lock()
#: Access-token value -> its granted scope string, from `tokeninfo`. A
#: token's scopes never change during its own lifetime, so this never
#: needs an expiry -- a cache-cleared/refreshed access token simply gets a
#: new cache entry under its own (different) value.
_scope_cache: dict[str, str] = {}
_scope_cache_lock = asyncio.Lock()


def _describe_oauth_error(response: httpx.Response) -> str:
    """Extract Google's OAuth `error`/`error_description` from a token-endpoint failure body."""
    try:
        payload: Any = response.json()
    except ValueError:
        return "unknown error"
    if not isinstance(payload, dict):
        return "unknown error"

    error = payload.get("error")
    description = payload.get("error_description")
    if error and description:
        return f"{error}: {description}"
    if error:
        return str(error)
    return "unknown error"


async def get_access_token(
    http_client: httpx.AsyncClient,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    *,
    force_refresh: bool = False,
) -> str:
    """Return a cached or freshly-refreshed OAuth access token for `refresh_token`.

    Cached in-process (keyed on `client_id` + `refresh_token`, since a
    service may hold more than one YouTube channel's credentials) until
    `expires_in - _EXPIRY_SAFETY_MARGIN_SECONDS`; `force_refresh` bypasses
    the cache (the caller's single retry after an observed 401). Guarded
    by a lock so concurrent sends for the same credential set don't each
    mint their own token.

    Raises `YouTubeOAuthError` (message: `"youtube oauth refresh failed:
    ..."`) on a network failure, a non-200 response, or a 200 response
    missing `access_token`.
    """
    cache_key = _CacheKey(client_id=client_id, refresh_token=refresh_token)
    async with _token_cache_lock:
        cached = _token_cache.get(cache_key)
        if not force_refresh and cached is not None and cached.expires_at > time.monotonic():
            logger.debug("youtube_oauth.token_cache=hit")
            return cached.value

        logger.debug("youtube_oauth.token_cache=%s", "refresh" if force_refresh else "miss")
        try:
            response = await http_client.post(
                _OAUTH_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError as exc:
            raise YouTubeOAuthError(
                f"youtube oauth refresh failed: {type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            raise YouTubeOAuthError(
                f"youtube oauth refresh failed: HTTP {response.status_code} "
                f"{_describe_oauth_error(response)}"
            )

        payload: Any = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        expires_in = payload.get("expires_in", 3600) if isinstance(payload, dict) else 3600
        if not token:
            raise YouTubeOAuthError("youtube oauth refresh failed: response missing access_token")

        new_token = _CachedToken(
            value=str(token),
            expires_at=time.monotonic() + max(0, int(expires_in) - _EXPIRY_SAFETY_MARGIN_SECONDS),
        )
        _token_cache[cache_key] = new_token
        return new_token.value


async def token_has_scope(
    http_client: httpx.AsyncClient, access_token: str, scope: str
) -> bool:
    """True if `access_token`'s granted OAuth scopes include `scope` (space-delimited match).

    Calls `GET .../tokeninfo?access_token=...` once per distinct
    `access_token` value (result cached -- a token's scopes are fixed for
    its own lifetime) rather than once per caller. A `tokeninfo` failure
    (network error, non-200, malformed body) is treated as "scope
    unknown, not confirmed absent" and raises `YouTubeOAuthError` --
    the caller decides how to degrade, this helper never guesses.
    """
    async with _scope_cache_lock:
        cached_scope = _scope_cache.get(access_token)
        if cached_scope is not None:
            return scope in cached_scope.split()

        try:
            response = await http_client.get(
                _TOKENINFO_URL, params={"access_token": access_token}
            )
        except httpx.HTTPError as exc:
            raise YouTubeOAuthError(
                f"youtube oauth tokeninfo lookup failed: {type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            raise YouTubeOAuthError(
                f"youtube oauth tokeninfo lookup failed: HTTP {response.status_code}"
            )

        payload: Any = response.json()
        granted_scope = payload.get("scope") if isinstance(payload, dict) else None
        if not isinstance(granted_scope, str):
            raise YouTubeOAuthError(
                "youtube oauth tokeninfo lookup failed: response missing scope"
            )

        _scope_cache[access_token] = granted_scope
        return scope in granted_scope.split()
