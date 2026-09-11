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
"""

from __future__ import annotations

import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

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
from services.activity_feed import record_activity
from services.moderation_gate import run_moderation_gate

logger = logging.getLogger(__name__)


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

        # DEMO SHIM (board-demo crunch, see gh #298/#295 for the proper fix):
        # the pipeline runs tenant-wide (`community=None`) today, but the
        # command-router feature bundles (`bot_process` -> social_quote/
        # social_alias/community_polls/community_announcements/
        # community_forums) reject state-changing ops without a community
        # scope. Map None -> the configured demo community so `!quote add`
        # etc. work end to end; a real envelope community is never
        # overridden.
        community_for_context = (
            envelope_in.community
            if envelope_in.community is not None
            else str(Config.DEMO_ACTIVITY_COMMUNITY_ID)
        )

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
