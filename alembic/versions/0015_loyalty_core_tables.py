"""Create the loyalty MVP core-currency tables (gh-317).

Closes gh-317: `action/interactive/loyalty_interaction_module/services/
{currency_service,gear_service,earning_config_service}.py` (and
`hub_api/services/community_loyalty.py`'s proxied contract) reference
`loyalty_balances`/`loyalty_transactions`/`loyalty_config`/gear-shop
tables, but no migration -- numbered SQL or Alembic -- ever CREATEd
them; only `loyalty_feature_toggles` exists live (018/040 only ALTER
it). This migration adds the five MVP "loyalty core" tables: per-
community earn-rate config, per-user balances, an append-only
transaction ledger, a generic points shop, and shop-item redemptions.
Gear (`loyalty_gear_items`/`loyalty_user_gear`), giveaways, and
minigames are a disjoint, much larger legacy surface the old Node/
Python `loyalty_interaction_module` also references under its own
column-naming scheme -- deliberately out of scope for this MVP cut
(follow-up issue), matching the file name (`loyalty_core_tables`, not
`loyalty_all_tables`).

Column-naming provenance: `hub_api/services/community_loyalty.py` /
`blueprints/v1/community_loyalty.py` are a pure reverse-proxy to a
separate `loyalty-interaction` deployment (`X-API-Key` service auth,
`services/community_loyalty.py`'s own docstring) -- their JSON contract
(`DEFAULT_LOYALTY_CONFIG`'s `chat_rate`/`chat_cooldown`/`gear_enabled`/
etc., spanning giveaways+games+gear) is the *downstream* service's
shape, not a binding on hub-api's own DB columns; hub-api never queries
these five tables directly today, so no existing hub-api DTO forces a
rename here. The column names below instead follow this same file's
own established ledger-table precedent for a per-community points/
token balance+transaction pair -- `bind_token_billing_tables()`'s
`community_token_balances`/`token_transactions` (`delta`/`ref`/
`balance_after`) and `bind_ai_routing_tables()`'s `ai_token_balances`/
`ai_token_transactions` (`bigint` balance/lifetime columns) -- rather
than the disused legacy Python module's own `transaction_type`/
`amount`/`reference_id` naming, which was never actually backed by a
real table in any environment.

Two typing decisions not spelled out by the column list alone:
  - `loyalty_redemptions.fulfilled_by` is `INTEGER REFERENCES
    hub_users(id) ON DELETE SET NULL` -- the admin who fulfills a
    redemption acts through hub-api's own admin UI (a hub account),
    unlike `loyalty_transactions.actor_platform_user_id` (a platform
    identity acting via chat commands) -- matches the established
    `music_policy.updated_by` / `ai_byok_keys.created_by_user_id`
    admin-FK convention elsewhere in this file.
  - `loyalty_redemptions.item_id` is `NOT NULL REFERENCES
    loyalty_shop_items(id) ON DELETE RESTRICT`, not CASCADE --
    `loyalty_shop_items.enabled` exists precisely so a shop item is
    retired via soft-delete; hard-deleting a shop item that already has
    redemption history would silently destroy the audit/financial
    trail `loyalty_transactions` is meant to preserve.

Idempotent `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`,
same style as 0008/0012/0013; `downgrade()` drops in FK-dependency
order (`loyalty_redemptions` before `loyalty_shop_items`; the other
three have no cross-table FK among themselves).

Revision ID: 0015_loyalty_core_tables
Revises: 0014_wave1a_bundle_seeds
Create Date: 2026-09-11
"""

from alembic import op

