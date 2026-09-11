"""Tests for `services.live_status` -- gh #287 S10's `coordination` upsert.

`dal` is always passed explicitly (this module's own test-injection
override param), mirroring `test_raid_shoutout.py`'s own `_FakeDal`
structure for the sibling raw-SQL-write service module.
"""

from __future__ import annotations

from typing import Any

from flask_core import PlatformEvent

from services.live_status import (
    LIVE_STATUS_EVENT_TYPES,
    STREAM_OFFLINE_EVENT_TYPE,
    STREAM_ONLINE_EVENT_TYPE,
    LiveStatusResult,
    record_live_event,
)


class _FakeDal:
    """Records every `execute()` call; always returns an empty result set."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Any] | None]] = []

    async def execute(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        self.calls.append((sql, params))
        return []


class _RaisingDal:
    async def execute(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        raise RuntimeError("simulated DB outage")


def _live_event(
    *,
    event_type: str = STREAM_ONLINE_EVENT_TYPE,
    broadcaster_id: str | None = "999",
    broadcaster_login: str | None = "waddlebot",
    metadata: dict[str, Any] | None = None,
    platform: str = "twitch",
) -> PlatformEvent:
    """Build a `PlatformEvent` shaped like `twitch_eventsub_ingest.normalize`'s real output."""
    return PlatformEvent(
        platform=platform,
        event_type=event_type,
        actor=broadcaster_id,
        payload={
            "broadcaster_id": broadcaster_id,
            "broadcaster_login": broadcaster_login,
            "user_id": None,
            "user_login": None,
            "user_display_name": None,
            "metadata": metadata if metadata is not None else {},
        },
        occurred_at="2026-01-01T00:00:00+00:00",
    )


def test_live_status_event_types_constant() -> None:
    assert LIVE_STATUS_EVENT_TYPES == {STREAM_ONLINE_EVENT_TYPE, STREAM_OFFLINE_EVENT_TYPE}


class TestNotALiveStatusEvent:
    async def test_short_circuits_before_any_db_call(self) -> None:
        dal = _FakeDal()
        event = _live_event(event_type="channel.raid")

        result = await record_live_event(event, community="7", dal=dal)

        assert result == LiveStatusResult(
            recorded=False, is_live=None, reason="not_a_live_status_event"
        )
        assert dal.calls == []


class TestMissingBroadcasterId:
    async def test_short_circuits_before_any_db_call(self) -> None:
        dal = _FakeDal()
        event = _live_event(broadcaster_id=None)

        result = await record_live_event(event, community="7", dal=dal)

        assert result == LiveStatusResult(
            recorded=False, is_live=None, reason="missing_broadcaster_id"
        )
        assert dal.calls == []


class TestStreamOnline:
    async def test_upserts_coordination_with_is_live_true(self) -> None:
        dal = _FakeDal()
        event = _live_event(
            event_type=STREAM_ONLINE_EVENT_TYPE, metadata={"type": "live", "viewer_count": 42}
        )

        result = await record_live_event(event, community="7", dal=dal)

        assert result == LiveStatusResult(recorded=True, is_live=True, reason="ok")
        assert len(dal.calls) == 1
        sql, params = dal.calls[0]
        assert "INSERT INTO coordination" in sql
        assert "ON CONFLICT (platform, channel_id)" in sql
        (
            entity_id,
            platform,
            server_id,
            channel_id,
            channel_name,
            is_live,
            viewer_count,
            live_since,
        ) = params
        assert entity_id == "twitch:999"
        assert platform == "twitch"
        assert server_id == "999"
        assert channel_id == "999"
        assert channel_name == "waddlebot"
        assert is_live is True
        assert viewer_count == 42
        assert live_since == "2026-01-01T00:00:00+00:00"  # event.occurred_at

    async def test_missing_viewer_count_defaults_to_zero(self) -> None:
        dal = _FakeDal()
        event = _live_event(event_type=STREAM_ONLINE_EVENT_TYPE, metadata={"type": "live"})

        await record_live_event(event, community="7", dal=dal)

        _, params = dal.calls[0]
        assert params[6] == 0  # viewer_count

    async def test_non_int_viewer_count_defaults_to_zero(self) -> None:
        dal = _FakeDal()
        event = _live_event(
            event_type=STREAM_ONLINE_EVENT_TYPE, metadata={"viewer_count": "not-a-number"}
        )

        await record_live_event(event, community="7", dal=dal)

        _, params = dal.calls[0]
        assert params[6] == 0  # viewer_count


class TestStreamOffline:
    async def test_upserts_coordination_with_is_live_false_and_null_live_since(self) -> None:
        dal = _FakeDal()
        event = _live_event(event_type=STREAM_OFFLINE_EVENT_TYPE)

        result = await record_live_event(event, community="7", dal=dal)

        assert result == LiveStatusResult(recorded=True, is_live=False, reason="ok")
        _, params = dal.calls[0]
        is_live = params[5]
        viewer_count = params[6]
        live_since = params[7]
        assert is_live is False
        assert viewer_count == 0
        assert live_since is None  # ON CONFLICT's CASE keeps the existing value instead


class TestWriteFailure:
    async def test_db_error_never_raises(self) -> None:
        event = _live_event(event_type=STREAM_ONLINE_EVENT_TYPE)

        result = await record_live_event(event, community="7", dal=_RaisingDal())

        assert result == LiveStatusResult(recorded=False, is_live=True, reason="write_failed")
