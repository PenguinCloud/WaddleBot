"""Tests for `services.command_alias_store` -- `bot_process`'s alias-lookup DB+Redis store.

`dal`/`redis_client` are always passed explicitly (this module's own
test-injection override params) except for the small set of
`TestDefaultResolution` cases that exercise the real
`flask_core.get_bundle_dal()`/singleton-Redis-client fallback paths
`bot_process._expand_alias` itself relies on.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from flask_core.bundle_runtime import reset_bundle_dal_for_tests, set_bundle_dal

from services import command_alias_store as store_module
from services.command_alias_store import (
    CommandAlias,
    _cache_key,
    invalidate_alias,
    list_aliases,
    reset_redis_client_for_tests,
    reset_warn_rate_limit_for_tests,
    resolve_alias,
)

COMMUNITY_ID = 4
ALIAS = "xx"
TARGET = "songrequest"


class _FakeDal:
    """Records every `execute()` call; returns a preloaded row set for that SQL."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = rows if rows is not None else []
        self.calls: list[tuple[str, list[Any] | None]] = []

    async def execute(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        self.calls.append((sql, params))
        return self._rows


class _BoomDal:
    """Every `execute()` call raises, simulating a DB outage."""

    async def execute(self, sql: str, params: list[Any] | None = None) -> list[Any]:
        raise RuntimeError("simulated DB outage")


class _BoomRedis:
    """Every method raises, simulating a Redis outage."""

    async def get(self, key: str) -> str | None:
        raise RuntimeError("simulated redis outage")

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        raise RuntimeError("simulated redis outage")

    async def delete(self, key: str) -> None:
        raise RuntimeError("simulated redis outage")


@pytest.fixture(autouse=True)
def _isolate_singletons() -> Any:
    """Reset every module-level singleton around every test -- no cross-test leakage."""
    reset_bundle_dal_for_tests()
    reset_redis_client_for_tests()
    reset_warn_rate_limit_for_tests()
    yield
    reset_bundle_dal_for_tests()
    reset_redis_client_for_tests()
    reset_warn_rate_limit_for_tests()


class TestCacheKey:
    def test_key_shape(self) -> None:
        key = _cache_key(community_id=COMMUNITY_ID, alias=ALIAS)
        assert key == f"cmdalias:{COMMUNITY_ID}:{ALIAS}"


class TestResolveAliasRedisHit:
    async def test_positive_cache_hit_never_queries_db(self, redis_client: Any) -> None:
        key = _cache_key(community_id=COMMUNITY_ID, alias=ALIAS)
        await redis_client.set(key, f"1:{TARGET}")
        dal = _FakeDal(rows=[{"alias": ALIAS, "target_command": "wrong"}])  # would be wrong if hit

        result = await resolve_alias(
            community_id=COMMUNITY_ID, alias=ALIAS, dal=dal, redis_client=redis_client
        )

        assert result == CommandAlias(alias=ALIAS, target_command=TARGET, community_id=COMMUNITY_ID)
        assert dal.calls == []

    async def test_negative_cache_hit_never_queries_db(self, redis_client: Any) -> None:
        key = _cache_key(community_id=COMMUNITY_ID, alias=ALIAS)
        await redis_client.set(key, "0")
        dal = _FakeDal(rows=[{"alias": ALIAS, "target_command": TARGET}])  # would be wrong if hit

        result = await resolve_alias(
            community_id=COMMUNITY_ID, alias=ALIAS, dal=dal, redis_client=redis_client
        )

        assert result is None
        assert dal.calls == []


class TestResolveAliasTableFallback:
    async def test_table_hit_caches_positive_with_ttl(self, redis_client: Any) -> None:
        dal = _FakeDal(rows=[{"alias": ALIAS, "target_command": TARGET}])

        result = await resolve_alias(
            community_id=COMMUNITY_ID, alias=ALIAS, dal=dal, redis_client=redis_client
        )

        assert result == CommandAlias(alias=ALIAS, target_command=TARGET, community_id=COMMUNITY_ID)
        assert dal.calls[0][1] == [COMMUNITY_ID, ALIAS]
        key = _cache_key(community_id=COMMUNITY_ID, alias=ALIAS)
        assert await redis_client.get(key) == f"1:{TARGET}"
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= store_module._POSITIVE_TTL_S

    async def test_table_miss_caches_negative_with_ttl(self, redis_client: Any) -> None:
        dal = _FakeDal(rows=[])

        result = await resolve_alias(
            community_id=COMMUNITY_ID, alias=ALIAS, dal=dal, redis_client=redis_client
        )

        assert result is None
        key = _cache_key(community_id=COMMUNITY_ID, alias=ALIAS)
        assert await redis_client.get(key) == "0"
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= store_module._NEGATIVE_TTL_S


class TestResolveAliasCommunityNone:
    async def test_none_community_id_skips_lookup_entirely(self, redis_client: Any) -> None:
        dal = _FakeDal(rows=[{"alias": ALIAS, "target_command": TARGET}])

        result = await resolve_alias(
            community_id=None, alias=ALIAS, dal=dal, redis_client=redis_client
        )

        assert result is None
        assert dal.calls == []


class TestResolveAliasErrors:
    async def test_db_failure_returns_none(self, redis_client: Any) -> None:
        result = await resolve_alias(
            community_id=COMMUNITY_ID, alias=ALIAS, dal=_BoomDal(), redis_client=redis_client
        )
        assert result is None

    async def test_redis_failure_returns_none(self) -> None:
        dal = _FakeDal(rows=[{"alias": ALIAS, "target_command": TARGET}])
        result = await resolve_alias(
            community_id=COMMUNITY_ID, alias=ALIAS, dal=dal, redis_client=_BoomRedis()
        )
        assert result is None

    async def test_repeated_failures_warn_at_most_once_per_interval(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger="services.command_alias_store")
        dal = _BoomDal()

        for _ in range(3):
            result = await resolve_alias(
                community_id=COMMUNITY_ID, alias=ALIAS, dal=dal, redis_client=_BoomRedis()
            )
            assert result is None

        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warn_records) == 1


