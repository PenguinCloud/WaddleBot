"""Tests for `services.activity_accrual.record_activity` -- reputation AND loyalty accrual.

Every case is driven through dependency-injected fakes (`feature_enabled_fn`
/`redis_client`/`reputation_service`/`http_client`), mirroring `test_
moderation_gate.py`'s own established pattern -- no real PostHog/Valkey/
HTTP network calls happen. `redis_client` is `fakeredis.FakeAsyncRedis`
(from `conftest.py`) for the cooldown guard's real `SET NX EX` semantics.
`http_client` defaults to `_loyalty_success_client()` (a fresh `httpx.
MockTransport`-backed client returning a canned success response) so
every pre-existing `_call(...)` site exercises gh #317's independent
loyalty-earn leg deterministically, with no real network dependency,
without needing to pass `http_client` explicitly at every call site.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from config import Config
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

_LOYALTY_EARN_URL_FRAGMENT = "/api/v1/internal/loyalty/earn"


def _loyalty_success_client(
    *, captured: dict[str, Any] | None = None, status_code: int = 200
) -> httpx.AsyncClient:
    """A fresh `httpx.AsyncClient` (`MockTransport`-backed) for the loyalty leg's `earn` POST.

    `captured`, if given, records the last request's url/body/headers --
    used by tests asserting the exact HTTP call made.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            captured["service_key"] = request.headers.get("x-service-key")
        if status_code >= 400:
            return httpx.Response(status_code)
        return httpx.Response(status_code, json={"status": "success", "data": {"applied_delta": 1}})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _loyalty_unreachable_client() -> httpx.AsyncClient:
    """An `httpx.AsyncClient` whose every request raises a network error."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


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

    async def adjust(
        self,
        community_id: int,
        user_id: int | None,
        event_type: str,
        platform: str,
        platform_user_id: str,
        metadata: dict[str, Any] | None = None,
        reason: str | None = None,
        amount_multiplier: float = 1.0,
    ) -> Any:
        self.calls.append(
            {
                "community_id": community_id,
                "user_id": user_id,
                "event_type": event_type,
                "platform": platform,
                "platform_user_id": platform_user_id,
                "metadata": metadata,
                "reason": reason,
                "amount_multiplier": amount_multiplier,
            }
        )
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
    http_client: Any = None,
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
        http_client=http_client if http_client is not None else _loyalty_success_client(),
    )


class TestAppliedPath:
    async def test_chat_message_applies_and_calls_reputation_with_correct_args(
        self, redis_client: Any
    ) -> None:
        reputation = _FakeReputationService()

        result = await _call(redis_client=redis_client, reputation_service=reputation)

        assert result == ActivityAccrualResult(
            applied=True,
            event_type="chat_message",
            reason="ok",
            loyalty_applied=True,
            loyalty_reason="ok",
        )
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
        assert result.loyalty_applied is False
        assert result.loyalty_reason == "not_attempted"
        assert reputation.calls == []


class TestInvalidCommunity:
    async def test_non_numeric_community_is_rejected(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, community="not-a-number"
        )

        assert result.applied is False
        assert result.reason == "invalid_community"
        assert result.loyalty_applied is False
        assert result.loyalty_reason == "not_attempted"
        assert reputation.calls == []


class TestFlagGating:
    async def test_flag_off_is_noop(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, feature_enabled_fn=_flag_off
        )

        assert result == ActivityAccrualResult(
            applied=False,
            event_type="chat_message",
            reason="flag_disabled",
            loyalty_applied=False,
            loyalty_reason="flag_disabled",
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
        assert result.loyalty_applied is False
        assert result.loyalty_reason == "flag_disabled"
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

        expected_loyalty_key = (
            f"loy:cooldown:{TENANT}:{COMMUNITY}:{PLATFORM}:{PLATFORM_USER_ID}:chat_message"
        )
        assert await redis_client.exists(expected_loyalty_key)

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
            http_client=_loyalty_success_client(),
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
            http_client=_loyalty_success_client(),
        )

        assert first.applied is True
        assert second.applied is True
        assert first.loyalty_applied is True
        assert second.loyalty_applied is True
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
        # The loyalty leg is fully independent -- a reputation failure never blocks it.
        assert result.loyalty_applied is True
        assert result.loyalty_reason == "ok"

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
                    http_client=_loyalty_success_client(),
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


class TestLoyaltyEarnCall:
    """gh #317's independent loyalty-earn leg -- own flag, own cooldown, own hub-api call."""

    async def test_posts_correct_body_and_service_key(
        self, redis_client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Config, "HUB_API_URL", "https://hub-api.internal")
        monkeypatch.setattr(Config, "SERVICE_API_KEY", "s3cr3t")
        reputation = _FakeReputationService()
        captured: dict[str, Any] = {}

        result = await _call(
            redis_client=redis_client,
            reputation_service=reputation,
            http_client=_loyalty_success_client(captured=captured),
        )

        assert result.loyalty_applied is True
        assert result.loyalty_reason == "ok"
        assert captured["url"] == f"https://hub-api.internal{_LOYALTY_EARN_URL_FRAGMENT}"
        assert captured["service_key"] == "s3cr3t"
        assert captured["body"] == {
            "community_id": COMMUNITY,
            "platform": PLATFORM,
            "platform_user_id": PLATFORM_USER_ID,
            "kind": "earn_chat",
            "points": 1,
            "ref": EVENT_ID,
        }

    async def test_flag_off_is_noop_and_never_calls_hub_api(self, redis_client: Any) -> None:
        """The loyalty flag is checked independently -- `_flag_off` disables BOTH legs here."""
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client, reputation_service=reputation, feature_enabled_fn=_flag_off
        )

        assert result.loyalty_applied is False
        assert result.loyalty_reason == "flag_disabled"

    async def test_loyalty_flag_independent_of_reputation_flag(self, redis_client: Any) -> None:
        """Only the loyalty flag key is disabled -- reputation still applies."""
        reputation = _FakeReputationService()

        async def _loyalty_only_off(flag_key: str, **_kwargs: Any) -> bool:
            return flag_key != "waddles.community.loyalty"

        result = await _call(
            redis_client=redis_client,
            reputation_service=reputation,
            feature_enabled_fn=_loyalty_only_off,
        )

        assert result.applied is True
        assert result.loyalty_applied is False
        assert result.loyalty_reason == "flag_disabled"

    async def test_second_earn_within_cooldown_is_skipped(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        first = await _call(redis_client=redis_client, reputation_service=reputation)
        second = await _call(redis_client=redis_client, reputation_service=reputation)

        assert first.loyalty_applied is True
        assert second.loyalty_applied is False
        assert second.loyalty_reason == "cooldown"
        # Reputation's own cooldown independently blocks its second call too --
        # this asserts the loyalty leg's cooldown fired for its OWN reason,
        # not as a side effect of the reputation leg's.
        assert second.reason == "cooldown"

    async def test_reputation_cooldown_does_not_block_loyalty(self, redis_client: Any) -> None:
        """Deleting only the reputation cooldown key re-allows reputation but not loyalty."""
        reputation = _FakeReputationService()
        rep_key = f"rep:cooldown:{TENANT}:{COMMUNITY}:{PLATFORM}:{PLATFORM_USER_ID}:chat_message"

        first = await _call(redis_client=redis_client, reputation_service=reputation)
        assert first.applied is True
        assert first.loyalty_applied is True

        await redis_client.delete(rep_key)

        second = await _call(redis_client=redis_client, reputation_service=reputation)
        assert second.applied is True
        assert second.loyalty_applied is False
        assert second.loyalty_reason == "cooldown"

    async def test_unreachable_hub_api_is_never_raised(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client,
            reputation_service=reputation,
            http_client=_loyalty_unreachable_client(),
        )

        assert result.loyalty_applied is False
        assert result.loyalty_reason.startswith("loyalty_unreachable:")

    async def test_5xx_response_is_never_raised(self, redis_client: Any) -> None:
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client,
            reputation_service=reputation,
            http_client=_loyalty_success_client(status_code=500),
        )

        assert result.loyalty_applied is False
        assert result.loyalty_reason == "loyalty_unreachable: HTTP 500"

    async def test_loyalty_failure_isolated_from_reputation_path(self, redis_client: Any) -> None:
        """A failed loyalty POST never affects the reputation leg's own outcome."""
        reputation = _FakeReputationService()

        result = await _call(
            redis_client=redis_client,
            reputation_service=reputation,
            http_client=_loyalty_unreachable_client(),
        )

        assert result.applied is True
        assert result.reason == "ok"
        assert len(reputation.calls) == 1

    async def test_warn_logged_at_most_once_per_minute_per_community(
        self, redis_client: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            for i in range(2):
                reputation = _FakeReputationService()
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
                    http_client=_loyalty_unreachable_client(),
                )

        warn_records = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "loyalty_unreachable" in r.message
        ]
        debug_records = [
            r
            for r in caplog.records
            if r.levelno == logging.DEBUG and "loyalty_unreachable" in r.message
        ]
        assert len(warn_records) == 1
        assert len(debug_records) == 1
