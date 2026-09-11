"""Tests for `services.raid_shoutout` -- gh #316's auto-shoutout decision matrix.

`dal`/`redis_client` are always passed explicitly (this module's own
test-injection override params), mirroring `test_command_alias_store.py`'s
own structure for the sibling Redis-first DB store this module is modeled
on.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from flask_core import PlatformEvent

from services import raid_shoutout as raid_shoutout_module
from services.raid_shoutout import (
    _HIT_PREFIX,
    _MISS_VALUE,
    RAID_EVENT_TYPE,
    ShoutoutDecision,
    _config_cache_key,
    maybe_auto_shoutout,
    reset_redis_client_for_tests,
    reset_warn_rate_limit_for_tests,
)

COMMUNITY_ID = 7
COMMUNITY = str(COMMUNITY_ID)
TARGET_LOGIN = "raiderlogin"


def _raid_event(
    *,
    user_login: str | None = TARGET_LOGIN,
    user_id: str | None = "999",
    actor: str | None = None,
    viewers: int = 50,
    event_type: str = RAID_EVENT_TYPE,
    platform: str = "twitch",
) -> PlatformEvent:
    """Build a `PlatformEvent` shaped like `twitch_eventsub_ingest.normalize`'s real raid output."""
    return PlatformEvent(
        platform=platform,
        event_type=event_type,
        actor=actor,
        payload={
            "broadcaster_id": "111",
            "broadcaster_login": "targetchannel",
            "user_id": user_id,
            "user_login": user_login,
            "user_display_name": "RaiderLogin",
            "metadata": {"viewers": viewers},
        },
        occurred_at="2026-01-01T00:00:00+00:00",
    )


def _config_row(
    *, mode: str = "all_creators", trigger_raid_host: bool = True, vso_enabled: bool = True
) -> dict[str, Any]:
    return {
        "auto_shoutout_mode": mode,
        "trigger_raid_host": trigger_raid_host,
        "vso_enabled": vso_enabled,
    }


class _FakeDal:
    """Records every `execute()` call; routes by table name to a preloaded row set."""

    def __init__(
        self,
        *,
        config_rows: list[Any] | None = None,
        creator_rows: list[Any] | None = None,
    ) -> None:
        self.config_rows = config_rows if config_rows is not None else []
        self.creator_rows = creator_rows if creator_rows is not None else []
        self.calls: list[tuple[str, list[Any] | None]] = []

    async def execute(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        self.calls.append((sql, params))
        if "FROM shoutout_config" in sql:
            return self.config_rows
        if "FROM shoutout_creators" in sql:
            return self.creator_rows
        raise AssertionError(f"unexpected SQL: {sql}")


class _BoomDal:
    """Every `execute()` call raises, simulating a DB outage."""

    async def execute(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        raise RuntimeError("simulated DB outage")


class _ConfigOkCreatorBoomDal:
    """Config query succeeds; the creator-list query raises (simulates a mid-lookup outage)."""

    def __init__(self, config_rows: list[Any]) -> None:
        self.config_rows = config_rows
        self.calls: list[tuple[str, list[Any] | None]] = []

    async def execute(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        self.calls.append((sql, params))
        if "FROM shoutout_config" in sql:
            return self.config_rows
        raise RuntimeError("simulated DB outage on creator lookup")


@pytest.fixture(autouse=True)
def _isolate_singletons() -> Any:
    """Reset every module-level singleton around every test -- no cross-test leakage."""
    reset_redis_client_for_tests()
    reset_warn_rate_limit_for_tests()
    yield
    reset_redis_client_for_tests()
    reset_warn_rate_limit_for_tests()


class TestNotARaidEvent:
    async def test_non_raid_event_type_short_circuits_before_any_db_call(
        self, redis_client: Any
    ) -> None:
        event = _raid_event(event_type="message")
        result = await maybe_auto_shoutout(
            event, community=COMMUNITY, dal=_BoomDal(), redis_client=redis_client
        )
        assert result == ShoutoutDecision(
            emit=False, kind=None, target=None, reason="not_a_raid_event"
        )


class TestNoCommunity:
    async def test_none_community_short_circuits_before_any_db_call(
        self, redis_client: Any
    ) -> None:
        event = _raid_event()
        result = await maybe_auto_shoutout(
            event, community=None, dal=_BoomDal(), redis_client=redis_client
        )
        assert result == ShoutoutDecision(emit=False, kind=None, target=None, reason="no_community")

    async def test_unparseable_community_short_circuits(self, redis_client: Any) -> None:
        event = _raid_event()
        result = await maybe_auto_shoutout(
            event, community="not-a-number", dal=_BoomDal(), redis_client=redis_client
        )
        assert result.reason == "no_community"


class TestNoTarget:
    async def test_no_user_login_id_or_actor_short_circuits(self, redis_client: Any) -> None:
        event = _raid_event(user_login=None, user_id=None, actor=None)
        result = await maybe_auto_shoutout(
            event, community=COMMUNITY, dal=_BoomDal(), redis_client=redis_client
        )
        assert result == ShoutoutDecision(emit=False, kind=None, target=None, reason="no_target")

    async def test_falls_back_to_user_id_then_actor(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="disabled")])
        event = _raid_event(user_login=None, user_id="12345", actor="fallback-actor")
        result = await maybe_auto_shoutout(
            event, community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.target == "12345"

        dal2 = _FakeDal(config_rows=[_config_row(mode="disabled")])
        event2 = _raid_event(user_login=None, user_id=None, actor="Fallback-Actor")
        result2 = await maybe_auto_shoutout(
            event2, community=COMMUNITY, dal=dal2, redis_client=redis_client
        )
        assert result2.target == "fallback-actor"

    async def test_target_normalized_strip_at_and_lowercase(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="disabled")])
        event = _raid_event(user_login=" @RaiderLogin ")
        result = await maybe_auto_shoutout(
            event, community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.target == "raiderlogin"


class TestDisabledMode:
    async def test_mode_disabled_never_emits(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="disabled")])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "disabled"
        assert result.target == TARGET_LOGIN

    async def test_trigger_raid_host_false_never_emits_even_if_mode_active(
        self, redis_client: Any
    ) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="all_creators", trigger_raid_host=False)])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "disabled"

    async def test_missing_config_row_defaults_to_disabled(self, redis_client: Any) -> None:
        """No `shoutout_config` row provisioned -- defaults match the column's own DB default."""
        dal = _FakeDal(config_rows=[])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "disabled"