class TestInvalidateAlias:
    async def test_deletes_cache_key(self, redis_client: Any) -> None:
        key = _cache_key(community_id=COMMUNITY_ID, alias=ALIAS)
        await redis_client.set(key, f"1:{TARGET}")

        await invalidate_alias(community_id=COMMUNITY_ID, alias=ALIAS, redis_client=redis_client)

        assert await redis_client.get(key) is None


class TestListAliases:
    async def test_returns_ordered_aliases(self) -> None:
        dal = _FakeDal(
            rows=[
                {"alias": "aa", "target_command": "announce giveaway"},
                {"alias": "sr", "target_command": "songrequest"},
            ]
        )

        result = await list_aliases(community_id=COMMUNITY_ID, dal=dal)

        assert result == [
            CommandAlias(alias="aa", target_command="announce giveaway", community_id=COMMUNITY_ID),
            CommandAlias(alias="sr", target_command="songrequest", community_id=COMMUNITY_ID),
        ]
        assert dal.calls[0][1] == [COMMUNITY_ID]

    async def test_no_aliases_returns_empty_list(self) -> None:
        dal = _FakeDal(rows=[])
        result = await list_aliases(community_id=COMMUNITY_ID, dal=dal)
        assert result == []


class TestDefaultResolution:
    """No `dal`/`redis_client` override -- the real `bot_process` calling convention."""

    async def test_resolve_alias_uses_bound_dal_and_singleton_redis_by_default(
        self, redis_client: Any
    ) -> None:
        store_module._redis_client = redis_client
        dal = _FakeDal(rows=[{"alias": ALIAS, "target_command": TARGET}])
        set_bundle_dal(dal)

        result = await resolve_alias(community_id=COMMUNITY_ID, alias=ALIAS)

        assert result == CommandAlias(alias=ALIAS, target_command=TARGET, community_id=COMMUNITY_ID)

    async def test_list_aliases_uses_bound_dal_by_default(self) -> None:
        dal = _FakeDal(rows=[{"alias": ALIAS, "target_command": TARGET}])
        set_bundle_dal(dal)

        result = await list_aliases(community_id=COMMUNITY_ID)

        assert result == [
            CommandAlias(alias=ALIAS, target_command=TARGET, community_id=COMMUNITY_ID)
        ]
