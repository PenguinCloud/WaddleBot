"""Provider-agnostic resolve()/search() contract for real YouTube/Spotify music resolvers.

This is the seam the music-station queue (`services/music_service.py` and
friends) calls through -- callers never import `youtube`/`spotify` directly.
`resolve()` auto-detects the provider from a URL (youtube.com/youtu.be ->
youtube, open.spotify.com -> spotify). For bare search text (e.g. a chat
`!songrequest` query with no URL) an explicit `provider` argument wins when
given; otherwise the default is YouTube-first (falling back to Spotify on
`ProviderUnavailable`/`TrackNotFound`) when `YOUTUBE_API_KEY` is configured
-- YouTube gives a playable full-length result for the OBS overlay -- else
Spotify only, unchanged from prior behavior. Every resolver call is real
network I/O against the live YouTube Data API v3 / Spotify Web API -- there
is no stub/fake path; the only non-network outcome is `ProviderUnavailable`
when that provider's credentials are absent or unusable, which callers are
expected to catch and degrade on (e.g. "Spotify isn't configured for this
community" instead of a 500).

`community_music_settings.default_provider` (`services/schema.py`) is a
per-community override for this same bare-text decision, but nothing reads
it yet -- neither this module nor `services/community_music_queue_service.
py::_resolve_track()` (which doesn't receive `community_id` today). Until
that's wired through, the caller-supplied `provider` kwarg below is the
only per-call override; the module-level default here (env-var-driven, not
per-community) applies otherwise. See `resolve()`'s own DEBUG logging for
which branch fired on a given call.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from services.music_providers import spotify, youtube
from services.music_providers.errors import ProviderUnavailable, TrackNotFound
from services.music_providers.track import Track

__all__ = ["ProviderUnavailable", "Track", "TrackNotFound", "resolve", "search"]

logger = logging.getLogger(__name__)

_KNOWN_PROVIDERS = frozenset({"youtube", "spotify"})


def _detect_provider(url_or_query: str) -> str | None:
    """Sniff a provider from a URL's host; returns None for bare search text."""
    parsed = urlparse(url_or_query)
    host = (parsed.netloc or "").lower()
    if not host and "://" not in url_or_query:
        # No scheme (e.g. "youtu.be/xyz" pasted without "https://") --
        # urlparse can't find a netloc without one; re-parse as
        # scheme-relative so the same host logic below still applies.
        parsed = urlparse(f"//{url_or_query}")
        host = (parsed.netloc or "").lower()

    if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        return "youtube"
    if host == "spotify.com" or host.endswith(".spotify.com"):
        return "spotify"
    return None


async def _resolve_via(provider: str, url_or_query: str) -> Track:
    """Dispatch to the named provider's own `resolve()` -- `provider` already validated."""
    if provider == "youtube":
        return await youtube.resolve(url_or_query)
    return await spotify.resolve(url_or_query)


async def resolve(url_or_query: str, provider: str | None = None) -> Track:
    """Resolve one URL or bare query to a single `Track`.

    Provider is auto-detected from the URL host when possible. For bare
    search text (host detection fails): the caller-supplied `provider`
    wins when given; otherwise -- see module docstring -- YouTube is tried
    first when `YOUTUBE_API_KEY` is configured (falling back to Spotify on
    `ProviderUnavailable`/`TrackNotFound`), else Spotify only. Raises
    `ProviderUnavailable` if the resolved provider has no usable
    credentials, `TrackNotFound` if the provider found nothing (or an
    unknown `provider` was given explicitly).
    """
    detected_provider = _detect_provider(url_or_query)
    if detected_provider is not None:
        logger.debug(
            "music_providers.resolve provider=%s reason=url_host_detected", detected_provider
        )
        return await _resolve_via(detected_provider, url_or_query)

    if provider is not None:
        if provider not in _KNOWN_PROVIDERS:
            raise TrackNotFound(url_or_query)
        logger.debug("music_providers.resolve provider=%s reason=explicit_provider_arg", provider)
        return await _resolve_via(provider, url_or_query)

    # Bare text, no explicit provider -- see module docstring for why
    # `community_music_settings.default_provider` isn't consulted here.
    if youtube.youtube_credentials_configured():
        logger.debug(
            "music_providers.resolve provider=youtube reason=bare_text_default_youtube_key_set"
        )
        try:
            return await youtube.resolve(url_or_query)
        except (ProviderUnavailable, TrackNotFound) as exc:
            logger.debug(
                "music_providers.resolve provider=spotify "
                "reason=bare_text_youtube_fallback youtube_error=%s",
                type(exc).__name__,
            )
            return await spotify.resolve(url_or_query)

    logger.debug("music_providers.resolve provider=spotify reason=bare_text_default_no_youtube_key")
    return await spotify.resolve(url_or_query)


async def search(query: str, provider: str) -> list[Track]:
    """Search a specific provider for `query`, returning every match found.

    Raises `ProviderUnavailable` if `provider` has no usable credentials,
    `TrackNotFound` if the search returns zero results.
    """
    if provider not in _KNOWN_PROVIDERS:
        raise TrackNotFound(query)

    if provider == "youtube":
        return await youtube.search(query)
    return await spotify.search(query)
