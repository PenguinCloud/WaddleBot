"""Regression test for 0015_loyalty_core_tables (gh-317).

Same harness convention as `test_0012_schema_drift_columns.py`/
`test_0013_music_policy_youtube_labels.py` -- this repo has no
pytest-level fixture that runs Alembic against a real Postgres
(`op.execute()`-based migrations aren't exercised end-to-end in CI).
These tests: (a) mock `alembic.op.execute` and assert the exact
`CREATE TABLE IF NOT EXISTS`/`CREATE INDEX IF NOT EXISTS` targets
0015's `upgrade()` emits, and that `downgrade()` drops every one of
them in FK-safe order; (b) cross-check that every column this
migration creates is actually referenced by a `Field()` call on the
matching table in `hub_api/services/schema.py`'s new
`bind_loyalty_tables()` (static AST parse, zero DB/runtime dependency)
-- guards against the migration drifting away from what pydal
actually needs, mirroring 0012's own `_pydal_fields()` methodology.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path
from unittest.mock import patch

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "versions" / "0015_loyalty_core_tables.py"
)
_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "hub_api" / "services" / "schema.py"

EXPECTED_TABLES = {
    "loyalty_config",
    "loyalty_balances",
    "loyalty_transactions",
    "loyalty_shop_items",
    "loyalty_redemptions",
}

# Every (table, column) 0015's upgrade() must create.
EXPECTED_COLUMNS: dict[str, set[str]] = {
    "loyalty_config": {
        "community_id",
        "currency_name",
        "currency_symbol",
        "earn_chat_points",
        "earn_chat_cooldown_s",
        "earn_watch_points_per_min",
        "earn_watch_enabled",
        "max_balance",
        "enabled",
        "updated_at",
    },
    "loyalty_balances": {
        "community_id",
        "platform",
        "platform_user_id",
        "balance",
        "lifetime_earned",
        "lifetime_spent",
        "updated_at",
    },
    "loyalty_transactions": {
        "community_id",
        "platform",
        "platform_user_id",
        "delta",
        "balance_after",
        "kind",
        "ref",
        "actor_platform_user_id",
        "created_at",
    },
    "loyalty_shop_items": {
        "community_id",
        "sku",
        "name",
        "description",
        "cost",
        "stock",
        "enabled",
        "requires_mod_approval",
        "created_at",
        "updated_at",
    },
    "loyalty_redemptions": {
        "community_id",
        "item_id",
        "platform",
        "platform_user_id",
        "cost",
        "status",
        "note",
        "created_at",
        "fulfilled_at",
        "fulfilled_by",
    },
}

EXPECTED_INDEXES = {
    "idx_loyalty_balances_leaderboard",
    "idx_loyalty_transactions_user",
    "idx_loyalty_redemptions_item",
    "idx_loyalty_redemptions_user",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_0015_loyalty_core_tables", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pydal_fields() -> dict[str, set[str]]:
    """Static AST union of every Field() bound per table in schema.py.

    Mirrors 0012's `_pydal_fields()` extraction methodology (see that
    test's own docstring for why a runtime replay is unsafe here).
    """
    tree = ast.parse(_SCHEMA_PATH.read_text(), filename=str(_SCHEMA_PATH))
    tables: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "define_table"):
            continue
        if not node.args:
            continue
        table_arg = node.args[0]
        if not (isinstance(table_arg, ast.Constant) and isinstance(table_arg.value, str)):
            continue
        fields = tables.setdefault(table_arg.value, set())
        for arg in node.args[1:]:
            if not (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "Field"
            ):
                continue
            if not arg.args:
                continue
            name_node = arg.args[0]
            if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
                fields.add(name_node.value)
    return tables


@pytest.fixture
def migration():
    return _load_migration()


@pytest.fixture(scope="module")
def pydal_fields() -> dict[str, set[str]]:
    return _pydal_fields()


class TestMigrationMetadata:
    def test_chains_directly_off_0014_wave1a_bundle_seeds(self, migration) -> None:
        assert migration.revision == "0015_loyalty_core_tables"
        assert migration.down_revision == "0014_wave1a_bundle_seeds"

    def test_revision_id_fits_alembic_version_num_varchar32(self, migration) -> None:
        # alembic_version.version_num is VARCHAR(32) -- a too-long revision
        # id fails silently truncated or raises at stamp time.
        assert len(migration.revision) <= 32


class TestUpgradeCreatesEveryTable:
    def test_every_expected_table_gets_a_create_table_if_not_exists(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)

        for table in EXPECTED_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {table} " in sql or (
                f"CREATE TABLE IF NOT EXISTS {table}\n" in sql
                or f"CREATE TABLE IF NOT EXISTS {table}(" in sql
            ), f"upgrade() missing 'CREATE TABLE IF NOT EXISTS {table}'"

    def test_every_expected_column_appears_in_its_table_definition(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        calls = [call.args[0] for call in mock_execute.call_args_list]

        for table, columns in EXPECTED_COLUMNS.items():
            stmt = next(
                (c for c in calls if f"CREATE TABLE IF NOT EXISTS {table} " in c), None
            )
            assert stmt is not None, f"no CREATE TABLE statement captured for {table}"
            for column in columns:
                assert re.search(rf"\b{column}\b", stmt), (
                    f"CREATE TABLE {table} is missing column {column!r}"
                )

    def test_every_expected_index_gets_a_create_index_if_not_exists(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)

        for index in EXPECTED_INDEXES:
            assert f"CREATE INDEX IF NOT EXISTS {index}" in sql, (
                f"upgrade() missing 'CREATE INDEX IF NOT EXISTS {index}'"
            )

    def test_unique_constraints_present(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)
        assert "UNIQUE (community_id, platform, platform_user_id)" in sql
        assert "UNIQUE (community_id, sku)" in sql


class TestDowngradeRemovesEverythingInFkSafeOrder:
    def test_every_expected_table_gets_dropped(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.downgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)

        for table in EXPECTED_TABLES:
            assert f"DROP TABLE IF EXISTS {table}" in sql, (
                f"downgrade() missing 'DROP TABLE IF EXISTS {table}'"
            )

    def test_redemptions_dropped_before_shop_items(self, migration) -> None:
        # loyalty_redemptions.item_id REFERENCES loyalty_shop_items(id) --
        # must be dropped first or the DROP TABLE on shop_items fails.
        with patch("alembic.op.execute") as mock_execute:
            migration.downgrade()

        calls = [call.args[0] for call in mock_execute.call_args_list]
        redemptions_idx = next(
            i for i, c in enumerate(calls) if "DROP TABLE IF EXISTS loyalty_redemptions" in c
        )
        shop_items_idx = next(
            i for i, c in enumerate(calls) if "DROP TABLE IF EXISTS loyalty_shop_items" in c
        )
        assert redemptions_idx < shop_items_idx


class TestCreatedTablesMatchPydalSchema:
    """Cross-check against `hub_api/services/schema.py` itself -- every
    table/column this migration creates must be a real pydal-bound
    field on `bind_loyalty_tables()` (catches a typo'd column name or a
    column added for the wrong table)."""

    def test_every_table_is_pydal_bound(self, pydal_fields) -> None:
        for table in EXPECTED_TABLES:
            assert table in pydal_fields, f"{table} is not bound anywhere in schema.py"

    def test_every_column_is_pydal_bound(self, pydal_fields) -> None:
        for table, columns in EXPECTED_COLUMNS.items():
            for column in columns:
                assert column in pydal_fields[table], (
                    f"schema.py's {table} table has no Field({column!r}, ...) -- "
                    "migration is creating a column pydal doesn't reference"
                )

    def test_pydal_has_no_extra_untested_columns(self, pydal_fields) -> None:
        """Guards the inverse drift direction -- a Field() added to
        bind_loyalty_tables() without a matching migration column."""
        for table, columns in EXPECTED_COLUMNS.items():
            assert pydal_fields[table] == columns, (
                f"{table}: schema.py Field() set {pydal_fields[table]} != "
                f"migration column set {columns}"
            )
