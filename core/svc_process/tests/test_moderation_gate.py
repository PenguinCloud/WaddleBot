"""Tests for `services.moderation_gate.run_moderation_gate` -- the P1 content-moderation gate.

Every case is driven through dependency-injected fakes (`feature_enabled_fn`
/`get_enabled_categories_fn`/`get_tenant_id_fn`/`classifier`/
`reputation_service`) so no real Ollama/PostHog/DB/Valkey network calls
happen -- `redis_client` is `fakeredis.FakeAsyncRedis` (from `conftest.py`)
for the dedupe guard's real `SET NX` semantics.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from flask_core import PROCESS_TARGET_APP_ID_KEY, PlatformEvent
from flask_core.bundle_runtime import bundle_context
from moderation_module import Classification, LocalOllamaClassifier

from services.moderation_gate import (
    _get_default_classifier,
    _mask_actor,
    reset_classifier_for_tests,
    run_moderation_gate,
)

TENANT = "acme-corp"
COMMUNITY = "42"
APP_ID = "waddles.bot.twitch.default"


def _event(text: str = "you are trash", *, author_id: str | None = "u-1") -> PlatformEvent:
    payload: dict[str, Any] = {"text": text, "channel_id": "chan-1"}
    if author_id is not None:
        payload["author_id"] = author_id
    return PlatformEvent(
        platform="twitch",
        event_type="message",
        actor="penguin",
        payload=payload,
        occurred_at="2026-01-01T00:00:00+00:00",
    )


class _FakeClassifier:
    """Records every `classify()` call; returns a fixed `result` (or `None`)."""

    def __init__(self, result: Classification | None) -> None:
        self.result = result
        self.calls: list[tuple[str, set[str], int, int]] = []

    async def classify(
        self, message: str, enabled_categories: set[str], *, tenant_id: int, community_id: int
    ) -> Classification | None:
        self.calls.append((message, set(enabled_categories), tenant_id, community_id))
        return self.result


class _FakeReputationService:
    """Records every `adjust()` call -- mocks `reputation_service.adjust()` per the task spec."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def adjust(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return kwargs


async def _flag_on(*_args: Any, **_kwargs: Any) -> bool:
    return True


async def _flag_off(*_args: Any, **_kwargs: Any) -> bool:
    return False


class TestFlagGating:
    async def test_flag_off_is_total_noop_classifier_never_called(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)
        reputation = _FakeReputationService()

        async def _cats_must_not_be_called(_cid: int) -> set[str]:
            raise AssertionError("get_enabled_categories must not run when the flag is OFF")

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_flag_off,
                get_enabled_categories_fn=_cats_must_not_be_called,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert classifier.calls == []
        assert reputation.calls == []


class TestNoEnabledCategories:
    async def test_flag_on_no_categories_passes_through_without_calling_classifier(
        self, redis_client: Any
    ) -> None:
        classifier = _FakeClassifier(result=None)
        reputation = _FakeReputationService()

        async def _no_categories(_cid: int) -> set[str]:
            return set()

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_no_categories,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert classifier.calls == []
        assert reputation.calls == []


