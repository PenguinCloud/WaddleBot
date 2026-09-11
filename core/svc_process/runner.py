"""svc-process's real poll -> pull -> transform -> enqueue loop.

Mirrors `core/svc_ingest/runner.py`'s shape exactly, one stage over: RPOPs
each active bundle's `:process` Valkey key, runs the bundle's real
`transform()` entrypoint, and LPUSHes the result onto that bundle's
`:action` key as a JSON `StageEnvelope` -- the task's explicit requirement
("enqueue to `waddles:t:{tenant}:c:{community}:app:{app_id}:action`").
Separated from `app.py` for direct unit-testability, same rationale as
svc-ingest's own `runner.py`.

Wire contract (frozen, `flask_core.stream_pipeline`): the `:process` key
carries `json.dumps(StageEnvelope.to_dict())` strings; this runner reads
one with `StageEnvelope.from_dict(json.loads(raw))`, hands the carried
`PlatformEvent` to the bundle's `transform(event) -> PlatformEvent | None`
entrypoint, and writes the result back as a new `StageEnvelope` (`stage=
"action"`) onto the `:action` key the same way. Malformed input raises
`EnvelopeError` (a `ValueError` subclass) from `from_dict` -- caught here
per-event so one bad message never kills the poll loop.

A transform may return `None` to mean "no reply" -- e.g. a chat bot bundle
that only responds to commands/keywords and must not echo every message
back to the channel. `None` is logged (`process.no_reply`) and the event is
simply dropped -- nothing is enqueued to the `:action` key for it.

Every `transform_fn` call is wrapped in `flask_core.bundle_context()`
(tenant/community/app_id from the envelope just popped) -- `transform`'s
own frozen signature carries only the bare `PlatformEvent`, not the
envelope, so a stateful bundle reaches its tenant/community scope via
`flask_core.get_bundle_context()` from inside its own body instead (see
docs/APP_BUNDLE_AUTHORING.md, 'Accessing the database / shared state').

Cross-app routing (gh #298, `flask_core.PROCESS_TARGET_APP_ID_KEY`): a
transform's returned event may carry a reserved payload key requesting its
result be enqueued onto a DIFFERENT app's `:action` key than the
originating bundle's own (e.g. `bot_process` delegating `!forum` to the
community-forums feature bundle, whose action handler actually persists
the post). This runner pops that key back out of the payload -- it never
leaks into the enqueued event's real data -- and, when present, computes
the destination `:action` key from `target_app_id` instead of `bundle.
app_id`. `tenant`/`community` are unaffected either way: they still come
solely from `envelope_in` (itself sourced from `get_bundle_context()`
upstream), never from event payload -- `target_app_id` changes the
destination QUEUE KEY only, not the tenancy scope.

Board-demo live activity feed: after a successful (non-raising) transform,
`_emit_activity()` writes one best-effort `live_activity_events` row (inbound
message + the bot's reply, or `None` for no-reply) via `services.
activity_feed.record_activity`, so the live WebUI feed can show it. This is
pure telemetry, never load-bearing -- any failure (no DAL bound, DB error,
bad data) is caught broadly and logged; the pipeline still enqueues the
reply (if any) to the `:action` key and returns normally either way.

Content-moderation gate (P1, docs/plans/2026-09-08-content-moderation-
design.md): `services.moderation_gate.run_moderation_gate` runs inside the
same `bundle_context()` block, BEFORE `transform_fn` -- a mandatory gate,
not a bundle, so no community can individually opt out short of the
master PostHog flag. P1 is observe-safe: on a classifier match it logs and
applies a reputation hit (`core/reputation_module`'s already-fixed gh #299
`ReputationService.adjust()`), never blocks or alters the message -- every
one of its own failure modes (flag check, DB read, classifier, reputation
write) is caught internally and never propagates here, so it can never be
the reason a message fails to reach `transform_fn`.

Community resolution (gh #311): a tenant-wide (`community=None`) envelope
no longer maps unconditionally to `Config.DEMO_ACTIVITY_COMMUNITY_ID` --
`services.community_resolver.resolve_community` is consulted first (per-
user override -> channel primary -> demo shim -> none), controlled by
`Config.COMMUNITY_RESOLUTION_ENABLED` (default on; `false` restores the
prior unconditional shim with no lookup at all). An envelope that already
carries a real community is never looked up. Landing on the demo-shim
source logs one WARN per process lifetime (`_warn_demo_shim_once`), not
per event.

Ordinary-activity reputation accrual (gh #310): after a successful
(non-raising) transform of an INBOUND `event_type == "message"` event,
`services.activity_accrual.record_activity` (imported here as
`accrue_activity` -- `services.activity_feed.record_activity`, the board-
demo telemetry writer above, already owns the bare name) is awaited
best-effort to credit the acting user's community reputation --
`command_usage` for a bot-prefixed (`!...`) message, `chat_message`
otherwise. Runs whether or not `transform_fn` produced a reply: ordinary
chatter with no bot reply is exactly the activity this hook credits.
Skipped (never guessed) when the resolved community or the platform user
id can't be determined, and for any non-"message" `event_type` (Twitch
EventSub follow/subscribe/raid and similar system events are out of scope
for this positive-accrual path). Never raises into the caller.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast

from flask_core import (
    PROCESS_TARGET_APP_ID_KEY,
    PlatformEvent,
    StageEnvelope,
    bundle_context,
    get_bundle_dal,
)
from flask_core.stage_runner import (
    BundleDistribution,
    BundlePoller,
    EntrypointLoadError,
    load_entrypoint,
)
from flask_core.stream_pipeline import bundle_stream_key

from config import Config
from services.activity_accrual import ActivityAccrualResult
from services.activity_accrual import record_activity as accrue_activity
from services.activity_feed import record_activity
from services.community_resolver import resolve_community
from services.moderation_gate import run_moderation_gate

logger = logging.getLogger(__name__)

_DEMO_SHIM_WARNED = False


def _warn_demo_shim_once(community_id: int | None) -> None:
    """WARN, once per process (not per event), that resolution fell through to the demo shim.

    `resolve_community` itself only WARNs on a genuine lookup FAILURE
    (rate-limited per `(platform, entity)`); landing on `source=
    "demo_shim"` is not a failure, it's this runner's own alpha-only
    fallback -- worth one visible WARN per process lifetime so an operator
    notices the shim is still load-bearing, without spamming one line per
    tenant-wide message.
    """
    global _DEMO_SHIM_WARNED
    if not _DEMO_SHIM_WARNED:
        _DEMO_SHIM_WARNED = True
        logger.warning("runner.demo_shim_in_use community=%s", community_id)


def reset_demo_shim_warned_for_tests() -> None:
    """Clear the once-per-process demo-shim WARN latch. Test isolation only."""
    global _DEMO_SHIM_WARNED
    _DEMO_SHIM_WARNED = False


def _resolve_platform_user_id(event: PlatformEvent) -> str | None:
    """The platform-native user id for community resolution/activity accrual, or `None`.

    Same convention `services/moderation_gate.py::_resolve_platform_user_id`
    already uses (not imported -- that helper is private to its own
    module): prefers `payload['author_id']`, falls back to `event.actor`
    (a display name), `None` only when neither is available.
    """
    author_id = event.payload.get("author_id")
    if isinstance(author_id, str) and author_id:
        return author_id
    if event.actor:
        # `flask_core` ships no py.typed marker (`follow_imports = "skip"`
        # override in pyproject.toml) -- `event.actor`'s real `str | None`
        # annotation is invisible to mypy here, `cast` restores it. Same
        # boundary `services/moderation_gate.py::_resolve_platform_user_id`
        # already crosses identically.
        return cast(str, event.actor)
    return None


def _resolve_platform_entity_id(event: PlatformEvent) -> str | None:
    """The platform-native channel/server id for community resolution, or `None`.

    Same `channel_id or channel_name` normalization `_emit_activity()`
    (below) and `bundles/community_context_process.py` already use, to
    reconcile Discord's `channel_id` against Twitch's `channel_name` into
    one platform-entity identifier.
    """
    raw = event.payload.get("channel_id") or event.payload.get("channel_name")
    if isinstance(raw, str) and raw:
        return raw
    return None


class ProcessRunner:
    """One poll+drain cycle per call to `run_once()`; `run_forever()` loops it in production."""

    def __init__(self, *, poller: BundlePoller, redis_client: Any, tenant_slug: str) -> None:
        """Build a runner bound to one `BundlePoller`, one Valkey client, and one tenant scope."""
        self._poller = poller
        self._redis = redis_client
        self._tenant_slug = tenant_slug
        self._running = False

    def stop(self) -> None:
        """Signal `run_forever()` to exit after its current iteration."""
        self._running = False

    async def run_forever(self) -> None:
        """Production loop: poll, drain every active bundle's process queue, sleep, repeat."""
        self._running = True
        while self._running:
            await self.run_once()
            import asyncio

            await asyncio.sleep(self._poller.next_delay_s)

    async def run_once(self) -> int:
        """One poll+drain cycle; returns total events transformed+enqueued. Never raises."""
        bundles = await self._poller.poll_once()
        total = 0
        for bundle in bundles:
            total += await self._process_bundle(bundle)
        return total

    async def _process_bundle(self, bundle: BundleDistribution) -> int:
        if bundle.entrypoint is None:
            logger.info("process.no_entrypoint app_id=%s -- skipping", bundle.app_id)
            return 0

        try:
            transform_fn = load_entrypoint(bundle.entrypoint)
        except EntrypointLoadError as exc:
            logger.error(
                "process.entrypoint_load_failed app_id=%s entrypoint=%s error=%s",
                bundle.app_id,
                bundle.entrypoint,
                exc,
            )
            return 0

        community_str: str | None = (
            str(bundle.community_id) if bundle.community_id is not None else None
        )
        process_key = bundle_stream_key(self._tenant_slug, community_str, bundle.app_id, "process")
        action_key = bundle_stream_key(self._tenant_slug, community_str, bundle.app_id, "action")

        count = 0
        while True:
            raw = await self._redis.rpop(process_key)
            if raw is None:
                break
            count += await self._transform_and_enqueue(
                raw,
                transform_fn,
                bundle=bundle,
                action_key=action_key,
                community_str=community_str,
            )
        return count

    async def _transform_and_enqueue(
        self,
        raw: Any,
        transform_fn: Callable[..., Awaitable[Any]],
        *,
        bundle: BundleDistribution,
        action_key: str,
        community_str: str | None,
    ) -> int:
        """Parse the incoming `StageEnvelope`, transform its event, LPUSH the result envelope."""
        try:
            envelope_in = StageEnvelope.from_dict(json.loads(raw))
        except (TypeError, ValueError) as exc:
            # ValueError also covers EnvelopeError (StageEnvelope.from_dict's
            # own error type is a ValueError subclass) and json.JSONDecodeError.
            logger.error("process.bad_envelope app_id=%s error=%s", bundle.app_id, exc)
            return 0

        event_in: PlatformEvent = envelope_in.event

        # Community resolution (gh #311): the pipeline runs tenant-wide
        # (`community=None`) today, but the command-router feature bundles
        # (`bot_process` -> social_quote/social_alias/community_polls/
        # community_announcements/community_forums) reject state-changing
        # ops without a community scope. An envelope that already carries a
        # real community is never overridden -- resolution only runs for a
        # tenant-wide envelope, via `resolve_community`'s per-user ->
        # per-channel -> demo-shim order. `Config.
        # COMMUNITY_RESOLUTION_ENABLED=false` restores the prior
        # unconditional demo-shim mapping with no lookup at all (an
        # operational escape hatch, not expected in normal operation).
        community_for_context: str | None
        if envelope_in.community is not None:
            community_for_context = envelope_in.community
        elif Config.COMMUNITY_RESOLUTION_ENABLED:
            resolved = await resolve_community(
                platform=event_in.platform,
                platform_user_id=_resolve_platform_user_id(event_in),
                platform_entity_id=_resolve_platform_entity_id(event_in),
                demo_default=Config.DEMO_ACTIVITY_COMMUNITY_ID,
            )
            logger.debug(
                "runner.community_resolved source=%s community=%s",
                resolved.source,
                resolved.community_id,
            )
            if resolved.source == "demo_shim":
                _warn_demo_shim_once(resolved.community_id)
            community_for_context = (
                str(resolved.community_id) if resolved.community_id is not None else None
            )
        else:
            community_for_context = str(Config.DEMO_ACTIVITY_COMMUNITY_ID)

        try:
            with bundle_context(
                tenant=envelope_in.tenant,
                community=community_for_context,
                app_id=envelope_in.app_id,
            ):
                await run_moderation_gate(event_in, redis_client=self._redis)
                event_out: PlatformEvent | None = await transform_fn(event_in)
        except Exception as exc:  # noqa: BLE001 - one bad event must never kill the loop
            logger.error("process.transform_failed app_id=%s error=%s", bundle.app_id, exc)
            return 0

        # Cross-app routing (gh #298): pull the reserved routing key back out
        # of the payload before it goes anywhere else -- it must never reach
        # the activity feed or an action-stage bundle as real event data.
        target_app_id: str | None = None
        if event_out is not None and PROCESS_TARGET_APP_ID_KEY in event_out.payload:
            raw_target = event_out.payload[PROCESS_TARGET_APP_ID_KEY]
            if isinstance(raw_target, str) and raw_target:
                target_app_id = raw_target
            event_out = dataclasses.replace(
                event_out,
                payload={
                    k: v for k, v in event_out.payload.items() if k != PROCESS_TARGET_APP_ID_KEY
                },
            )

        await self._emit_activity(envelope_in, event_in, event_out)
        await self._accrue_activity(envelope_in, event_in, community_for_context, bundle)

        if event_out is None:
            logger.info("process.no_reply app_id=%s", bundle.app_id)
            return 0

        envelope_out = StageEnvelope(
            tenant=envelope_in.tenant,
            # Carry the RESOLVED community (real activation, or the demo-shim
            # fallback above) onto the action-stage envelope -- not
            # envelope_in.community, which is still None for a tenant-wide
            # activation. Action bundles run outside bundle_context() (they
            # only see the envelope they're handed), so this is the only
            # channel a resolved community reaches them through. Always
            # sourced from pipeline context/the shim, never from event
            # payload -- same tenancy invariant as target_app_id above.
            community=community_for_context,
            app_id=envelope_in.app_id,
            stage="action",
            event=event_out,
            ts=datetime.now(UTC).isoformat(),
            target_app_id=target_app_id,
        )
        destination_key = (
            bundle_stream_key(self._tenant_slug, community_str, target_app_id, "action")
            if target_app_id is not None
            else action_key
        )
        await self._redis.lpush(destination_key, json.dumps(envelope_out.to_dict()))
        return 1

    async def _emit_activity(
        self,
        envelope_in: StageEnvelope,
        event_in: PlatformEvent,
        event_out: PlatformEvent | None,
    ) -> None:
        """Best-effort write of one `live_activity_events` row for the live WebUI feed.

        FAIL-SAFE (demo-critical): wraps the entire emit in `except
        Exception` -- no DAL bound (`get_bundle_dal()`'s `BundleRuntimeError`),
        a DB error, or bad data must never break the pipeline or the reply.
        On any failure this logs and returns; the caller's subsequent LPUSH
        and normal return are unaffected either way. This is pure telemetry,
        never load-bearing.
        """
        try:
            dal = get_bundle_dal()
            community_id = (
                int(envelope_in.community)
                if envelope_in.community
                else Config.DEMO_ACTIVITY_COMMUNITY_ID
            )
            await record_activity(
                dal,
                community_id=community_id,
                platform=event_in.platform,
                actor=event_in.actor,
                message_in=event_in.payload.get("text"),
                reply_out=event_out.payload.get("text") if event_out is not None else None,
                channel_id=event_in.payload.get("channel_id")
                or event_in.payload.get("channel_name"),
            )
        except Exception as exc:  # noqa: BLE001 - best-effort telemetry, must never break the pipeline
            logger.warning(
                "process.activity_emit_failed app_id=%s error=%s", envelope_in.app_id, exc
            )

    async def _accrue_activity(
        self,
        envelope_in: StageEnvelope,
        event_in: PlatformEvent,
        community_for_context: str | None,
        bundle: BundleDistribution,
    ) -> None:
        """Best-effort ordinary-activity reputation accrual hook (gh #310).

        Fires once per successfully-transformed INBOUND platform event --
        `event_in.event_type == "message"` only (a Twitch EventSub follow/
        subscribe/raid or any other non-chat system event is out of scope
        for this positive-accrual path, same as `services.activity_accrual`'s
        own `_SUPPORTED_EVENT_TYPES`). Runs regardless of whether
        `transform_fn` produced a reply (`event_out`) -- ordinary chatter
        that gets no bot reply is exactly the activity this hook exists to
        credit; only a `command_usage` (bot-prefixed) message is expected to
        usually also enqueue a reply. Skipped, never guessed, when the
        community or the platform user id can't be resolved.

        Awaited directly, not backgrounded: no fire-and-forget/background-
        task pattern exists elsewhere in this runner for a per-event side
        call (`_emit_activity` above is the closest precedent, and it is
        awaited too) -- `record_activity()` already short-circuits cheaply
        on a claimed cooldown before it would ever reach the reputation
        service's HTTP call (`reputation_gate_client.py`'s own 5s
        `httpx.AsyncClient` timeout). Never raises into the caller --
        `record_activity()`'s own contract already never raises; this wraps
        it anyway as defense in depth (mirrors `_emit_activity`'s FAIL-SAFE
        wrapping above) so a broken test double or future refactor can't
        turn best-effort telemetry into a pipeline-breaking bug.
        """
        if event_in.event_type != "message":
            logger.debug(
                "process.activity_accrual_skipped app_id=%s reason=non_message_event_type "
                "event_type=%s",
                bundle.app_id,
                event_in.event_type,
            )
            return
        if community_for_context is None:
            logger.debug(
                "process.activity_accrual_skipped app_id=%s reason=no_community", bundle.app_id
            )
            return
        platform_user_id = _resolve_platform_user_id(event_in)
        if platform_user_id is None:
            logger.debug(
                "process.activity_accrual_skipped app_id=%s reason=no_platform_user_id",
                bundle.app_id,
            )
            return

        text = event_in.payload.get("text")
        accrual_event_type = (
            "command_usage"
            if isinstance(text, str) and text.strip().startswith("!")
            else "chat_message"
        )

        try:
            result: ActivityAccrualResult = await accrue_activity(
                tenant=envelope_in.tenant,
                community=community_for_context,
                platform=event_in.platform,
                platform_user_id=platform_user_id,
                event_type=accrual_event_type,
                # No true per-message id exists on the frozen `StageEnvelope`/
                # `PlatformEvent` contract -- `ts` is the closest available
                # correlation value; `record_activity()` only carries this
                # into `metadata['event_id']` for audit/debugging, never as
                # an idempotency key (the per-user cooldown is that guard).
                event_id=envelope_in.ts,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort accrual, must never break the pipeline
            logger.warning("process.activity_accrual_failed app_id=%s error=%s", bundle.app_id, exc)
            return

        logger.debug(
            "process.activity_accrual_result app_id=%s applied=%s event_type=%s reason=%s",
            bundle.app_id,
            result.applied,
            result.event_type,
            result.reason,
        )
