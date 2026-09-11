"""`services/community_loyalty.py` -- direct service-layer tests (gh-317).

Real `AsyncDAL` (file-backed sqlite, `pool_size=1`) + real `bind_loyalty_
tables()`, no mocking of the DB -- same rationale as `community_music_
queue_service`'s own coverage (exercised entirely through its blueprint
tests): this module's atomic executor-job pattern (`_sync_earn`/`_sync_
adjust`/`_sync_redeem`/`_sync_refund`/`_sync_wipe`) is worth proving
directly against a real DAL rather than only through the blueprint layer,
since a mocked DAL can't catch a `SELECT ... FOR UPDATE` / commit-ordering
bug.

`loyalty_db` (this file's own fixture, not `tests/conftest.py` --
`hub_api/services/community_loyalty.py`/`blueprints/v1/community_loyalty.
py` are the only files this PR may edit) mirrors `tests/conftest.py`'s
`music_station_db` fixture shape exactly: `bind_auth_tables()` (for
`tenants`/`communities`, which `community_in_tenant()`-style tenant checks
need even though this file never calls that helper directly) + this
feature's own `bind_loyalty_tables()`.
"""

from __future__ import annotations

from typing import Any

import pytest
from flask_core.database import AsyncDAL
from pydal import Field

from services import community_loyalty as svc
from services.errors import ApiError
from services.schema import bind_auth_tables, bind_loyalty_tables

TENANT_SLUG = "acme-corp"


@pytest.fixture
def loyalty_db(tmp_path: Any) -> Any:
    """`(async_dal, community_id)` -- file-backed `AsyncDAL` with loyalty + auth tables bound."""
    async_dal = AsyncDAL(f"sqlite://{tmp_path / 'loyalty_service_test.db'}", pool_size=1)
    dal = async_dal.dal
    dal.define_table(
        "tenants",
        Field("slug", unique=True),
        Field("display_name"),
        Field("logo_url"),
        Field("is_global", "boolean", default=False),
        Field("is_active", "boolean", default=True),
        Field("config", "json"),
    )
    bind_auth_tables(dal, migrate=True)
    bind_loyalty_tables(dal, migrate=True)
    tenant_id = dal.tenants.insert(slug=TENANT_SLUG, display_name="Acme Corp", is_active=True)
    dal.commit()
    community_id = dal.communities.insert(
        name="test-community", tenant_id=tenant_id, is_active=True
    )
    dal.commit()
    for table_name in dal.tables:
        dal(dal[table_name]).count()
    yield async_dal, community_id
    dal.close()


