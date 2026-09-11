"""Tests for `services.community_resolver.resolve_community` -- source order + never-raises."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from services import community_resolver as resolver_module
from services.community_context_store import ChannelCommunity
from services.community_resolver import ResolvedCommunity, resolve_community

PLATFORM = "discord"
ENTITY_ID = "chan-1"
USER_ID = "u-1"


@pytest.fixture(autouse=True)
def _reset_warn_rate_limit() -> Any:
    resolver_module.reset_warn_rate_limit_for_tests()
    yield
    resolver_module.reset_warn_rate_limit_for_tests()


def _patch_get_context(
    monkeypatch: pytest.MonkeyPatch, *, result: int | None = None, exc: Exception | None = None
) -> None:
    async def _fake(**kwargs: Any) -> int | None:
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(resolver_module, "get_context", _fake)


def _patch_list_channel_communities(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: list[ChannelCommunity] | None = None,
    exc: Exception | None = None,
) -> None:
    async def _fake(**kwargs: Any) -> list[ChannelCommunity]:
        if exc is not None:
            raise exc
        return result if result is not None else []

    monkeypatch.setattr(resolver_module, "list_channel_communities", _fake)


class TestUserContextSource:
    async def test_hit_returns_user_context_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_get_context(monkeypatch, result=42)
        _patch_list_channel_communities(monkeypatch, result=[])  # would be wrong if reached

        result = await resolve_community(
            platform=PLATFORM,
            platform_user_id=USER_ID,
            platform_entity_id=ENTITY_ID,
            demo_default=None,
        )

        assert result == ResolvedCommunity(community_id=42, source="user_context")

    async def test_skipped_when_user_id_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = False

        async def _fail_if_called(**kwargs: Any) -> int | None:
            nonlocal called
            called = True
            return 999

        monkeypatch.setattr(resolver_module, "get_context", _fail_if_called)
        _patch_list_channel_communities(
            monkeypatch, result=[ChannelCommunity(id=7, name="c", is_primary=True)]
        )

        result = await resolve_community(
            platform=PLATFORM,
            platform_user_id=None,
            platform_entity_id=ENTITY_ID,
            demo_default=None,
        )

        assert called is False
        assert result == ResolvedCommunity(community_id=7, source="channel_primary")

    async def test_skipped_when_entity_id_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = False

        async def _fail_if_called(**kwargs: Any) -> int | None:
            nonlocal called
            called = True
            return 999

        monkeypatch.setattr(resolver_module, "get_context", _fail_if_called)

        result = await resolve_community(
            platform=PLATFORM, platform_user_id=USER_ID, platform_entity_id=None, demo_default=5
        )

        assert called is False
        assert result == ResolvedCommunity(community_id=5, source="demo_shim")

    async def test_miss_falls_through_to_channel_primary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_get_context(monkeypatch, result=None)
        _patch_list_channel_communities(
            monkeypatch, result=[ChannelCommunity(id=9, name="c", is_primary=True)]
        )

        result = await resolve_community(
            platform=PLATFORM,
            platform_user_id=USER_ID,
            platform_entity_id=ENTITY_ID,
            demo_default=None,
        )

        assert result == ResolvedCommunity(community_id=9, source="channel_primary")

    async def test_error_falls_through_and_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _patch_get_context(monkeypatch, exc=RuntimeError("redis down"))
        _patch_list_channel_communities(
            monkeypatch, result=[ChannelCommunity(id=9, name="c", is_primary=True)]
        )

        with caplog.at_level(logging.WARNING, logger="services.community_resolver"):
            result = await resolve_community(
                platform=PLATFORM,
                platform_user_id=USER_ID,
                platform_entity_id=ENTITY_ID,
                demo_default=None,
            )

        assert result == ResolvedCommunity(community_id=9, source="channel_primary")
        assert any("user_context_failed" in r.message for r in caplog.records)


class TestChannelPrimarySource:
    async def test_hit_returns_channel_primary_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_get_context(monkeypatch, result=None)
        _patch_list_channel_communities(
            monkeypatch,
            result=[
                ChannelCommunity(id=1, name="not-primary", is_primary=False),
                ChannelCommunity(id=2, name="primary", is_primary=True),
            ],
        )

        result = await resolve_community(
            platform=PLATFORM,
            platform_user_id=USER_ID,
            platform_entity_id=ENTITY_ID,
            demo_default=None,
        )

        assert result == ResolvedCommunity(community_id=2, source="channel_primary")

    async def test_no_primary_falls_through_to_demo_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_get_context(monkeypatch, result=None)
        _patch_list_channel_communities(
            monkeypatch, result=[ChannelCommunity(id=1, name="none-primary", is_primary=False)]
        )

        result = await resolve_community(
            platform=PLATFORM,
            platform_user_id=USER_ID,
            platform_entity_id=ENTITY_ID,
            demo_default=4,
        )

        assert result == ResolvedCommunity(community_id=4, source="demo_shim")

    async def test_error_falls_through_and_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _patch_get_context(monkeypatch, result=None)
        _patch_list_channel_communities(monkeypatch, exc=RuntimeError("db down"))

        with caplog.at_level(logging.WARNING, logger="services.community_resolver"):
            result = await resolve_community(
                platform=PLATFORM,
                platform_user_id=USER_ID,
                platform_entity_id=ENTITY_ID,
                demo_default=4,
            )

        assert result == ResolvedCommunity(community_id=4, source="demo_shim")
        assert any("channel_primary_failed" in r.message for r in caplog.records)


class TestDemoShimAndNone:
    async def test_demo_default_used_when_no_other_source_hits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_get_context(monkeypatch, result=None)
        _patch_list_channel_communities(monkeypatch, result=[])

        result = await resolve_community(
            platform=PLATFORM,
            platform_user_id=USER_ID,
            platform_entity_id=ENTITY_ID,
            demo_default=4,
        )

        assert result == ResolvedCommunity(community_id=4, source="demo_shim")

    async def test_none_when_every_source_misses_and_no_demo_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_get_context(monkeypatch, result=None)
        _patch_list_channel_communities(monkeypatch, result=[])

        result = await resolve_community(
            platform=PLATFORM,
            platform_user_id=USER_ID,
            platform_entity_id=ENTITY_ID,
            demo_default=None,
        )

        assert result == ResolvedCommunity(community_id=None, source="none")

    async def test_none_when_both_identifiers_unknown_and_no_demo_default(self) -> None:
        result = await resolve_community(
            platform=PLATFORM, platform_user_id=None, platform_entity_id=None, demo_default=None
        )

        assert result == ResolvedCommunity(community_id=None, source="none")


class TestWarnRateLimiting:
    """Rate-limit coverage for the WARN log line on a failing resolution source.

    Avoids monkeypatching the real `time.monotonic` -- it is the actual
    `time` module object (`resolver_module.time is time`), so patching it
    globally would also perturb asyncio/pytest-asyncio's own internal
    timing. `_last_warned_at` is manipulated directly instead, exercising
    the identical branch (`now - last >= _WARN_INTERVAL_S`).
    """

    async def test_repeated_failures_within_interval_warn_once(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _patch_get_context(monkeypatch, exc=RuntimeError("redis down"))
        _patch_list_channel_communities(monkeypatch, result=[])

        with caplog.at_level(logging.WARNING, logger="services.community_resolver"):
            # Real elapsed time between these two calls is microseconds --
            # far under `_WARN_INTERVAL_S` (30s), no clock mocking needed.
            await resolve_community(
                platform=PLATFORM,
                platform_user_id=USER_ID,
                platform_entity_id=ENTITY_ID,
                demo_default=None,
            )
            await resolve_community(
                platform=PLATFORM,
                platform_user_id=USER_ID,
                platform_entity_id=ENTITY_ID,
                demo_default=None,
            )

        warn_records = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "user_context_failed" in r.message
        ]
        assert len(warn_records) == 1

    async def test_failure_after_interval_elapses_warns_again(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _patch_get_context(monkeypatch, exc=RuntimeError("redis down"))
        _patch_list_channel_communities(monkeypatch, result=[])

        with caplog.at_level(logging.WARNING, logger="services.community_resolver"):
            await resolve_community(
                platform=PLATFORM,
                platform_user_id=USER_ID,
                platform_entity_id=ENTITY_ID,
                demo_default=None,
            )
            # Simulate the interval having elapsed since the first WARN.
            key = ("user_context", PLATFORM, ENTITY_ID)
            resolver_module._last_warned_at[key] -= resolver_module._WARN_INTERVAL_S + 1
            await resolve_community(
                platform=PLATFORM,
                platform_user_id=USER_ID,
                platform_entity_id=ENTITY_ID,
                demo_default=None,
            )

        warn_records = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "user_context_failed" in r.message
        ]
        assert len(warn_records) == 2