class TestListOnlyMode:
    async def test_listed_creator_emits(self, redis_client: Any) -> None:
        dal = _FakeDal(
            config_rows=[_config_row(mode="list_only")],
            creator_rows=[{"platform_username": TARGET_LOGIN}],
        )
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is True
        assert result.reason == "ok"
        assert result.target == TARGET_LOGIN

        creator_call = next(c for c in dal.calls if "shoutout_creators" in c[0])
        assert creator_call[1] == [COMMUNITY_ID, "twitch", TARGET_LOGIN]

    async def test_unlisted_creator_does_not_emit(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="list_only")], creator_rows=[])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "not_in_list"


class TestAllCreatorsMode:
    async def test_all_creators_always_emits_without_creator_list_lookup(
        self, redis_client: Any
    ) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="all_creators")])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is True
        assert result.reason == "ok"
        assert not any("shoutout_creators" in c[0] for c in dal.calls)


class TestRoleBasedMode:
    async def test_role_based_treated_as_all_creators_for_now(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="role_based")])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is True
        assert result.reason == "ok"
        assert not any("shoutout_creators" in c[0] for c in dal.calls)


class TestUnknownMode:
    async def test_unrecognized_mode_value_never_emits(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="something_bogus")])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "unknown_mode"


class TestKindSelection:
    async def test_vso_enabled_true_selects_video(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="all_creators", vso_enabled=True)])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.kind == "video"

    async def test_vso_enabled_false_selects_text(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="all_creators", vso_enabled=False)])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.kind == "text"


class TestNoMinViewersThreshold:
    async def test_zero_viewers_still_emits_no_threshold_in_schema(self, redis_client: Any) -> None:
        """`shoutout_config` (migration 046) has no min-viewers column -- see module docstring."""
        dal = _FakeDal(config_rows=[_config_row(mode="all_creators")])
        result = await maybe_auto_shoutout(
            _raid_event(viewers=0), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is True


class TestErrors:
    async def test_config_lookup_failure_returns_no_emit(self, redis_client: Any) -> None:
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=_BoomDal(), redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "lookup_failed"

    async def test_creator_list_lookup_failure_returns_no_emit(self, redis_client: Any) -> None:
        dal = _ConfigOkCreatorBoomDal(config_rows=[_config_row(mode="list_only")])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "lookup_failed"

    async def test_redis_failure_returns_no_emit(self, redis_client: Any) -> None:
        class _BoomRedis:
            async def get(self, key: str) -> str | None:
                raise RuntimeError("simulated redis outage")

            async def set(self, key: str, value: str, ex: int | None = None) -> None:
                raise RuntimeError("simulated redis outage")

        dal = _FakeDal(config_rows=[_config_row(mode="all_creators")])
        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=_BoomRedis()
        )
        assert result.emit is False
        assert result.reason == "lookup_failed"

    async def test_repeated_failures_warn_at_most_once_per_interval(
        self, redis_client: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="services.raid_shoutout")

        for _ in range(3):
            result = await maybe_auto_shoutout(
                _raid_event(), community=COMMUNITY, dal=_BoomDal(), redis_client=redis_client
            )
            assert result.emit is False

        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) == 1


class TestRedisCache:
    async def test_positive_cache_hit_never_queries_db(self, redis_client: Any) -> None:
        key = _config_cache_key(COMMUNITY_ID)
        payload = json.dumps(
            {"auto_shoutout_mode": "all_creators", "trigger_raid_host": True, "vso_enabled": True}
        )
        await redis_client.set(key, f"{_HIT_PREFIX}{payload}")
        dal = _BoomDal()  # would raise if ever queried

        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is True

    async def test_negative_cache_hit_never_queries_db(self, redis_client: Any) -> None:
        key = _config_cache_key(COMMUNITY_ID)
        await redis_client.set(key, _MISS_VALUE)
        dal = _BoomDal()  # would raise if ever queried

        result = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert result.emit is False
        assert result.reason == "disabled"

    async def test_table_hit_caches_positive_with_ttl(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="all_creators")])
        await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )

        key = _config_cache_key(COMMUNITY_ID)
        cached = await redis_client.get(key)
        assert cached is not None
        assert cached.startswith(_HIT_PREFIX)
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= raid_shoutout_module._CONFIG_CACHE_TTL_S

    async def test_table_miss_caches_negative_with_ttl(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[])
        await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )

        key = _config_cache_key(COMMUNITY_ID)
        assert await redis_client.get(key) == _MISS_VALUE
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= raid_shoutout_module._CONFIG_CACHE_TTL_S

    async def test_second_call_within_ttl_skips_db(self, redis_client: Any) -> None:
        dal = _FakeDal(config_rows=[_config_row(mode="all_creators")])
        await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert len(dal.calls) == 1

        result2 = await maybe_auto_shoutout(
            _raid_event(), community=COMMUNITY, dal=dal, redis_client=redis_client
        )
        assert len(dal.calls) == 1  # no second DB round trip
        assert result2.emit is True
