"""Read-only lookups against svc-presentation's own `overlay_surfaces`/`presentation_config`.

Both tables (`services/schema.py::bind_presentation_tables`, migration
`073_svc_presentation_overlays.sql`) are read here to make two real
decisions at render time: whether a surface is enabled for a community
(`overlay_surfaces.enabled`), and which theme/palette to inject into the
rendered HTML (`presentation_config`). No write path exists in this PR --
provisioning rows is admin/hub-webui follow-up work, out of this task's
scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.surfaces import resolve_community_id


@dataclass(slots=True, frozen=True)
class ThemeConfig:
    """The subset of `presentation_config` that `services/render.py` injects as CSS variables."""

    primary_color: str | None
    secondary_color: str | None
    font_family: str | None


async def is_surface_enabled(async_dal: Any, dal: Any, *, community: str, surface: str) -> bool:
    """True unless an explicit `overlay_surfaces` row disables this surface for this community.

    No row at all (the common case -- no admin has touched per-community
    surface config yet) means "enabled by default", not "not found".
    """
    community_id = resolve_community_id(community)
    if community_id is None:
        return True
    rows = await async_dal.select_async(
        dal(
            (dal.overlay_surfaces.community_id == community_id)
            & (dal.overlay_surfaces.surface == surface)
        )
    )
    if not rows:
        return True
    return bool(rows.first().enabled)


async def get_theme_config(async_dal: Any, dal: Any, *, community: str) -> ThemeConfig:
    """Return this community's theme overrides, or all-`None` defaults if unset."""
    community_id = resolve_community_id(community)
    if community_id is None:
        return ThemeConfig(primary_color=None, secondary_color=None, font_family=None)
    rows = await async_dal.select_async(dal(dal.presentation_config.community_id == community_id))
    if not rows:
        return ThemeConfig(primary_color=None, secondary_color=None, font_family=None)
    row = rows.first()
    return ThemeConfig(
        primary_color=row.primary_color,
        secondary_color=row.secondary_color,
        font_family=row.font_family,
    )
