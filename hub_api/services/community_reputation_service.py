"""Community reputation *read* service -- score + tier visibility (gh-310).

Backs `blueprints/v1/community_reputation.py`'s two member-facing routes:
the caller's own `(community score, global score)` snapshot
(`GET .../reputation/me`) and a community's top-N reputation leaderboard
(`GET .../reputation/leaderboard`). Read-only -- SELECTs only, never a
write; reputation is written exclusively by
`core/reputation_module/services/reputation_service.py::adjust()` (the
`!rep`/`!reputation` write path) and the M3 Platform-admin group's
`services/admin_service.py::adjust_reputation()` (neither touched here).

Two tables, two different provenance:

- `community_members.reputation` -- bound via `services.schema.
  bind_auth_tables()` (the M1 binder every other service module touching
  this table already calls: `admin_service.py`, `community_loyalty.py`'s
  own test fixtures), reused here rather than a second local
  `define_table()` call, which pydal rejects outright for an
  already-bound table name.
- `reputation_global.score` -- migration `080_add_reputation_tables.sql`;
  no existing hub-api binder touches this table (`core/reputation_module`
  owns it), so `_ensure_reputation_tables()` below defines it locally,
  guarded the same `dal.tables` membership-check way
  `services/community_common.py::ensure_community_tables()` does. No
  auto `id` column -- `hub_user_id` is the real table's own PRIMARY KEY
  (`primarykey=["hub_user_id"]`, matching `bind_app_bundle_tables()`'s
  `primarykey=["app_id"]` precedent for the same "natural key, no
  surrogate id" shape).

**Known DB-grants gap (flagged, not fixed here -- out of this module's
edit scope):** migration 080's `GRANT SELECT, INSERT, UPDATE ON
reputation_global` targets `mod_core_reputation` only; no migration
grants hub-api's own scoped DB role SELECT on this table. A production
Postgres deployment enforcing those per-service grants (security.md
Per-Service Database Accounts) will see this service 42501 on its first
`reputation_global` read until that grant is added -- needs a follow-up
migration, tracked separately. Sqlite-backed tests (no grants concept)
don't catch this.

**Tier table rescale (gh-310's brief assumed a 0-1000 score range;
this system's is different -- stated per that brief's own instruction to
adjust and state it):** `core/reputation_module/config.py`'s
`Config.REPUTATION_MIN/MAX` are 300/850 (a real FICO-style band, not
0-1000), `REPUTATION_DEFAULT` 600 -- confirmed against migration 080's
`reputation_global.score INTEGER NOT NULL DEFAULT 600` column default
and `community_members.reputation`'s identical default. The brief's five
cut points (300/500/650/800/900) assume a 0-1000 scale; rescaled here via
the single affine transform mapping that scale's endpoints onto this
system's actual ones (`0 -> 300`, `1000 -> 850`): `new = 300 + old *
0.55` (`0.55 == (850 - 300) / 1000`), then rounded round-half-away-from-
zero (matching `core/reputation_module/services/reputation_service.py::
_clamp_score()`'s own rounding rule) to the nearest integer:

    300 -> 465   500 -> 575   650 -> 657.5 -> 658   800 -> 740   900 -> 795

Two pre-existing, unrelated tier tables already live in this codebase
(`core/svc_process/bundles/community_reputation_process.py`'s `!rep`
reply -- Menace/Troll/Fair/Good/Outstanding/Saint at 550/600/650/700/750
-- and `blueprints/v1/admin.py::_reputation_dto` -- Exceptional/Very
Good/Good/Fair/Poor at 800/740/670/580); neither is touched or reused by
this module (both are outside gh-310's edit scope). This module and
`community_reputation_process.py`'s `!rep` reply are the ONE new shared
table gh-310 introduces -- `test_community_reputation_service.py::
test_tier_table_matches_bundle` and `core/svc_process/tests/
test_bundles_community_reputation_process.py`'s mirrored assertion both
guard the two independent copies from drifting apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydal import Field

from services.schema import bind_auth_tables

#: FICO-style baseline every score defaults to when no row exists --
#: matches `reputation_global.score`'s own DB column default (migration
#: 080) and `community_members.reputation`'s (`bind_auth_tables()`).
_DEFAULT_SCORE = 600

#: Hard ceiling for `get_leaderboard()`'s `limit` -- matches
#: `services/pagination.py::DEFAULT_MAX_PAGE_SIZE` / `community_loyalty.
#: py::_MAX_LEADERBOARD_LIMIT`'s identical convention.
_MAX_LEADERBOARD_LIMIT = 100

#: Ascending `(exclusive_upper_bound, label)` cut points -- see module
#: docstring for the 0-1000 -> 300-850 rescale this table encodes. A
#: score strictly below the first threshold is "Newcomer"; a score at or
#: above the last threshold's bound falls through to `_TOP_TIER_LABEL`
#: ("Legend"). MUST stay byte-identical to `core/svc_process/bundles/
#: community_reputation_process.py`'s own mirrored copy -- see that
#: module's docstring and `test_tier_table_matches_bundle` below.
REPUTATION_TIERS: tuple[tuple[int, str], ...] = (
    (465, "Newcomer"),
    (575, "Regular"),
    (658, "Trusted"),
    (740, "Respected"),
    (795, "Champion"),
)
_TOP_TIER_LABEL = "Legend"


def reputation_tier(score: int) -> str:
    """Map a `community_members.reputation` / `reputation_global.score` value to a tier label.

    See module docstring for the full rescale rationale. Never raises --
    a score outside `[REPUTATION_MIN, REPUTATION_MAX]` (shouldn't happen;
    both write paths clamp before storing) still resolves to a sane tier
    at either end (`Newcomer` below the first cut, `Legend` at/above the
    last).
    """
    for threshold, label in REPUTATION_TIERS:
        if score < threshold:
            return label
    return _TOP_TIER_LABEL


@dataclass(slots=True, frozen=True)
class MyReputationDTO:
    """`GET .../reputation/me` response payload -- both scoring tiers, each with a label."""

    community_score: int
    community_tier: str
    global_score: int
    global_tier: str
    total_events: int
    last_event_at: str | None


@dataclass(slots=True, frozen=True)
class LeaderboardEntryDTO:
    """One `GET .../reputation/leaderboard` row -- display name only, no ids/emails."""

    display_name: str
    score: int
    tier: str


def _iso(value: Any) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _ensure_reputation_tables(dal: Any, *, migrate: bool = False) -> None:
    """Idempotently bind `community_members` (reused) + `reputation_global` (new, local).

    `bind_auth_tables()` no-ops after its own first call on this `dal`
    instance (see that function's docstring) -- safe to call unconditionally
    every request, matching every other service module's `_ensure_tables()`
    convention. `migrate` defaults to `False` (production: schema owned by
    `config/postgres/migrations/080_add_reputation_tables.sql`, this
    process never runs DDL); tests pass `migrate=True` against a throwaway
    `sqlite:memory`/file DAL, same convention every `bind_*` function in
    `services/schema.py` follows.
    """
    bind_auth_tables(dal, migrate=migrate)
    if "reputation_global" not in dal.tables:
        dal.define_table(
            "reputation_global",
            Field("hub_user_id", "integer", notnull=True),
            Field("score", "integer", default=_DEFAULT_SCORE),
            Field("total_events", "integer", default=0),
            Field("last_event_at", "datetime"),
            Field("created_at", "datetime"),
            Field("updated_at", "datetime"),
            primarykey=["hub_user_id"],
            migrate=migrate,
        )


async def get_my_reputation(
    async_dal: Any, dal: Any, *, community_id: int, hub_user_id: int
) -> MyReputationDTO:
    """Caller's own community + global reputation, each defaulted to 600 (baseline) if unset.

    A member never linked to a `community_members` row yet (brand new)
    looks identical to "everyone starts at 600" -- never an error, same
    convention `community_reputation_process.py`'s `!rep` reply follows.
    """
    _ensure_reputation_tables(dal)

    member_rows = await async_dal.select_async(
        dal(
            (dal.community_members.community_id == community_id)
            & (dal.community_members.user_id == str(hub_user_id))
        )
    )
    member = member_rows.first() if member_rows else None
    community_score = (
        int(member.reputation)
        if member is not None and member.reputation is not None
        else _DEFAULT_SCORE
    )

    global_rows = await async_dal.select_async(
        dal(dal.reputation_global.hub_user_id == hub_user_id)
    )
    global_row = global_rows.first() if global_rows else None
    global_score = (
        int(global_row.score)
        if global_row is not None and global_row.score is not None
        else _DEFAULT_SCORE
    )
    total_events = int(global_row.total_events) if global_row is not None else 0
    last_event_at = _iso(global_row.last_event_at) if global_row is not None else None

    return MyReputationDTO(
        community_score=community_score,
        community_tier=reputation_tier(community_score),
        global_score=global_score,
        global_tier=reputation_tier(global_score),
        total_events=total_events,
        last_event_at=last_event_at,
    )


async def get_leaderboard(
    async_dal: Any, dal: Any, *, community_id: int, limit: int = 10
) -> list[LeaderboardEntryDTO]:
    """Top `limit` community members by `reputation`, highest first, active members only.

    Display-name + score + tier only (security.md PII Tokenization / this
    feature's own "no ids/emails" brief) -- never `user_id`/
    `platform_user_id`.
    """
    _ensure_reputation_tables(dal)
    clamped_limit = max(1, min(int(limit), _MAX_LEADERBOARD_LIMIT))
    rows = await async_dal.select_async(
        dal(
            (dal.community_members.community_id == community_id)
            & (dal.community_members.is_active == True)  # noqa: E712 - pydal idiom
        ),
        orderby=~dal.community_members.reputation,
        limitby=(0, clamped_limit),
    )
    entries = []
    for row in rows:
        score = int(row.reputation) if row.reputation is not None else _DEFAULT_SCORE
        entries.append(
            LeaderboardEntryDTO(
                display_name=row.display_name or "unknown",
                score=score,
                tier=reputation_tier(score),
            )
        )
    return entries
