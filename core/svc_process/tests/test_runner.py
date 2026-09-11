"""Tests for `runner.ProcessRunner` -- the real poll -> RPOP -> transform -> LPUSH loop.

Mirrors `core/svc_ingest/tests/test_runner.py`'s shape -- `redis_client` is
`fakeredis.FakeAsyncRedis` (real LIST semantics), distribution poll mocked
at the HTTP transport layer. Queue wire format is the frozen
`StageEnvelope`/`PlatformEvent` contract (`flask_core.stream_pipeline`):
every push/pop on `:process`/`:action` is `json.dumps(StageEnvelope.
to_dict())`.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import httpx
import pytest
from flask_core import (
    PROCESS_TARGET_APP_ID_KEY,
    EnvelopeError,
    PlatformEvent,
    StageEnvelope,
    reset_bundle_dal_for_tests,
    set_bundle_dal,
)
from flask_core.stage_runner import BundlePoller
from flask_core.stream_pipeline import bundle_stream_key

from config import Config
from runner import ProcessRunner

TENANT = "acme-corp"
APP_ID = "waddles.core.demo.echo"


def _envelope(*, community: str | None, stage: str, text: str = "hello there") -> StageEnvelope:
    return StageEnvelope(
        tenant=TENANT,
        community=community,
        app_id=APP_ID,
        stage=stage,
        event=PlatformEvent(
            platform="twitch",
            event_type="message",
            actor="penguin",
            payload={"text": text, "channel_id": "chan-1"},
            occurred_at="2026-01-01T00:00:00+00:00",
        ),
        ts="2026-01-01T00:00:00+00:00",
    )


def _distribution_handler(bundles: list[dict[str, Any]]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"success": True, "stage": "process", "bundles": bundles, "meta": {}}
        )

    return handler


def _make_poller(http_client_factory: Any, bundles: list[dict[str, Any]]) -> BundlePoller:
    client = http_client_factory(_distribution_handler(bundles))
    return BundlePoller(
        client,
        "http://hub-api/api/v1/distribution/bundles",
        stage="process",
        jwt_provider=lambda: "t",
    )


class TestRunOnce:
    async def test_no_bundles_processes_nothing(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        poller = _make_poller(http_client_factory, [])
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        assert await runner.run_once() == 0

    async def test_real_valkey_roundtrip_transforms_and_enqueues_to_action(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """Fail-first proof: prove a real LPUSH/RPOP round trip onto the process->action key.

        Matches the task's explicit key requirement:
        `waddles:t:{tenant}:c:{community}:app:{app_id}:action`, and the
        frozen `StageEnvelope`/`PlatformEvent` wire contract end to end.
        """
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)

        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        assert await redis_client.rpop(process_key) is None

        action_key = bundle_stream_key(TENANT, "42", APP_ID, "action")
        assert action_key == f"waddles:t:{TENANT}:c:42:app:{APP_ID}:action"
        raw_out = await redis_client.rpop(action_key)
        assert raw_out is not None

        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.stage == "action"
        assert env_out.app_id == APP_ID
        assert env_out.tenant == TENANT
        assert env_out.community == "42"
        assert env_out.event.payload["text"] == "HELLO THERE"
        assert env_out.event.payload["word_count"] == 2
        assert env_out.event.payload["channel_id"] == "chan-1"  # survives the transform
        assert env_out.event.payload["processed"] is True
        assert env_out.event.platform == "twitch"  # top-level PlatformEvent fields preserved

    async def test_malformed_json_in_queue_is_skipped_not_fatal(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """A non-JSON raw value on the `:process` key must not crash the drain loop."""
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        await redis_client.lpush(process_key, "not valid json{{{")
        env_in = _envelope(community=None, stage="process", text="still works")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

    async def test_malformed_envelope_raises_envelope_error_and_is_skipped(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """`StageEnvelope.from_dict` raises `EnvelopeError` on a malformed shape.

        Confirmed directly (unit-level) and end to end (the runner catches
        it -- `EnvelopeError` is a `ValueError` subclass -- and skips the
        one bad message without killing the drain loop).
        """
        with pytest.raises(EnvelopeError):
            StageEnvelope.from_dict({"stage": "process"})  # missing tenant/app_id/event

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        # Legacy/malformed shape -- no "event" key at all.
        await redis_client.lpush(process_key, json.dumps({"stage": "process"}))
        env_in = _envelope(community=None, stage="process", text="still works")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

    async def test_transform_raising_is_skipped_not_fatal(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """A `transform()` that raises (e.g. missing 'text') must not crash the drain loop."""
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        bad_event = StageEnvelope(
            tenant=TENANT,
            community=None,
            app_id=APP_ID,
            stage="process",
            event=PlatformEvent(
                platform="twitch",
                event_type="message",
                actor=None,
                payload={},  # no "text" -- transform() raises ValueError
                occurred_at="2026-01-01T00:00:00+00:00",
            ),
            ts="2026-01-01T00:00:00+00:00",
        )
        await redis_client.lpush(process_key, json.dumps(bad_event.to_dict()))
        env_in = _envelope(community=None, stage="process", text="still works")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

    async def test_transform_returning_none_is_skipped_not_enqueued(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """A transform returning `None` ("no reply") must be dropped, not enqueued.

        Uses the real `bot_process` bundle with random chatter (no command,
        no keyword match) -- its `transform()` returns `None` by design.
        """
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.bot_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        env_in = _envelope(community=None, stage="process", text="just chatting about the game")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 0

        action_key = bundle_stream_key(TENANT, None, APP_ID, "action")
        assert await redis_client.rpop(action_key) is None

    async def test_unknown_entrypoint_skips_bundle_gracefully(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.no_such_module:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        assert await runner.run_once() == 0

    async def test_bundle_with_no_entrypoint_is_skipped(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        poller = _make_poller(
            http_client_factory,
            [{"appId": APP_ID, "communityId": None, "entrypoint": None, "spec": {}, "config": {}}],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        assert await runner.run_once() == 0


class _FakeActivityDal:
    """Minimal AsyncDAL stand-in for `services.activity_feed.record_activity`.

    Implements only the surface `_emit_activity` uses: attribute access for
    the `live_activity_events` table sentinel, and `insert_async`.
    """

    def __init__(self, *, raise_on_insert: Exception | None = None) -> None:
        self.inserted: list[dict[str, Any]] = []
        self._raise_on_insert = raise_on_insert
        self.live_activity_events = object()

    async def insert_async(self, table: Any, **fields: Any) -> int:
        if self._raise_on_insert is not None:
            raise self._raise_on_insert
        assert table is self.live_activity_events
        self.inserted.append(fields)
        return len(self.inserted)


@pytest.fixture
def _activity_dal() -> Any:
    """Bind/unbind a `_FakeActivityDal` around each test in this class."""
    fake = _FakeActivityDal()
    set_bundle_dal(fake)
    yield fake
    reset_bundle_dal_for_tests()


class TestActivityFeedEmit:
    """`_transform_and_enqueue` writes one best-effort `live_activity_events` row.

    Board-demo crunch feature (`runner.py::_emit_activity`) -- see that
    method's docstring for the fail-safe contract this class proves.
    """

    async def test_message_with_reply_writes_message_in_and_reply_out(
        self, redis_client: Any, http_client_factory: Any, _activity_dal: _FakeActivityDal
    ) -> None:
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        assert len(_activity_dal.inserted) == 1
        row = _activity_dal.inserted[0]
        assert row["community_id"] == 42
        assert row["platform"] == "twitch"
        assert row["actor"] == "penguin"
        assert row["message_in"] == "hello there"
        assert row["reply_out"] == "HELLO THERE"
        assert row["channel_id"] == "chan-1"

    async def test_no_reply_writes_reply_out_null(
        self, redis_client: Any, http_client_factory: Any, _activity_dal: _FakeActivityDal
    ) -> None:
        """Uses `bot_process` (random chatter -> `None`) -- reply_out must be `None`."""
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.bot_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        env_in = _envelope(community=None, stage="process", text="just chatting about the game")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 0  # no reply enqueued

        assert len(_activity_dal.inserted) == 1
        row = _activity_dal.inserted[0]
        assert row["message_in"] == "just chatting about the game"
        assert row["reply_out"] is None
        # No community on the envelope -- falls back to the demo default.
        assert row["community_id"] == Config.DEMO_ACTIVITY_COMMUNITY_ID

    async def test_emit_failure_does_not_break_pipeline(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """An `insert_async` failure must not stop the reply from being enqueued/returned."""
        fake = _FakeActivityDal(raise_on_insert=RuntimeError("db is down"))
        set_bundle_dal(fake)
        try:
            poller = _make_poller(
                http_client_factory,
                [
                    {
                        "appId": APP_ID,
                        "communityId": 42,
                        "entrypoint": "bundles.echo_process:transform",
                        "spec": {},
                        "config": {},
                    }
                ],
            )
            runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
            process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
            env_in = _envelope(community="42", stage="process", text="hello there")
            await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

            processed = await runner.run_once()
            assert processed == 1  # pipeline still enqueues despite the emit failure

            action_key = bundle_stream_key(TENANT, "42", APP_ID, "action")
            assert await redis_client.rpop(action_key) is not None
            assert fake.inserted == []  # the raising insert never recorded a row
        finally:
            reset_bundle_dal_for_tests()

    async def test_no_dal_bound_does_not_break_pipeline(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """`get_bundle_dal()` itself raising (no DAL ever bound) must not break the pipeline."""
        reset_bundle_dal_for_tests()  # defensive -- ensure no DAL leaked in from another test
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        action_key = bundle_stream_key(TENANT, "42", APP_ID, "action")
        assert await redis_client.rpop(action_key) is not None


class TestBundleContextWiring:
    """`_transform_and_enqueue` wraps the `transform_fn` call in `flask_core.bundle_context()`.

    Monkeypatches `runner.load_entrypoint` (the name imported into
    `runner.py`'s own namespace) to return a stub `transform`, rather than
    touching any real `core/svc_process/bundles/*.py` file. This is the
    fix for the gap `bundles/social_welcome_process.py` worked around by
    reading `event.payload["community_id"]` -- `transform(event)`'s own
    frozen signature never receives the envelope, so this is the only way
    a process bundle reaches its tenant/community scope.
    """

    async def test_transform_sees_envelope_tenant_community_app_id(
        self, redis_client: Any, http_client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from flask_core import get_bundle_context

        import runner as runner_module

        captured: dict[str, Any] = {}

        async def _stub_transform(event: PlatformEvent) -> PlatformEvent | None:
            ctx = get_bundle_context()
            captured["tenant"] = ctx.tenant
            captured["community"] = ctx.community
            captured["app_id"] = ctx.app_id
            return event

        monkeypatch.setattr(runner_module, "load_entrypoint", lambda ep: _stub_transform)

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.stub:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()

        assert processed == 1
        assert captured == {"tenant": TENANT, "community": "42", "app_id": APP_ID}

    async def test_context_cleared_after_transform(
        self, redis_client: Any, http_client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No context leaks past `_transform_and_enqueue` -- the block always exits cleanly."""
        from flask_core import BundleRuntimeError, get_bundle_context

        import runner as runner_module

        async def _stub_transform(event: PlatformEvent) -> PlatformEvent | None:
            return event

        monkeypatch.setattr(runner_module, "load_entrypoint", lambda ep: _stub_transform)

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.stub:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        env_in = _envelope(community=None, stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        await runner.run_once()

        with pytest.raises(BundleRuntimeError):
            get_bundle_context()

    async def test_none_community_maps_to_demo_community_for_context(
        self, redis_client: Any, http_client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DEMO SHIM: `community=None` on the envelope maps to `Config.DEMO_ACTIVITY_COMMUNITY_ID`.

        Proves the fix state-changing feature commands need (e.g. `!poll
        create`, which calls `get_bundle_context().community` and refuses
        to run when it's `None`) -- the pipeline runs tenant-wide
        (`community=None`) today without this mapping. A real envelope
        community (see `test_transform_sees_envelope_tenant_community_app_id`
        above) is never overridden.
        """
        from flask_core import get_bundle_context

        import runner as runner_module

        captured: dict[str, Any] = {}

        async def _stub_transform(event: PlatformEvent) -> PlatformEvent | None:
            captured["community"] = get_bundle_context().community
            return event

        monkeypatch.setattr(runner_module, "load_entrypoint", lambda ep: _stub_transform)

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.stub:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        env_in = _envelope(community=None, stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()

        assert processed == 1
        assert captured["community"] == str(Config.DEMO_ACTIVITY_COMMUNITY_ID)


class TestCrossAppRouting:
    """gh #298: `target_app_id` reroutes the outbound envelope cross-app.

    `target_app_id` (`flask_core.PROCESS_TARGET_APP_ID_KEY`) reroutes the
    outbound `StageEnvelope` onto a DIFFERENT app's `:action` key than the
    originating bundle's own -- e.g. `bot_process` delegating `!forum` to the
    community-forums feature bundle, whose action handler actually persists
    the post. See `runner.py::_transform_and_enqueue`'s module/method docstrings.
    """

    _TARGET_APP_ID = "waddles.community.forums.default"

    async def test_target_app_id_routes_to_target_apps_action_key(
        self, redis_client: Any, http_client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A `transform_fn` requesting cross-app routing lands on the TARGET's action key.

        Uses a stub transform (not `community_forums_process`) to isolate the
        runner's routing behavior from the forum bundle's own parsing logic --
        that logic is covered separately in
        `test_bundles_community_forums_process.py`.
        """

        async def _stub_transform(event: PlatformEvent) -> PlatformEvent | None:
            return dataclasses.replace(
                event,
                payload={**event.payload, PROCESS_TARGET_APP_ID_KEY: self._TARGET_APP_ID},
            )

        import runner as runner_module

        monkeypatch.setattr(runner_module, "load_entrypoint", lambda ep: _stub_transform)

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.stub:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="!forum create Title | Body")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        # Nothing lands on the originating bundle's own action key.
        own_action_key = bundle_stream_key(TENANT, "42", APP_ID, "action")
        assert await redis_client.rpop(own_action_key) is None

        # It lands on the TARGET app's action key instead.
        target_action_key = bundle_stream_key(TENANT, "42", self._TARGET_APP_ID, "action")
        raw_out = await redis_client.rpop(target_action_key)
        assert raw_out is not None

        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.target_app_id == self._TARGET_APP_ID
        assert env_out.app_id == APP_ID  # originating app_id preserved on the envelope
        assert env_out.tenant == TENANT
        assert env_out.community == "42"
        # The routing key must never leak into the actual event payload data.
        assert PROCESS_TARGET_APP_ID_KEY not in env_out.event.payload

    async def test_no_target_app_id_routes_to_bundles_own_action_key(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """Default (unset) behavior: enqueue to `bundle.app_id`'s own key, `target_app_id=None`."""
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        action_key = bundle_stream_key(TENANT, "42", APP_ID, "action")
        raw_out = await redis_client.rpop(action_key)
        assert raw_out is not None
        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.target_app_id is None

    async def test_target_app_id_with_tenant_wide_community_carries_resolved_community(
        self, redis_client: Any, http_client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression: tenant-wide routing must not put `community=None` on the action envelope.

        Before the fix, `_transform_and_enqueue` built the outbound envelope
        with `envelope_in.community` (still `None` for a tenant-wide
        activation) instead of the resolved `community_for_context` (the
        demo-shim value used for `bundle_context()`/`transform_fn` itself).
        A cross-app-routed action bundle (e.g. `social_music_action`,
        `community_forums_action`) that requires a real community then
        rejected or silently mis-persisted the event. This proves the
        resolved value now rides all the way onto the action envelope.
        """

        async def _stub_transform(event: PlatformEvent) -> PlatformEvent | None:
            return dataclasses.replace(
                event,
                payload={**event.payload, PROCESS_TARGET_APP_ID_KEY: self._TARGET_APP_ID},
            )

        import runner as runner_module

        monkeypatch.setattr(runner_module, "load_entrypoint", lambda ep: _stub_transform)

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.stub:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        env_in = _envelope(community=None, stage="process", text="!forum create Title | Body")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        target_action_key = bundle_stream_key(TENANT, None, self._TARGET_APP_ID, "action")
        raw_out = await redis_client.rpop(target_action_key)
        assert raw_out is not None

        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.community == str(Config.DEMO_ACTIVITY_COMMUNITY_ID)
        assert env_out.community is not None

    async def test_forum_command_via_real_bot_process_routes_to_forums_action_key(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """End-to-end with the REAL `bot_process` -> `community_forums_process` delegation.

        Proves the actual bug this fixes: `!forum create Title | body` sent
        through `bot_process` (the originating bot's own bundle) lands on the
        forums app's `:action` key -- where `community_forums_action.
        create_forum_post` actually persists the post -- not on the bot's own
        action key (chat echo only, never invokes the forum action bundle).
        """
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.bot_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="!forum create My Title | My Body")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        own_action_key = bundle_stream_key(TENANT, "42", APP_ID, "action")
        assert await redis_client.rpop(own_action_key) is None

        forums_action_key = bundle_stream_key(TENANT, "42", self._TARGET_APP_ID, "action")
        raw_out = await redis_client.rpop(forums_action_key)
        assert raw_out is not None
        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.target_app_id == self._TARGET_APP_ID
        assert env_out.event.payload["forum_action"] == "create"
        assert env_out.event.payload["forum_title"] == "My Title"
        assert env_out.event.payload["forum_body"] == "My Body"
        assert PROCESS_TARGET_APP_ID_KEY not in env_out.event.payload

    async def test_forum_command_tenant_wide_activation_carries_resolved_community(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """Same as the test above, but the app is activated TENANT-WIDE (`community=None`).

        Proves the fix for `community_forums_action.create_forum_post`,
        which reads `envelope.community` directly (`community_id=envelope.
        community`, `core/svc_action/bundles/community_forums_action.py`) --
        before the fix this landed a `None` `community_id` in
        `hub_forum_posts` for every tenant-wide activation.
        """
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.bot_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        env_in = _envelope(community=None, stage="process", text="!forum create My Title | My Body")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        forums_action_key = bundle_stream_key(TENANT, None, self._TARGET_APP_ID, "action")
        raw_out = await redis_client.rpop(forums_action_key)
        assert raw_out is not None
        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.community == str(Config.DEMO_ACTIVITY_COMMUNITY_ID)

    async def test_song_request_via_real_bot_process_routes_to_music_action_key(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """End-to-end with the REAL `bot_process` -> `social_music_process` delegation.

        Community-scoped counterpart to the forum tests above, mirroring
        `!sr`'s real routing shape (`_MUSIC_APP_ID =
        "waddles.social.music.default"`, `bundles/social_music_process.py`).
        """
        music_app_id = "waddles.social.music.default"
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.bot_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="!sr some great song")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        music_action_key = bundle_stream_key(TENANT, "42", music_app_id, "action")
        raw_out = await redis_client.rpop(music_action_key)
        assert raw_out is not None
        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.target_app_id == music_app_id
        assert env_out.community == "42"
        assert env_out.event.payload["music_query"] == "some great song"

    async def test_song_request_tenant_wide_activation_carries_resolved_community(
        self, redis_client: Any, http_client_factory: Any
    ) -> None:
        """Root-cause proof: `!sr` under a TENANT-WIDE activation (`community=None`).

        Before the fix this is the exact failure from the live trace:
        `social_music_action.enqueue_song_request` raises
        `NonRetryableTransportError("...envelope.community is None
        (tenant-wide activation unsupported)")` because the action-stage
        envelope carried `community=None` instead of the resolved demo-shim
        value. Asserts the action envelope now carries a real community.
        """
        music_app_id = "waddles.social.music.default"
        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": None,
                    "entrypoint": "bundles.bot_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, None, APP_ID, "process")
        env_in = _envelope(community=None, stage="process", text="!sr some great song")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()
        assert processed == 1

        music_action_key = bundle_stream_key(TENANT, None, music_app_id, "action")
        raw_out = await redis_client.rpop(music_action_key)
        assert raw_out is not None
        env_out = StageEnvelope.from_dict(json.loads(raw_out))
        assert env_out.community == str(Config.DEMO_ACTIVITY_COMMUNITY_ID)
        assert env_out.community is not None
        assert env_out.event.payload["music_query"] == "some great song"


class TestModerationGateWiring:
    """`services.moderation_gate.run_moderation_gate` runs inside `bundle_context()`.

    Proves the wiring point itself, not the gate's own logic (covered in
    `test_moderation_gate.py`): it is actually invoked BEFORE `transform_fn`,
    and a match never blocks the pipeline -- the message still reaches
    `transform_fn` and still gets enqueued to the `:action` key exactly as
    before.
    """

    async def test_gate_is_invoked_before_transform_and_never_blocks_the_pipeline(
        self, redis_client: Any, http_client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import runner as runner_module

        gate_calls: list[Any] = []

        async def _stub_gate(event: PlatformEvent, *, redis_client: Any) -> None:
            # Simulate a real match's own contract: never raises, never
            # alters the event, always lets the caller continue.
            gate_calls.append(event)

        monkeypatch.setattr(runner_module, "run_moderation_gate", _stub_gate)

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        processed = await runner.run_once()

        assert processed == 1
        assert len(gate_calls) == 1
        assert gate_calls[0].payload["text"] == "hello there"

        action_key = bundle_stream_key(TENANT, "42", APP_ID, "action")
        assert await redis_client.rpop(action_key) is not None

    async def test_gate_exception_does_not_break_the_pipeline(
        self, redis_client: Any, http_client_factory: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defense in depth: even if the gate somehow raised, the message still passes."""
        import runner as runner_module

        async def _raising_gate(event: PlatformEvent, *, redis_client: Any) -> None:
            raise RuntimeError("classifier exploded")

        monkeypatch.setattr(runner_module, "run_moderation_gate", _raising_gate)

        poller = _make_poller(
            http_client_factory,
            [
                {
                    "appId": APP_ID,
                    "communityId": 42,
                    "entrypoint": "bundles.echo_process:transform",
                    "spec": {},
                    "config": {},
                }
            ],
        )
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)
        process_key = bundle_stream_key(TENANT, "42", APP_ID, "process")
        env_in = _envelope(community="42", stage="process", text="hello there")
        await redis_client.lpush(process_key, json.dumps(env_in.to_dict()))

        # `_transform_and_enqueue`'s own broad except around the whole
        # `bundle_context()` block catches this -- the one bad event is
        # skipped (not enqueued), matching `process.transform_failed`'s
        # existing contract for any other exception raised inside that block.
        processed = await runner.run_once()
        assert processed == 0


class TestRunForeverLifecycle:
    async def test_stop_ends_run_forever(self, redis_client: Any, http_client_factory: Any) -> None:
        import asyncio

        poller = _make_poller(http_client_factory, [])
        poller._poll_interval_s = 0.01  # noqa: SLF001 - test-only override
        runner = ProcessRunner(poller=poller, redis_client=redis_client, tenant_slug=TENANT)

        task = asyncio.ensure_future(runner.run_forever())
        await asyncio.sleep(0.05)
        runner.stop()
        await asyncio.wait_for(task, timeout=2.0)
        assert task.done()
