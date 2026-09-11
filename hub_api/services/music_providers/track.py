"""Normalized cross-provider Track -- the shared shape every music provider resolves into.

Kept byte-identical to the sibling music-station agent's own `Track` (same
module built independently against the same spec) so the two land in the
same queue without a translation layer between them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Track:
    """A single playable unit, normalized across music providers.

    `provider` is the resolver's own name (`"youtube"`/`"spotify"`),
    `external_id` is that provider's native id (YouTube video id, Spotify
    track id), and `url` is the canonical link back to the track on that
    provider.

    `labels` (gh-313): lowercase, de-duplicated category/tag/topic labels
    -- YouTube populates this from a second `videos.list` call
    (`services/music_providers/youtube.py::_fetch_labels`); every other
    provider (Spotify) leaves it at the default empty tuple. Used by the
    Music Station community label-allowlist gate.
    """

    provider: str
    external_id: str
    title: str
    artist: str
    duration_ms: int
    artwork_url: str | None
    url: str
    labels: tuple[str, ...] = field(default_factory=tuple)