class TestConfig:
    async def test_get_config_creates_default_row(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        config = await svc.get_config(async_dal, dal, community_id=community_id)
        assert config.enabled is True
        assert config.currency_name == "Points"
        assert config.max_balance is None

    async def test_get_config_is_idempotent(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        first = await svc.get_config(async_dal, dal, community_id=community_id)
        second = await svc.get_config(async_dal, dal, community_id=community_id)
        assert first.community_id == second.community_id
        rows = await async_dal.select_async(dal(dal.loyalty_config.community_id == community_id))
        assert len(rows) == 1

    async def test_set_config_partial_update(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.get_config(async_dal, dal, community_id=community_id)
        updated = await svc.set_config(
            async_dal, dal, community_id=community_id, currency_name="Gems", max_balance=500
        )
        assert updated.currency_name == "Gems"
        assert updated.max_balance == 500
        assert updated.currency_symbol == "\U0001fa99"  # untouched

    async def test_set_config_no_fields_is_bad_request(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        with pytest.raises(ApiError, match="No config fields"):
            await svc.set_config(async_dal, dal, community_id=community_id)

    async def test_set_config_negative_points_is_bad_request(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        with pytest.raises(ApiError):
            await svc.set_config(async_dal, dal, community_id=community_id, earn_chat_points=-1)


class TestBalance:
    async def test_get_balance_defaults_to_zero_without_insert(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        balance = await svc.get_balance(
            async_dal, dal, community_id=community_id, platform="twitch", platform_user_id="u1"
        )
        assert balance.balance == 0
        rows = await async_dal.select_async(dal(dal.loyalty_balances.community_id == community_id))
        assert len(rows) == 0


class TestEarn:
    async def test_earn_credits_points_and_writes_transaction(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        result = await svc.earn(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            kind="earn_chat",
            points=10,
        )
        assert result.applied_delta == 10
        assert result.balance.balance == 10
        rows = await async_dal.select_async(
            dal(dal.loyalty_transactions.community_id == community_id)
        )
        assert len(rows) == 1
        assert rows.first().kind == "earn_chat"
        assert rows.first().delta == 10

    async def test_earn_respects_max_balance_clamp(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.set_config(async_dal, dal, community_id=community_id, max_balance=15)
        await svc.earn(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            kind="earn_chat",
            points=10,
        )
        result = await svc.earn(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            kind="earn_chat",
            points=10,
        )
        assert result.applied_delta == 5  # clamped: 10 + 10 -> capped at 15
        assert result.balance.balance == 15

    async def test_earn_unknown_kind_is_bad_request(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        with pytest.raises(ApiError, match="unknown earn kind"):
            await svc.earn(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                kind="bogus",
                points=10,
            )

    async def test_earn_non_positive_points_is_bad_request(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        with pytest.raises(ApiError, match="positive"):
            await svc.earn(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                kind="earn_chat",
                points=0,
            )

    async def test_earn_rejected_when_loyalty_disabled(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.set_config(async_dal, dal, community_id=community_id, enabled=False)
        with pytest.raises(ApiError, match="loyalty is disabled here"):
            await svc.earn(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                kind="earn_chat",
                points=10,
            )


class TestAdjust:
    async def test_adjust_add_points(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        balance = await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=50,
            actor="1",
            note="admin grant",
        )
        assert balance.balance == 50
        assert balance.lifetime_earned == 50

    async def test_adjust_floors_at_zero_never_below(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=10,
            actor="1",
        )
        balance = await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=-100,
            actor="1",
            allow_negative=True,
        )
        assert balance.balance == 0

    async def test_adjust_rejects_negative_overshoot_by_default(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=10,
            actor="1",
        )
        with pytest.raises(ApiError, match="insufficient points"):
            await svc.adjust(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                delta=-100,
                actor="1",
            )

    async def test_adjust_zero_delta_is_bad_request(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        with pytest.raises(ApiError, match="non-zero"):
            await svc.adjust(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                delta=0,
                actor="1",
            )


class TestLeaderboard:
    async def test_leaderboard_orders_by_balance_descending(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="low",
            delta=5,
            actor="1",
        )
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="high",
            delta=50,
            actor="1",
        )
        entries = await svc.leaderboard(async_dal, dal, community_id=community_id, limit=10)
        assert [e.platform_user_id for e in entries] == ["high", "low"]

    async def test_leaderboard_respects_limit(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        for i in range(5):
            await svc.adjust(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id=f"u{i}",
                delta=i + 1,
                actor="1",
            )
        entries = await svc.leaderboard(async_dal, dal, community_id=community_id, limit=2)
        assert len(entries) == 2


class TestShopItems:
    async def test_upsert_item_creates_then_updates(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        created = await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Cool Hat", cost=100, stock=5
        )
        assert created.stock == 5
        updated = await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Cool Hat", cost=150, stock=3
        )
        assert updated.id == created.id
        assert updated.cost == 150
        assert updated.stock == 3

    async def test_list_items_enabled_only_filters(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=10, enabled=True
        )
        await svc.upsert_item(
            async_dal,
            dal,
            community_id=community_id,
            sku="cape",
            name="Cape",
            cost=10,
            enabled=False,
        )
        items = await svc.list_items(async_dal, dal, community_id=community_id, enabled_only=True)
        assert [i.sku for i in items] == ["hat"]


class TestRedeem:
    async def test_redeem_atomic_debit_and_stock_decrement(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=100,
            actor="1",
        )
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=40, stock=2
        )
        redemption = await svc.redeem(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            sku="hat",
        )
        assert redemption.status == "fulfilled"
        assert redemption.cost == 40
        balance = await svc.get_balance(
            async_dal, dal, community_id=community_id, platform="twitch", platform_user_id="u1"
        )
        assert balance.balance == 60
        items = await svc.list_items(async_dal, dal, community_id=community_id)
        assert items[0].stock == 1

    async def test_redeem_requires_mod_approval_is_pending(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=100,
            actor="1",
        )
        await svc.upsert_item(
            async_dal,
            dal,
            community_id=community_id,
            sku="vip",
            name="VIP",
            cost=40,
            requires_mod_approval=True,
        )
        redemption = await svc.redeem(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            sku="vip",
        )
        assert redemption.status == "pending"

    async def test_redeem_insufficient_points_message(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=100
        )
        with pytest.raises(ApiError, match=r"not enough points \(have 0, need 100\)"):
            await svc.redeem(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                sku="hat",
            )

    async def test_redeem_out_of_stock_message(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=100,
            actor="1",
        )
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=10, stock=0
        )
        with pytest.raises(ApiError, match="item out of stock"):
            await svc.redeem(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                sku="hat",
            )

    async def test_redeem_unknown_item_message(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        with pytest.raises(ApiError, match="unknown item 'nope'"):
            await svc.redeem(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                sku="nope",
            )

    async def test_redeem_disabled_item_is_unknown_item(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=10, enabled=False
        )
        with pytest.raises(ApiError, match="unknown item 'hat'"):
            await svc.redeem(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                sku="hat",
            )

    async def test_redeem_rejected_when_loyalty_disabled(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.set_config(async_dal, dal, community_id=community_id, enabled=False)
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=10
        )
        with pytest.raises(ApiError, match="loyalty is disabled here"):
            await svc.redeem(
                async_dal,
                dal,
                community_id=community_id,
                platform="twitch",
                platform_user_id="u1",
                sku="hat",
            )


class TestRefund:
    async def test_refund_restores_balance_and_stock(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=100,
            actor="1",
        )
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=40, stock=2
        )
        redemption = await svc.redeem(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            sku="hat",
        )
        refunded = await svc.refund(
            async_dal, dal, community_id=community_id, redemption_id=redemption.id
        )
        assert refunded.status == "refunded"
        balance = await svc.get_balance(
            async_dal, dal, community_id=community_id, platform="twitch", platform_user_id="u1"
        )
        assert balance.balance == 100
        items = await svc.list_items(async_dal, dal, community_id=community_id)
        assert items[0].stock == 2

    async def test_refund_unknown_redemption_is_not_found(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        with pytest.raises(ApiError, match="not found"):
            await svc.refund(async_dal, dal, community_id=community_id, redemption_id=9999)

    async def test_double_refund_is_conflict(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=100,
            actor="1",
        )
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="hat", name="Hat", cost=40
        )
        redemption = await svc.redeem(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            sku="hat",
        )
        await svc.refund(async_dal, dal, community_id=community_id, redemption_id=redemption.id)
        with pytest.raises(ApiError, match="already refunded"):
            await svc.refund(async_dal, dal, community_id=community_id, redemption_id=redemption.id)


class TestStatsAndWipe:
    async def test_get_stats_aggregates_balances(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=10,
            actor="1",
        )
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u2",
            delta=30,
            actor="1",
        )
        stats = await svc.get_stats(async_dal, dal, community_id=community_id)
        assert stats.total_users == 2
        assert stats.total_currency == 40
        assert stats.average_balance == 20.0

    async def test_get_stats_empty_community(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        stats = await svc.get_stats(async_dal, dal, community_id=community_id)
        assert stats.total_users == 0
        assert stats.average_balance == 0.0

    async def test_wipe_zeroes_balances_and_ledgers_each(self, loyalty_db: Any) -> None:
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=10,
            actor="1",
        )
        affected = await svc.wipe(async_dal, dal, community_id=community_id)
        assert affected == 1
        balance = await svc.get_balance(
            async_dal, dal, community_id=community_id, platform="twitch", platform_user_id="u1"
        )
        assert balance.balance == 0


class TestContractFields:
    """Regression tests for gh-317 contract: verify new fields in responses."""

    async def test_balance_includes_currency_name_and_symbol(self, loyalty_db: Any) -> None:
        # regression: gh-317 contract
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.set_config(
            async_dal, dal, community_id=community_id, currency_name="Gems", currency_symbol="💎"
        )
        balance = await svc.get_balance(
            async_dal, dal, community_id=community_id, platform="twitch", platform_user_id="u1"
        )
        assert hasattr(balance, "currency_name")
        assert hasattr(balance, "currency_symbol")
        assert balance.currency_name == "Gems"
        assert balance.currency_symbol == "💎"

    async def test_balance_defaults_currency_to_points(self, loyalty_db: Any) -> None:
        # regression: gh-317 contract
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        balance = await svc.get_balance(
            async_dal, dal, community_id=community_id, platform="twitch", platform_user_id="u1"
        )
        assert balance.currency_name == "Points"
        assert balance.currency_symbol == "\U0001fa99"

    async def test_adjust_includes_currency_name_and_symbol(self, loyalty_db: Any) -> None:
        # regression: gh-317 contract
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.set_config(
            async_dal, dal, community_id=community_id, currency_name="Gold", currency_symbol="🏆"
        )
        balance = await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=25,
            actor="1",
        )
        assert balance.currency_name == "Gold"
        assert balance.currency_symbol == "🏆"

    async def test_redeem_includes_item_name_and_currency(self, loyalty_db: Any) -> None:
        # regression: gh-317 contract
        async_dal, community_id = loyalty_db
        dal = async_dal.dal
        await svc.set_config(
            async_dal, dal, community_id=community_id, currency_name="Coins", currency_symbol="💰"
        )
        await svc.adjust(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            delta=100,
            actor="1",
        )
        await svc.upsert_item(
            async_dal, dal, community_id=community_id, sku="sword", name="Iron Sword", cost=50
        )
        redemption = await svc.redeem(
            async_dal,
            dal,
            community_id=community_id,
            platform="twitch",
            platform_user_id="u1",
            sku="sword",
        )
        assert hasattr(redemption, "item_name")
        assert hasattr(redemption, "currency_name")
        assert hasattr(redemption, "currency_symbol")
        assert redemption.item_name == "Iron Sword"
        assert redemption.cost == 50
        assert redemption.currency_name == "Coins"
        assert redemption.currency_symbol == "💰"