class TestMatch:
    async def test_match_applies_reputation_hit_and_logs(
        self, redis_client: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        match = Classification(category="hate_speech", confidence=0.91, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        async def _tenant_id(_slug: str) -> int:
            return 7

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with caplog.at_level(logging.INFO):
                await run_moderation_gate(
                    _event("you are trash"),
                    redis_client=redis_client,
                    feature_enabled_fn=_flag_on,
                    get_enabled_categories_fn=_enabled,
                    get_tenant_id_fn=_tenant_id,
                    classifier=classifier,
                    reputation_service=reputation,
                )

        assert len(classifier.calls) == 1
        message, categories, tenant_id, community_id = classifier.calls[0]
        assert message == "you are trash"
        assert categories == {"hate_speech"}
        assert tenant_id == 7
        assert community_id == 42

        assert len(reputation.calls) == 1
        call = reputation.calls[0]
        assert call["community_id"] == 42
        assert call["user_id"] is None
        assert call["event_type"] == "warn"
        assert call["platform"] == "twitch"
        assert call["platform_user_id"] == "u-1"
        assert call["amount_multiplier"] == 1.0
        assert call["metadata"]["moderation_category"] == "hate_speech"
        assert call["metadata"]["confidence"] == 0.91
        assert call["metadata"]["severity"] == "high"

        assert any("moderation_gate.match" in r.message for r in caplog.records)
        assert any("category=hate_speech" in r.message for r in caplog.records)
        # Masked actor -- the raw actor name must not appear verbatim in the log line.
        match_records = [r for r in caplog.records if "moderation_gate.match" in r.message]
        assert "penguin" not in match_records[0].message

    async def test_no_match_does_not_call_reputation_service(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event("hello there, good game"),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert len(classifier.calls) == 1
        assert reputation.calls == []


class TestContextScoping:
    async def test_community_and_tenant_come_from_bundle_context_not_payload(
        self, redis_client: Any
    ) -> None:
        """Security.md Tenant Isolation: never trust tenant/community from `event.payload`."""
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(cid: int) -> set[str]:
            assert cid == 42  # the REAL bundle-context community, not the spoofed payload value
            return {"hate_speech"}

        event = _event("you are trash")
        # Payload carries attacker-controlled fields that must be ignored outright.
        event.payload["tenant"] = "attacker-tenant"
        event.payload["community_id"] = 999999

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert reputation.calls[0]["community_id"] == 42


class TestEnforcementEmit:
    """gh-304 (P4): `moderation_enforcement` + `PROCESS_TARGET_APP_ID_KEY` emission.

    Convention under test: a community opts a category INTO enforcement by
    including `f"{category}_filter"` (in ADDITION to the bare category
    itself) in its `enabled_categories` set -- `moderation_config.py`
    exposes no separate boolean column for this today.
    """

    async def test_filter_enabled_emits_enforcement_payload_and_target_app_id(
        self, redis_client: Any
    ) -> None:
        match = Classification(category="hate_speech", confidence=0.91, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech", "hate_speech_filter"}

        event = _event("you are trash")
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        # Reputation still hit -- enforcement is additive, never a substitute.
        assert len(reputation.calls) == 1

        enforcement = event.payload["moderation_enforcement"]
        assert enforcement["category"] == "hate_speech"
        assert enforcement["score"] == 0.91
        assert enforcement["timeout_s"] == 600
        assert enforcement["action"] == "timeout+warn"
        assert "hate_speech" in enforcement["warn_text"]
        # The original message text must never leak into the enforcement payload.
        assert "you are trash" not in str(enforcement.values())

        assert event.payload[PROCESS_TARGET_APP_ID_KEY] == "waddles.community.moderation.default"

    async def test_filter_disabled_does_not_emit_enforcement_but_still_hits_reputation(
        self, redis_client: Any
    ) -> None:
        match = Classification(category="hate_speech", confidence=0.91, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}  # category on, filter suffix absent

        event = _event("you are trash")
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert len(reputation.calls) == 1
        assert "moderation_enforcement" not in event.payload
        assert PROCESS_TARGET_APP_ID_KEY not in event.payload

    async def test_filter_skip_is_logged_at_debug(
        self, redis_client: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with caplog.at_level(logging.DEBUG):
                await run_moderation_gate(
                    _event("you are trash"),
                    redis_client=redis_client,
                    feature_enabled_fn=_flag_on,
                    get_enabled_categories_fn=_enabled,
                    classifier=classifier,
                    reputation_service=_FakeReputationService(),
                )

        assert any(
            "moderation.enforcement_skipped reason=filter_off" in r.message for r in caplog.records
        )

    async def test_enforcement_emitted_is_logged_at_debug(
        self, redis_client: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech", "hate_speech_filter"}

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            with caplog.at_level(logging.DEBUG):
                await run_moderation_gate(
                    _event("you are trash"),
                    redis_client=redis_client,
                    feature_enabled_fn=_flag_on,
                    get_enabled_categories_fn=_enabled,
                    classifier=classifier,
                    reputation_service=_FakeReputationService(),
                )

        assert any(
            "moderation.enforcement_emitted category=hate_speech timeout_s=600" in r.message
            for r in caplog.records
        )

    async def test_enforcement_applies_per_matched_category_not_just_hate_speech(
        self, redis_client: Any
    ) -> None:
        """Same default timeout/target app id for ANY matched+filtered category, not hardcoded."""
        match = Classification(category="harassment", confidence=0.75, severity="medium")
        classifier = _FakeClassifier(result=match)

        async def _enabled(_cid: int) -> set[str]:
            return {"harassment", "harassment_filter"}

        event = _event("you are trash")
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )

        enforcement = event.payload["moderation_enforcement"]
        assert enforcement["category"] == "harassment"
        assert enforcement["timeout_s"] == 600
        assert "harassment" in enforcement["warn_text"]
        assert event.payload[PROCESS_TARGET_APP_ID_KEY] == "waddles.community.moderation.default"

    async def test_no_match_never_emits_enforcement(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech", "hate_speech_filter"}

        event = _event("hello there, good game")
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )

        assert "moderation_enforcement" not in event.payload
        assert PROCESS_TARGET_APP_ID_KEY not in event.payload

    async def test_reputation_adjust_failure_still_evaluates_enforcement(
        self, redis_client: Any
    ) -> None:
        """Enforcement decision runs regardless of reputation write success/failure."""
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)

        class _RaisingReputationService:
            async def adjust(self, **_kwargs: Any) -> Any:
                raise RuntimeError("db write failed")

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech", "hate_speech_filter"}

        event = _event("you are trash")
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=_RaisingReputationService(),
            )

        assert event.payload[PROCESS_TARGET_APP_ID_KEY] == "waddles.community.moderation.default"


class TestDedupe:
    async def test_second_fanned_out_copy_of_same_message_is_skipped(
        self, redis_client: Any
    ) -> None:
        """The same raw message reaching the gate twice (multi-bundle fan-out) is charged once."""
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        event = _event("you are trash")
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert len(classifier.calls) == 1
        assert len(reputation.calls) == 1

    async def test_different_message_is_not_deduped(self, redis_client: Any) -> None:
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event("you are trash"),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )
            await run_moderation_gate(
                _event("a completely different insult"),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert len(classifier.calls) == 2
        assert len(reputation.calls) == 2


class TestNonChatEvents:
    async def test_non_message_event_type_is_ignored(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)
        event = PlatformEvent(
            platform="twitch",
            event_type="follow",
            actor="penguin",
            payload={},
            occurred_at="2026-01-01T00:00:00+00:00",
        )

        async def _cats_must_not_be_called(_cid: int) -> set[str]:
            raise AssertionError("must not resolve config for a non-chat event")

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_cats_must_not_be_called,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )

        assert classifier.calls == []


class TestNoPlatformUserId:
    async def test_match_falls_back_to_actor_when_no_author_id(self, redis_client: Any) -> None:
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        event = _event("you are trash", author_id=None)  # no native platform id, only actor

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert reputation.calls[0]["platform_user_id"] == "penguin"

    async def test_match_with_no_resolvable_platform_user_id_skips_reputation_hit(
        self, redis_client: Any
    ) -> None:
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        event = PlatformEvent(
            platform="twitch",
            event_type="message",
            actor=None,
            payload={"text": "you are trash"},
            occurred_at="2026-01-01T00:00:00+00:00",
        )

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )

        assert len(classifier.calls) == 1
        assert reputation.calls == []


class TestDefaultClassifierSingleton:
    def test_get_default_classifier_is_a_singleton_local_ollama_instance(self) -> None:
        reset_classifier_for_tests()
        try:
            first = _get_default_classifier()
            second = _get_default_classifier()
            assert first is second
            assert isinstance(first, LocalOllamaClassifier)
        finally:
            reset_classifier_for_tests()


class TestMaskActor:
    def test_none_actor(self) -> None:
        assert _mask_actor(None) == "<unknown>"

    def test_short_actor(self) -> None:
        assert _mask_actor("ab") == "a*"

    def test_long_actor_masked_after_first_two_chars(self) -> None:
        masked = _mask_actor("penguin")
        assert masked.startswith("pe")
        assert "penguin" not in masked
        assert len(masked) == len("penguin")


class TestNoBundleContextOrCommunity:
    async def test_no_bundle_context_bound_is_noop(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)
        # Deliberately NOT inside a `bundle_context()` block.
        await run_moderation_gate(
            _event(),
            redis_client=redis_client,
            feature_enabled_fn=_flag_on,
            classifier=classifier,
            reputation_service=_FakeReputationService(),
        )
        assert classifier.calls == []

    async def test_community_none_is_noop(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)
        with bundle_context(tenant=TENANT, community=None, app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )
        assert classifier.calls == []

    async def test_non_numeric_community_is_noop(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)
        with bundle_context(tenant=TENANT, community="not-a-number", app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )
        assert classifier.calls == []


class TestFailureModesNeverRaise:
    """Every external call the gate makes can fail; none of them may propagate out."""

    async def test_flag_check_exception_is_noop(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)

        async def _raising_flag(*_a: Any, **_k: Any) -> bool:
            raise RuntimeError("posthog unreachable")

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_raising_flag,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )
        assert classifier.calls == []

    async def test_missing_text_payload_is_noop(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)
        event = PlatformEvent(
            platform="twitch",
            event_type="message",
            actor="penguin",
            payload={},  # no "text"
            occurred_at="2026-01-01T00:00:00+00:00",
        )
        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                event,
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )
        assert classifier.calls == []

    async def test_config_read_exception_is_noop(self, redis_client: Any) -> None:
        classifier = _FakeClassifier(result=None)

        async def _raising_cats(_cid: int) -> set[str]:
            raise RuntimeError("db unreachable")

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_raising_cats,
                classifier=classifier,
                reputation_service=_FakeReputationService(),
            )
        assert classifier.calls == []

    async def test_classify_exception_skips_reputation_call(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        class _RaisingClassifier:
            async def classify(self, *_a: Any, **_k: Any) -> Classification | None:
                raise RuntimeError("ollama unreachable")

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=_RaisingClassifier(),
                reputation_service=reputation,
            )
        assert reputation.calls == []

    async def test_reputation_adjust_exception_does_not_propagate(self, redis_client: Any) -> None:
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)

        class _RaisingReputationService:
            async def adjust(self, **_kwargs: Any) -> Any:
                raise RuntimeError("db write failed")

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            # Must not raise -- the caller (runner.py) never wraps this in
            # its own try/except beyond the bundle_context() block already
            # covered by test_runner.py::TestModerationGateWiring.
            await run_moderation_gate(
                _event(),
                redis_client=redis_client,
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=_RaisingReputationService(),
            )

    async def test_dedupe_redis_failure_still_proceeds(self, redis_client: Any) -> None:
        match = Classification(category="hate_speech", confidence=0.9, severity="high")
        classifier = _FakeClassifier(result=match)
        reputation = _FakeReputationService()

        async def _enabled(_cid: int) -> set[str]:
            return {"hate_speech"}

        class _RaisingRedis:
            async def set(self, *_a: Any, **_k: Any) -> None:
                raise RuntimeError("valkey unreachable")

        with bundle_context(tenant=TENANT, community=COMMUNITY, app_id=APP_ID):
            await run_moderation_gate(
                _event(),
                redis_client=_RaisingRedis(),
                feature_enabled_fn=_flag_on,
                get_enabled_categories_fn=_enabled,
                classifier=classifier,
                reputation_service=reputation,
            )
        assert len(classifier.calls) == 1
        assert len(reputation.calls) == 1
