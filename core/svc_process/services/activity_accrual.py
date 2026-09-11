"""Ordinary-activity reputation accrual -- gh #310.

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
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

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


@dataclass(slots=True, frozen=True)
class ActivityAccrualResult:
    """Outcome of one `record_activity()` call.

    `applied=False` always carries a machine-readable `reason` (never a
    raised exception) -- the caller (a stage runner) is expected to log or
    ignore this, never branch its own control flow on it (mirrors
    `run_moderation_gate`'s fire-and-forget contract).
    """

    applied: bool
    event_type: str
    reason: str


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


_warn_lock = threading.Lock()
_last_warn_at: dict[int, float] = {}


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


def reset_rate_limited_warn_state_for_tests() -> None:
    """Clear the per-community last-WARN-at tracker -- test isolation only."""
    with _warn_lock:
        _last_warn_at.clear()


def _cooldown_key(
    tenant: str, community_id: int, platform: str, platform_user_id: str, event_type: str
) -> str:
    """Build the `SET NX EX` cooldown key for one (tenant, community, user, event_type)."""
    return f"rep:cooldown:{tenant}:{community_id}:{platform}:{platform_user_id}:{event_type}"


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
) -> ActivityAccrualResult:
    """Apply the community's configured reputation weight for one activity event.

    No-op, in increasing cost order: unsupported `event_type` ->
    unresolvable `community` -> flag OFF -> cooldown already claimed ->
    reputation service unreachable/rejects the write. Never raises --
    every external call (flag evaluation, cooldown SET, reputation
    adjust) is caught individually and folded into `ActivityAccrualResult.
    reason`, matching `run_moderation_gate`'s own contract so a caller can
    await this from inside the same best-effort pipeline stage.

    Args:
        tenant: Tenant slug -- from `flask_core.get_bundle_context()`,
            never from untrusted event payload data (security.md Tenant
            Isolation).
        community: Community id -- `str` or `int`, coerced to `int` before
            use (the caller's `BundleContext.community` is a `str`).
        platform: Platform name (`"twitch"`, `"discord"`, ...).
        platform_user_id: The platform-native user id to credit.
        event_type: `"chat_message"` or `"command_usage"` -- anything else
            is rejected with `reason="unsupported_event_type"`.
        event_id: Caller-supplied correlation id, carried into the
            reputation event's `metadata["event_id"]` for audit/debugging.
        logger: Logger to use for this call -- defaults to this module's
            own logger; a caller may pass a contextual logger instead.
        feature_enabled_fn: Injectable override for `feature_enabled` --
            test seam only, never overridden in production.
        redis_client: Injectable override for the Valkey client used for
            the cooldown check -- defaults to this module's own lazily
            constructed singleton (see `_get_default_redis_client`).
        reputation_service: Injectable override for the `ReputationAdjuster`
            used to apply the write -- defaults to `reputation_gate_client
            .get_reputation_service()`, the same singleton
            `moderation_gate.py` uses.

    Returns:
        `ActivityAccrualResult(applied=True, ...)` on a confirmed
        reputation write; `applied=False` with a machine-readable `reason`
        otherwise.
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
        return ActivityAccrualResult(applied=False, event_type=event_type, reason="flag_disabled")

    cooldown_s = _COOLDOWN_SECONDS[event_type]
    key = _cooldown_key(tenant, community_id, platform, platform_user_id, event_type)
    active_redis_client = redis_client if redis_client is not None else _get_default_redis_client()
    claimed = await _claim_cooldown_slot(active_redis_client, key, cooldown_s, logger)
    if not claimed:
        logger.debug("activity_accrual.cooldown key=%s", key)
        return ActivityAccrualResult(applied=False, event_type=event_type, reason="cooldown")

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
        return ActivityAccrualResult(applied=False, event_type=event_type, reason=reason)

    if isinstance(result, ReputationAdjustResult) and not result.ok:
        reason = f"reputation_unreachable: {result.error or 'unknown'}"
        _log_reputation_unreachable(community_id, reason, logger)
        return ActivityAccrualResult(applied=False, event_type=event_type, reason=reason)

    logger.debug(
        "activity_accrual.applied tenant=%s community=%s platform=%s event_type=%s event_id=%s",
        tenant,
        community_id,
        platform,
        event_type,
        event_id,
    )
    return ActivityAccrualResult(applied=True, event_type=event_type, reason="ok")
