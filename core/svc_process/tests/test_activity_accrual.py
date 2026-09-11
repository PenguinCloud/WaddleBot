"""Tests for `services.activity_accrual.record_activity` -- ordinary-activity reputation accrual.

Every case is driven through dependency-injected fakes (`feature_enabled_fn`
/`redis_client`/`reputation_service`), mirroring `test_moderation_gate.py`'s
own established pattern -- no real PostHog/Valkey/HTTP network calls happen.
`redis_client` is `fakeredis.FakeAsyncRedis` (from `conftest.py`) for the
cooldown guard's real `SET NX EX` semantics.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from services.activity_accrual import (
    ActivityAccrualResult,
    record_activity,
    reset_rate_limited_warn_state_for_tests,
)
from services.reputation_gate_client import ReputationAdjustResult

TENANT = "acme-corp"
COMMUNITY = 42
PLATFORM = "twitch"
PLATFORM_USER_ID = "u-1"
EVENT_ID = "evt-1"


@pytest.fixture(autouse=True)
def _reset_warn_state() -> None:
    reset_rate_limited_warn_state_for_tests()


class _FakeReputationService:
    """Records every `adjust()` call; returns a fixed `result` (or raises)."""

    def __init__(
        self, result: ReputationAdjustResult | None = None, raises: Exception | None = None
    ) -> None:
        self.result = result if result is not None else ReputationAdjustResult(ok=True, error=None)
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    async def adjust(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.result


async def _flag_on(*_args: Any, **_kwargs: Any) -> bool:
    return True


async def _flag_off(*_args: Any, **_kwargs: Any) -> bool:
    return False


async def _call(
    *,
    redis_client: Any,
    reputation_service: Any,
    feature_enabled_fn: Any = _flag_on,
    event_type: str = "chat_message",
    community: Any = COMMUNITY,
    event_id: str = EVENT_ID,
) -> ActivityAccrualResult:
    return await record_activity(
        tenant=TENANT,
        community=community,
        platform=PLATFORM,
        platform_user_id=PLATFORM_USER_ID,
        event_type=event_type,
        event_id=event_id,
        feature_enabled_fn=feature_enabled_fn,
        redis_client=redis_client,
        reputation_service=reputation_service,
    )


class TestAppliedPath:
    async def test_chat_message_applies_and_calls_reputation_with_correct_args(
        self, redis_client: Any
    ) -> None:
        reputation = _FakeReputationService()

        result = await _call(redis_client=redis_client, reputation_service=reputation)

        assert result == ActivityAccrualResult(applied=True, event_type="chat_message", reason="ok")
        assert len(reputation.calls) == 1
        call = reputation.calls[0]
        assert call["community_id"] == COMMUNITY
        assert call["user_id"] is None
        assert call["event_type"] == "chat_message"
        assert call["platform"] == PLATFORM
        assert call["platform_user_id"] == PLATFORM_USER_ID
        assert call["metadata"] == {"event_id": EVENT_ID, "source": "activity_accrual"}

    async def test_command_usage_applies(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, event_type="command_usage"
        )

        assert result.applied is True
        assert result.event_type == "command_usage"
        assert reputation.calls[0]["event_type"] == "command_usage"

    async def test_string_community_is_coerced_to_int(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, community="42"
        )

        assert result.applied is True
        assert reputation.calls[0]["community_id"] == 42


class TestUnsupportedEventType:
    async def test_unsupported_event_type_is_rejected_without_calling_reputation(
        self, redis_client: Any
    ) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, event_type="follow"
        )

        assert result == ActivityAccrualResult(
            applied=False, event_type="follow", reason="unsupported_event_type"
        )
        assert reputation.calls == []


class TestInvalidCommunity:
    async def test_non_numeric_community_is_rejected(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, community="not-a-number"
        )

        assert result.applied is False
        assert result.reason == "invalid_community"
        assert reputation.calls == []


class TestFlagGating:
    async def test_flag_off_is_noop(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, feature_enabled_fn=_flag_off
        )

        assert result == ActivityAccrualResult(
            applied=False, event_type="chat_message", reason="flag_disabled"
        )
        assert reputation.calls == []

    async def test_flag_check_exception_fails_closed(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        async def _raising_flag(*_a: Any, **_k: Any) -> bool:
            raise RuntimeError("posthog unreachable")

        result = await _call(
            redis_client=redis_client,
            reputation_service=reputation,
            feature_enabled_fn=_raising_flag,
        )

        assert result.applied is False
        assert result.reason == "flag_disabled"
        assert reputation.calls == []


class TestCooldown:
    async def test_second_chat_message_within_cooldown_is_skipped(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        first = await _call(redis_client=redis_client, reputation_service=reputation)
        second = await _call(redis_client=redis_client, reputation_service=reputation)

        assert first.applied is True
        assert second.applied is False
        assert second.reason == "cooldown"
        assert len(reputation.calls) == 1

    async def test_cooldown_key_format(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        await _call(redis_client=redis_client, reputation_service=reputation)

        expected_key = (
            f"rep:cooldown:{TENANT}:{COMMUNITY}:{PLATFORM}:{PLATFORM_USER_ID}:chat_message"
        )
        assert await redis_client.exists(expected_key)

    async def test_chat_message_and_command_usage_cooldowns_are_independent(
        self, redis_client: Any
    ) -> None:
        reputation = _FakeReputationService()

        chat_result = await _call(redis_client=redis_client, reputation_service=reputation)
        command_result = await _call(
            redis_client=redis_client, reputation_service=reputation, event_type="command_usage"
        )

        assert chat_result.applied is True
        assert command_result.applied is True
        assert len(reputation.calls) == 2

    async def test_different_users_are_not_cross_throttled(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        first = await record_activity(
            tenant=TENANT,
            community=COMMUNITY,
            platform=PLATFORM,
            platform_user_id="user-a",
            event_type="chat_message",
            event_id=EVENT_ID,
            feature_enabled_fn=_flag_on,
            redis_client=redis_client,
            reputation_service=reputation,
        )
        second = await record_activity(
            tenant=TENANT,
            community=COMMUNITY,
            platform=PLATFORM,
            platform_user_id="user-b",
            event_type="chat_message",
            event_id=EVENT_ID,
            feature_enabled_fn=_flag_on,
            redis_client=redis_client,
            reputation_service=reputation,
        )

        assert first.applied is True
        assert second.applied is True
        assert len(reputation.calls) == 2

    async def test_cooldown_expiry_allows_a_new_accrual(self, redis_client: Any) -> None:
        """Cooldown TTL expiring (not just a fresh key) re-allows accrual."""
        reputation = _FakeReputationService()
        key = f"rep:cooldown:{TENANT}:{COMMUNITY}:{PLATFORM}:{PLATFORM_USER_ID}:chat_message"

        first = await _call(redis_client=redis_client, reputation_service=reputation)
        assert first.applied is True

        # Simulate the cooldown TTL having elapsed -- delete the key rather
        # than sleeping 60s in a test.
        await redis_client.delete(key)

        second = await _call(redis_client=redis_client, reputation_service=reputation)
        assert second.applied is True
        assert len(reputation.calls) == 2

    async def test_cooldown_redis_failure_fails_open(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        class _RaisingRedis:
            async def set(self, *_a: Any, **_k: Any) -> None:
                raise RuntimeError("valkey unreachable")

        result = await _call(redis_client=_RaisingRedis(), reputation_service=reputation)

        assert result.applied is True
        assert len(reputation.calls) == 1


class TestReputationFailureModes:
    async def test_client_reports_failure_result_applied_false_with_reason(
        self, redis_client: Any
    ) -> None:
        reputation = _FakeReputationService(
            result=ReputationAdjustResult(ok=False, error="HTTP 500")
        )

        result = await _call(redis_client=redis_client, reputation_service=reputation)

        assert result.applied is False
        assert result.reason == "reputation_unreachable: HTTP 500"

    async def test_client_raises_applied_false_with_exception_class_reason(
        self, redis_client: Any
    ) -> None:
        reputation = _FakeReputationService(raises=RuntimeError("connection refused"))

        result = await _call(redis_client=redis_client, reputation_service=reputation)

        assert result.applied is False
        assert result.reason == "reputation_unreachable: RuntimeError"

    async def test_reputation_failure_never_raises_into_caller(self, redis_client: Any) -> None:
        reputation = _FakeReputationService(raises=RuntimeError("boom"))

        # Must not raise -- record_activity's own never-raise contract.
        await _call(redis_client=redis_client, reputation_service=reputation)

    async def test_warn_logged_at_most_once_per_minute_per_community(
        self, redis_client: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            for i in range(2):
                reputation = _FakeReputationService(raises=RuntimeError("boom"))
                await record_activity(
                    tenant=TENANT,
                    community=COMMUNITY,
                    platform=PLATFORM,
                    platform_user_id=f"user-{i}",
                    event_type="chat_message",
                    event_id=EVENT_ID,
                    feature_enabled_fn=_flag_on,
                    redis_client=redis_client,
                    reputation_service=reputation,
                )

        warn_records = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "reputation_unreachable" in r.message
        ]
        debug_records = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG and "reputation_unreachable" in r.message
        ]
        assert len(warn_records) == 1
        assert len(debug_records) == 1
