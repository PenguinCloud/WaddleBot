"""Ordinary-activity reputation AND loyalty accrual -- gh #310, gh #317.

Per `docs/plans/2026-09-08-content-moderation-design.md`'s own scope note
and this task's motivating gap: `services/moderation_gate.py` is the ONLY
existing caller of `ReputationAdjuster.adjust()` (a `warn`-event penalty on
a classifier match) -- reputation otherwise never accrues from ordinary
chat activity at all. This module is the missing positive-accrual path: a
process-stage runner calls `record_activity()` once per inbound chat
message / bot-command invocation it observes, and this module applies the
community's configured `chat_message`/`command_usage` weight
(`community_reputation_config`, read server-side by
`reputation_module.services.weight_manager.WeightManager`) via the exact
same HTTP-bridged `ReputationAdjuster` client `moderation_gate.py` already
uses -- never a second, competing write path into `reputation_module`'s
own tables (backend-database.md Per-Service Database Accounts: svc-process
has no business holding write access to those tables directly).

Two independent safety controls before ANY accrual reaches the reputation
service, in increasing-cost order:

1. **Feature flag** (`_REPUTATION_ACCRUAL_FLAG_KEY`, `flask_core.
   feature_flags.feature_enabled`) -- `default=True`: PostHog is not wired
   up for alpha yet, so the coded default is what actually governs
   behavior today; this is deliberately the opposite polarity of
   `moderation_gate.py`'s own flag (`default=False`) because a missing/
   OFF-by-default accrual flag would silently disable the entire feature
   this task exists to add, whereas a missing moderation flag safely
   defaults to "no enforcement". Both flags still resolve through the same
   two-gate (PostHog AND license entitlement) `feature_enabled()` contract.
2. **Per-user cooldown** (`SET NX EX` against the same Valkey/Redis the
   rest of svc-process already uses) -- prevents a single user from
   farming reputation by spamming `chat_message`/`command_usage` events
   faster than a real human would produce them. Keyed on `(tenant,
   community, platform, user, event_type)` so a chat-message cooldown and
   a command-usage cooldown for the SAME user never collide, and two
   different users (or the same user in two different communities) never
   share a slot.

Never raises into the caller, matching `run_moderation_gate`'s own
never-raise contract (the eventual runner hook calls this exactly the way
`runner.py::_transform_and_enqueue` calls `run_moderation_gate` today --
best-effort, logged, and never the reason a message fails to reach
`transform_fn`). Every external call (flag check, cooldown SET, reputation
adjust) is caught individually and degrades to `ActivityAccrualResult(
applied=False, reason=...)` rather than propagating.

gh #317 adds a SECOND, fully independent accrual leg alongside the
reputation one above: after the reputation decision is made, `record_
activity()` ALSO posts to `hub_api`'s internal Community Loyalty `earn`
endpoint (`POST /api/v1/internal/loyalty/earn`,
`hub_api/blueprints/v1/community_loyalty.py`) via a lightweight direct
`httpx` call -- same X-Service-Key/`HUB_API_URL` convention `bundles.
social_music_action`/`reputation_gate_client.py` already use, kept inline
here rather than a third client module since this is the module's only
caller of it. Independent in every respect the reputation leg is: its own
PostHog flag (`_LOYALTY_ACCRUAL_FLAG_KEY`, default `True` -- same alpha
rationale as point 1 above), its own `SET NX EX` cooldown key
(`loy:cooldown:...`, `_loyalty_cooldown_key`) so a reputation-flag outage
or cooldown claim never blocks loyalty and vice versa, and its own
never-raise contract (`_accrue_loyalty`). Every event type this module
supports earns at the flat `_LOYALTY_EARN_POINTS`/`_LOYALTY_EARN_KIND`
rate; hub-api applies the community's configured multiplier server-side.
Outcome is folded into `ActivityAccrualResult.loyalty_applied`/
`.loyalty_reason` -- new, defaulted fields so every existing caller/test
constructing this dataclass without them keeps working unchanged.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import redis.asyncio as redis
from flask_core.feature_flags import feature_enabled

from config import Config
from services.reputation_gate_client import (
    ReputationAdjuster,
    ReputationAdjustResult,
    get_reputation_service,
)

logger = logging.getLogger(__name__)

#: `waddles.<module>.<feature>` per the repo's flag-key convention --
#: gates the entire accrual feature. `default=True` (see module docstring
#: point 1) -- unlike `moderation_gate.py`'s `_MODERATION_FLAG_KEY`, this
#: flag being unreachable/never-evaluated must NOT silently disable
#: accrual for the alpha rollout.
_REPUTATION_ACCRUAL_FLAG_KEY = "waddles.community.reputation_accrual"

#: `event_type` values this module knows how to accrue. Anything else
#: (a moderation `warn`, a scaled donation/cheer event, ...) is out of
#: scope for this positive-accrual path -- those have their own callers.
_SUPPORTED_EVENT_TYPES = frozenset({"chat_message", "command_usage"})

#: Per-event-type cooldown window, seconds -- env-configurable, same
#: `os.getenv(..., default)` convention `config.py` itself uses.
#: `chat_message` (high frequency, low per-event weight) gets the longer
#: default window; `command_usage` (lower frequency, deliberate action)
#: gets a shorter one.
_COOLDOWN_SECONDS: dict[str, int] = {
    "chat_message": int(os.getenv("ACTIVITY_ACCRUAL_COOLDOWN_S", "60")),
    "command_usage": int(os.getenv("ACTIVITY_ACCRUAL_COMMAND_COOLDOWN_S", "10")),
}

#: Rate-limit window for the WARN-level "reputation unreachable" log, per
#: community -- see `_log_reputation_unreachable`. Every occurrence is
#: still logged at DEBUG (Observability: "overlog at DEBUG"); only the
#: WARN surface is throttled to avoid spamming on a sustained outage.
_UNREACHABLE_WARN_INTERVAL_S = 60.0

#: `waddles.<module>.<feature>` -- gh #317's independent loyalty-accrual
#: leg. Matches `hub_api/blueprints/v1/community_loyalty.py`'s own
#: `FEATURE_COMMUNITY_LOYALTY` flag key exactly (same feature, checked
#: from both sides of the internal call). `default=True` for the same
#: alpha rationale as `_REPUTATION_ACCRUAL_FLAG_KEY` (module docstring
#: point 1) -- independent flag, independent default decision.
_LOYALTY_ACCRUAL_FLAG_KEY = "waddles.community.loyalty"

#: Loyalty's own per-event-type cooldown window, seconds -- independently
#: tunable from `_COOLDOWN_SECONDS` above via its own env vars, even
#: though both currently default to the same 60s/10s values (gh #317).
_LOYALTY_COOLDOWN_SECONDS: dict[str, int] = {
    "chat_message": int(os.getenv("LOYALTY_ACCRUAL_COOLDOWN_S", "60")),
    "command_usage": int(os.getenv("LOYALTY_ACCRUAL_COMMAND_COOLDOWN_S", "10")),
}

_LOYALTY_EARN_PATH = "/api/v1/internal/loyalty/earn"
_LOYALTY_EARN_TIMEOUT_SECONDS = 5.0

#: Flat per-event earn rate for every supported `event_type` (gh #317
#: task requirement) -- hub-api applies the community's configured
#: multiplier server-side; this module never scales `points` itself.
_LOYALTY_EARN_KIND = "earn_chat"
_LOYALTY_EARN_POINTS = 1


@dataclass(slots=True, frozen=True)
class ActivityAccrualResult:
    """Outcome of one `record_activity()` call.

    `applied=False` always carries a machine-readable `reason` (never a
    raised exception) -- the caller (a stage runner) is expected to log or
    ignore this, never branch its own control flow on it (mirrors
    `run_moderation_gate`'s fire-and-forget contract). `loyalty_applied`/
    `loyalty_reason` (gh #317) report the fully independent loyalty-earn
    leg's own outcome under the same never-raise contract; both default so
    every pre-existing construction of this dataclass keeps working.
    """

    applied: bool
    event_type: str
    reason: str
    loyalty_applied: bool = False
    loyalty_reason: str = "not_attempted"


_redis_lock = threading.Lock()
_redis_client: Any | None = None


def _get_default_redis_client() -> Any:
    """Lazily construct (once, process-wide) the same Valkey client `app.py` builds.

    Mirrors `core/svc_process/app.py`'s own `redis.from_url(Config.
    VALKEY_URL, encoding="utf-8", decode_responses=True)` construction --
    this module does not receive the runner's `ProcessRunner._redis`
    instance directly (the eventual runner hook is a one-line call with no
    client threaded through), so it owns an equivalent process-wide
    singleton instead, the same pattern `moderation_gate.py`'s
    `_get_default_classifier()` and `reputation_gate_client.py`'s
    `get_reputation_service()` already use for their own cross-cutting
    dependencies.
    """
    global _redis_client
    with _redis_lock:
        if _redis_client is None:
            _redis_client = redis.from_url(
                Config.VALKEY_URL, encoding="utf-8", decode_responses=True
            )
        return _redis_client


def reset_redis_client_for_tests() -> None:
    """Clear the cached default Valkey client -- test isolation only."""
    global _redis_client
    _redis_client = None


_http_lock = threading.Lock()
_http_client: httpx.AsyncClient | None = None


def _get_default_http_client() -> httpx.AsyncClient:
    """Lazily construct (once, process-wide) the loyalty leg's own `httpx.AsyncClient`.

    Same singleton-per-process rationale as `_get_default_redis_client`
    above -- the eventual runner hook is a one-line `record_activity()`
    call with no client threaded through.
    """
    global _http_client
    with _http_lock:
        if _http_client is None:
            _http_client = httpx.AsyncClient()
        return _http_client


def reset_http_client_for_tests() -> None:
    """Clear the cached default `httpx.AsyncClient` -- test isolation only."""
    global _http_client
    _http_client = None


_warn_lock = threading.Lock()
_last_warn_at: dict[int, float] = {}

_loyalty_warn_lock = threading.Lock()
_last_loyalty_warn_at: dict[int, float] = {}


def _log_reputation_unreachable(community_id: int, reason: str, logger: logging.Logger) -> None:
    """Log a reputation-adjust failure -- WARN at most once per minute per community.

    Every failure is logged (DEBUG at minimum, per Observability's
    "overlog at DEBUG"); only the WARN surface is throttled so a sustained
    reputation-service outage does not spam the WARN log once per chat
    message.
    """
    now = time.monotonic()
    should_warn = False
    with _warn_lock:
        last = _last_warn_at.get(community_id, 0.0)
        if now - last >= _UNREACHABLE_WARN_INTERVAL_S:
            _last_warn_at[community_id] = now
            should_warn = True
    if should_warn:
        logger.warning(
            "activity_accrual.reputation_unreachable community=%s reason=%s",
            community_id,
            reason,
        )
    else:
        logger.debug(
            "activity_accrual.reputation_unreachable community=%s reason=%s",
            community_id,
            reason,
        )


def _log_loyalty_unreachable(community_id: int, reason: str, logger: logging.Logger) -> None:
    """Log a loyalty-earn failure -- WARN at most once per minute per community.

    Own rate-limit state (`_last_loyalty_warn_at`), independent of
    `_log_reputation_unreachable`'s -- a sustained loyalty outage must not
    suppress (or be suppressed by) a concurrent reputation-service outage
    WARN for the same community.
    """
    now = time.monotonic()
    should_warn = False
    with _loyalty_warn_lock:
        last = _last_loyalty_warn_at.get(community_id, 0.0)
        if now - last >= _UNREACHABLE_WARN_INTERVAL_S:
            _last_loyalty_warn_at[community_id] = now
            should_warn = True
    if should_warn:
        logger.warning(
            "activity_accrual.loyalty_unreachable community=%s reason=%s", community_id, reason
        )
    else:
        logger.debug(
            "activity_accrual.loyalty_unreachable community=%s reason=%s", community_id, reason
        )


def reset_rate_limited_warn_state_for_tests() -> None:
    """Clear the per-community last-WARN-at trackers (reputation AND loyalty) -- tests only."""
    with _warn_lock:
        _last_warn_at.clear()
    with _loyalty_warn_lock:
        _last_loyalty_warn_at.clear()


def _cooldown_key(
    tenant: str, community_id: int, platform: str, platform_user_id: str, event_type: str
) -> str:
    """Build the reputation leg's `SET NX EX` cooldown key -- `rep:` prefix."""
    return f"rep:cooldown:{tenant}:{community_id}:{platform}:{platform_user_id}:{event_type}"


def _loyalty_cooldown_key(
    tenant: str, community_id: int, platform: str, platform_user_id: str, event_type: str
) -> str:
    """Build the loyalty leg's own `SET NX EX` cooldown key -- `loy:` prefix, own namespace."""
    return f"loy:cooldown:{tenant}:{community_id}:{platform}:{platform_user_id}:{event_type}"


async def _claim_cooldown_slot(
    redis_client: Any,
    key: str,
    ttl_seconds: int,
    logger: logging.Logger,
) -> bool:
    """Atomically claim the cooldown slot for one user/event_type; `True` if claimed.

    A `redis_client` failure degrades to "proceed" (`True`) -- same
    fail-open rationale as `moderation_gate.py::_claim_dedupe_slot`: losing
    the anti-farming guarantee on a Valkey outage is preferable to
    silently dropping reputation accrual entirely.
    """
    try:
        claimed = await redis_client.set(key, "1", nx=True, ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001 - cooldown check must never break the caller
        logger.warning("activity_accrual.cooldown_check_failed error=%s", exc)
        return True
    return bool(claimed)


async def _accrue_reputation(
    *,
    tenant: str,
    community_id: int,
    platform: str,
    platform_user_id: str,
    event_type: str,
    event_id: str,
    logger: logging.Logger,
    feature_enabled_fn: Callable[..., Awaitable[bool]],
    redis_client: Any,
    reputation_service: ReputationAdjuster | None,
) -> tuple[bool, str]:
    """The reputation leg -- unchanged behavior/log lines from the pre-gh-#317 `record_activity`.

    In increasing cost order: flag OFF -> cooldown already claimed ->
    reputation service unreachable/rejects the write. Never raises --
    folded into the returned `(applied, reason)` tuple.
    """
    try:
        enabled = await feature_enabled_fn(
            _REPUTATION_ACCRUAL_FLAG_KEY, tenant=tenant, community=community_id, default=True
        )
    except Exception as exc:  # noqa: BLE001 - flag check must never break the caller
        # `feature_enabled()`'s own contract already degrades an outage to
        # `default=True` internally (never raising) -- this except only
        # fires for a genuine bug in the entitlement client or a test's
        # injected `feature_enabled_fn`. Fail closed here (mirrors
        # `moderation_gate.py`'s identical except-branch), NOT a violation
        # of this module's own "default=True" design: that default only
        # governs the normal never-evaluated/outage path inside
        # `feature_enabled()` itself.
        logger.warning("activity_accrual.flag_check_failed error=%s", exc)
        enabled = False
    if not enabled:
        logger.debug("activity_accrual.flag_disabled tenant=%s community=%s", tenant, community_id)
        return False, "flag_disabled"

    cooldown_s = _COOLDOWN_SECONDS[event_type]
    key = _cooldown_key(tenant, community_id, platform, platform_user_id, event_type)
    claimed = await _claim_cooldown_slot(redis_client, key, cooldown_s, logger)
    if not claimed:
        logger.debug("activity_accrual.cooldown key=%s", key)
        return False, "cooldown"

    active_reputation_service = reputation_service or get_reputation_service()
    try:
        result: Any = await active_reputation_service.adjust(
            community_id=community_id,
            user_id=None,
            event_type=event_type,
            platform=platform,
            platform_user_id=platform_user_id,
            metadata={"event_id": event_id, "source": "activity_accrual"},
        )
    except Exception as exc:  # noqa: BLE001 - reputation write must never break the caller
        reason = f"reputation_unreachable: {type(exc).__name__}"
        _log_reputation_unreachable(community_id, reason, logger)
        return False, reason

    if isinstance(result, ReputationAdjustResult) and not result.ok:
        reason = f"reputation_unreachable: {result.error or 'unknown'}"
        _log_reputation_unreachable(community_id, reason, logger)
        return False, reason

    logger.debug(
        "activity_accrual.applied tenant=%s community=%s platform=%s event_type=%s event_id=%s",
        tenant,
        community_id,
        platform,
        event_type,
        event_id,
    )
    return True, "ok"


async def _accrue_loyalty(
    *,
    tenant: str,
    community_id: int,
    platform: str,
    platform_user_id: str,
    event_type: str,
    event_id: str,
    logger: logging.Logger,
    feature_enabled_fn: Callable[..., Awaitable[bool]],
    redis_client: Any,
    http_client: httpx.AsyncClient,
) -> tuple[bool, str]:
    """The loyalty leg (gh #317) -- fully independent flag/cooldown/call from `_accrue_reputation`.

    Same increasing-cost-order/never-raise contract as the reputation leg,
    against hub-api's internal Community Loyalty `earn` endpoint instead of
    `reputation_module`.
    """
    try:
        enabled = await feature_enabled_fn(
            _LOYALTY_ACCRUAL_FLAG_KEY, tenant=tenant, community=community_id, default=True
        )
    except Exception as exc:  # noqa: BLE001 - flag check must never break the caller
        logger.warning("activity_accrual.loyalty_flag_check_failed error=%s", exc)
        enabled = False
    if not enabled:
        logger.debug(
            "activity_accrual.loyalty_flag_disabled tenant=%s community=%s", tenant, community_id
        )
        return False, "flag_disabled"

    cooldown_s = _LOYALTY_COOLDOWN_SECONDS[event_type]
    key = _loyalty_cooldown_key(tenant, community_id, platform, platform_user_id, event_type)
    claimed = await _claim_cooldown_slot(redis_client, key, cooldown_s, logger)
    if not claimed:
        logger.debug("activity_accrual.loyalty_cooldown key=%s", key)
        return False, "cooldown"

    body = {
        "community_id": community_id,
        "platform": platform,
        "platform_user_id": platform_user_id,
        "kind": _LOYALTY_EARN_KIND,
        "points": _LOYALTY_EARN_POINTS,
        "ref": event_id,
    }
    try:
        response = await http_client.post(
            f"{Config.HUB_API_URL}{_LOYALTY_EARN_PATH}",
            json=body,
            headers={"X-Service-Key": Config.SERVICE_API_KEY},
            timeout=_LOYALTY_EARN_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - loyalty write must never break the caller
        reason = f"loyalty_unreachable: {type(exc).__name__}"
        _log_loyalty_unreachable(community_id, reason, logger)
        return False, reason

    if response.status_code >= 400:
        reason = f"loyalty_unreachable: HTTP {response.status_code}"
        _log_loyalty_unreachable(community_id, reason, logger)
        return False, reason

    logger.debug(
        "activity_accrual.loyalty_applied tenant=%s community=%s platform=%s event_type=%s "
        "event_id=%s",
        tenant,
        community_id,
        platform,
        event_type,
        event_id,
    )
    return True, "ok"


async def record_activity(
    *,
    tenant: str,
    community: str | int,
    platform: str,
    platform_user_id: str,
    event_type: str,
    event_id: str,
    logger: logging.Logger = logger,
    feature_enabled_fn: Callable[..., Awaitable[bool]] = feature_enabled,
    redis_client: Any | None = None,
    reputation_service: ReputationAdjuster | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> ActivityAccrualResult:
    """Apply the community's configured reputation weight AND loyalty-earn for one activity event.

    No-op, in increasing cost order, for BOTH shared preconditions:
    unsupported `event_type` -> unresolvable `community`. Past those two
    gates, the reputation leg (`_accrue_reputation`) and the loyalty leg
    (`_accrue_loyalty`, gh #317) each run their OWN flag check -> cooldown
    claim -> external call, fully independently -- the loyalty leg always
    runs after the reputation decision regardless of whether reputation
    applied, was flag-gated, cooled down, or failed, and vice versa. Never
    raises -- every external call (flag evaluation, cooldown SET,
    reputation adjust, loyalty earn POST) is caught individually and
    folded into the returned `ActivityAccrualResult`, matching
    `run_moderation_gate`'s own contract so a caller can await this from
    inside the same best-effort pipeline stage.

    Args:
        tenant: Tenant slug -- from `flask_core.get_bundle_context()`,
            never from untrusted event payload data (security.md Tenant
            Isolation).
        community: Community id -- `str` or `int`, coerced to `int` before
            use (the caller's `BundleContext.community` is a `str`).
        platform: Platform name (`"twitch"`, `"discord"`, ...).
        platform_user_id: The platform-native user id to credit.
        event_type: `"chat_message"` or `"command_usage"` -- anything else
            is rejected with `reason="unsupported_event_type"` (both legs
            skipped).
        event_id: Caller-supplied correlation id, carried into the
            reputation event's `metadata["event_id"]` and the loyalty
            earn call's `ref` for audit/debugging.
        logger: Logger to use for this call -- defaults to this module's
            own logger; a caller may pass a contextual logger instead.
        feature_enabled_fn: Injectable override for `feature_enabled` --
            test seam only, never overridden in production. Shared by both
            legs, each with its own flag key.
        redis_client: Injectable override for the Valkey client used for
            both legs' cooldown checks -- defaults to this module's own
            lazily constructed singleton (see `_get_default_redis_client`).
        reputation_service: Injectable override for the `ReputationAdjuster`
            used to apply the reputation write -- defaults to
            `reputation_gate_client.get_reputation_service()`, the same
            singleton `moderation_gate.py` uses.
        http_client: Injectable override for the `httpx.AsyncClient` used
            for the loyalty leg's `earn` POST -- defaults to this module's
            own lazily constructed singleton (see `_get_default_http_client`).

    Returns:
        `ActivityAccrualResult` with the reputation leg's outcome in
        `applied`/`reason` and the loyalty leg's in `loyalty_applied`/
        `loyalty_reason` -- both `False`/machine-readable-`reason` on any
        no-op or failure, never a raised exception.
    """
    if event_type not in _SUPPORTED_EVENT_TYPES:
        logger.debug("activity_accrual.unsupported_event_type event_type=%s", event_type)
        return ActivityAccrualResult(
            applied=False, event_type=event_type, reason="unsupported_event_type"
        )

    try:
        community_id = int(community)
    except (TypeError, ValueError):
        logger.debug("activity_accrual.invalid_community community=%r", community)
        return ActivityAccrualResult(
            applied=False, event_type=event_type, reason="invalid_community"
        )

    active_redis_client = redis_client if redis_client is not None else _get_default_redis_client()

    applied, reason = await _accrue_reputation(
        tenant=tenant,
        community_id=community_id,
        platform=platform,
        platform_user_id=platform_user_id,
        event_type=event_type,
        event_id=event_id,
        logger=logger,
        feature_enabled_fn=feature_enabled_fn,
        redis_client=active_redis_client,
        reputation_service=reputation_service,
    )

    active_http_client = http_client if http_client is not None else _get_default_http_client()
    loyalty_applied, loyalty_reason = await _accrue_loyalty(
        tenant=tenant,
        community_id=community_id,
        platform=platform,
        platform_user_id=platform_user_id,
        event_type=event_type,
        event_id=event_id,
        logger=logger,
        feature_enabled_fn=feature_enabled_fn,
        redis_client=active_redis_client,
        http_client=active_http_client,
    )

    return ActivityAccrualResult(
        applied=applied,
        event_type=event_type,
        reason=reason,
        loyalty_applied=loyalty_applied,
        loyalty_reason=loyalty_reason,
    )
