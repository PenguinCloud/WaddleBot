"""Shared surface-name constants and path-param validation.

Single source of truth for which browser-source surfaces this scaffold
actually knows how to render/push to -- `blueprints/overlay.py` (live/push,
generic across every surface) and `blueprints/music.py` (the Music Station,
`music` specifically) both import from here rather than each declaring
their own copy.
"""

from __future__ import annotations

import re

#: Core overlay surfaces (task scope) plus the Music Station. A future
#: activated bundle's own presentation-component surface name
#: (music-station-design.md §8.2 item 3) would extend this set --
#: out of scope here (no `presentation`-stage bundle poll/reconcile wired
#: yet, see this service's own pre-existing TODOs).
KNOWN_SURFACES: frozenset[str] = frozenset({"full_screen", "media", "crawler", "music"})

#: Loose slug validation for the `community` path param -- security.md
#: Input Validation (server-side validation on client input).
SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_valid_community(community: str) -> bool:
    """True if `community` is a syntactically valid community slug."""
    return bool(SLUG_RE.match(community))


def resolve_community_id(community: str) -> int | None:
    """Resolve the URL path's `community` segment to a numeric `community_id`.

    Every FK this service and hub-api's internal music-queue contract both
    key off (`overlay_surfaces.community_id`/`presentation_config
    .community_id`/hub-api's `GET .../music/queue?community_id=<int>`) is
    an integer -- the URL path segment itself stays a generic slug-
    validated string (`SLUG_RE`, same OBS-browser-source-URL convention
    `browser_source_core_module` already uses). A non-numeric slug has no
    resolution path today: this service owns no `communities` table
    (`backend-database.md` Per-Service Database Accounts -- it isn't
    `communities`' service) and the hub-api contract this module calls
    against has no slug->id lookup endpoint, so `None` is returned and
    every caller treats that the same way `presentation_config_service
    ._community_id` already did for its own pre-existing config lookups:
    apply a documented fallback, never raise or 500.
    """
    try:
        return int(community)
    except ValueError:
        return None