revision = "0015_loyalty_core_tables"
down_revision = "0014_wave1a_bundle_seeds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_config (
            id SERIAL PRIMARY KEY,
            community_id INTEGER NOT NULL UNIQUE
                REFERENCES communities(id) ON DELETE CASCADE,
            currency_name VARCHAR(50) NOT NULL DEFAULT 'Points',
            currency_symbol VARCHAR(16) NOT NULL DEFAULT '🪙',
            earn_chat_points INTEGER NOT NULL DEFAULT 1,
            earn_chat_cooldown_s INTEGER NOT NULL DEFAULT 60,
            earn_watch_points_per_min INTEGER NOT NULL DEFAULT 1,
            earn_watch_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            max_balance BIGINT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE loyalty_config IS "
        "'Per-community loyalty currency + earn-rate configuration (gh-317 MVP cut)'"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_balances (
            id SERIAL PRIMARY KEY,
            community_id INTEGER NOT NULL
                REFERENCES communities(id) ON DELETE CASCADE,
            platform VARCHAR(50) NOT NULL,
            platform_user_id VARCHAR(255) NOT NULL,
            balance BIGINT NOT NULL DEFAULT 0,
            lifetime_earned BIGINT NOT NULL DEFAULT 0,
            lifetime_spent BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (community_id, platform, platform_user_id)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE loyalty_balances IS "
        "'Current per-user loyalty currency balance, keyed by platform identity (gh-317 MVP cut)'"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_loyalty_balances_leaderboard
            ON loyalty_balances (community_id, balance DESC)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_transactions (
            id SERIAL PRIMARY KEY,
            community_id INTEGER NOT NULL
                REFERENCES communities(id) ON DELETE CASCADE,
            platform VARCHAR(50) NOT NULL,
            platform_user_id VARCHAR(255) NOT NULL,
            delta BIGINT NOT NULL,
            balance_after BIGINT NOT NULL,
            kind VARCHAR(32) NOT NULL
                CHECK (kind IN (
                    'earn_chat', 'earn_watch', 'admin_add', 'admin_remove',
                    'redeem', 'refund', 'transfer_in', 'transfer_out'
                )),
            ref VARCHAR(255),
            actor_platform_user_id VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE loyalty_transactions IS "
        "'Append-only loyalty currency ledger -- balance is reconstructable from balance_after (gh-317 MVP cut)'"
    )
    op.execute(
        "COMMENT ON COLUMN loyalty_transactions.ref IS "
        "'Opaque reference to the causing record -- shop item id, event id, etc.'"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_loyalty_transactions_user
            ON loyalty_transactions (community_id, platform_user_id, created_at)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_shop_items (
            id SERIAL PRIMARY KEY,
            community_id INTEGER NOT NULL
                REFERENCES communities(id) ON DELETE CASCADE,
            sku VARCHAR(64) NOT NULL,
            name VARCHAR(120) NOT NULL,
            description TEXT,
            cost BIGINT NOT NULL,
            stock INTEGER,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            requires_mod_approval BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (community_id, sku)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE loyalty_shop_items IS "
        "'Per-community points-shop catalog; NULL stock = unlimited (gh-317 MVP cut)'"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS loyalty_redemptions (
            id SERIAL PRIMARY KEY,
            community_id INTEGER NOT NULL
                REFERENCES communities(id) ON DELETE CASCADE,
            item_id INTEGER NOT NULL
                REFERENCES loyalty_shop_items(id) ON DELETE RESTRICT,
            platform VARCHAR(50) NOT NULL,
            platform_user_id VARCHAR(255) NOT NULL,
            cost BIGINT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'fulfilled', 'refunded')),
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            fulfilled_at TIMESTAMPTZ,
            fulfilled_by INTEGER REFERENCES hub_users(id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE loyalty_redemptions IS "
        "'Shop-item redemption requests + fulfillment state (gh-317 MVP cut)'"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_loyalty_redemptions_item
            ON loyalty_redemptions (item_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_loyalty_redemptions_user
            ON loyalty_redemptions (community_id, platform_user_id, created_at)
        """
    )


def downgrade() -> None:
    # FK-dependency order: loyalty_redemptions references loyalty_shop_items.
    op.execute("DROP TABLE IF EXISTS loyalty_redemptions")
    op.execute("DROP TABLE IF EXISTS loyalty_shop_items")
    op.execute("DROP TABLE IF EXISTS loyalty_transactions")
    op.execute("DROP TABLE IF EXISTS loyalty_balances")
    op.execute("DROP TABLE IF EXISTS loyalty_config")
