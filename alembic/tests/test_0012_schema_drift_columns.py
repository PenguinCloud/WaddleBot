"""Regression test for 0012_schema_drift_columns.

Same harness convention as `test_0010_music_bot_token_ref.py` -- this
repo has no pytest-level fixture that runs Alembic against a real
Postgres (`op.execute()`-based migrations aren't exercised end-to-end in
CI; see that file's own docstring). These tests instead: (a) mock
`alembic.op.execute` and assert the exact set of `ADD COLUMN IF NOT
EXISTS`/`CREATE TABLE IF NOT EXISTS` targets 0012's `upgrade()` emits,
locking in coverage so a future edit can't silently drop a table/column
without the test noticing; (b) cross-check that every (table, column)
0012 adds is actually referenced by a `Field()` call somewhere in
`hub_api/services/schema.py` (static AST parse, zero DB/runtime
dependency) -- guards against the migration drifting away from what
pydal actually needs.

The real upgrade+downgrade+re-upgrade round-trip against a throwaway
Postgres (via this repo's own `migrations/Dockerfile` image) WAS run for
this migration during development -- real output, not asserted here
because no DB fixture exists in this repo's pytest suite to reproduce it
in CI without adding new infrastructure (out of scope for this PR, which
is restricted to `alembic/versions/` + migration tests).
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path
from unittest.mock import patch

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent / "versions" / "0012_schema_drift_columns.py"
)
_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "hub_api" / "services" / "schema.py"
)

# Every (table, column) this migration's upgrade() must add via
# ADD COLUMN IF NOT EXISTS to an EXISTING table.
EXPECTED_ADDED_COLUMNS = {
    ("hub_users", "email_verification_expires"),
    ("platform_configs", "enabled"),
    ("communities", "about_extended"),
    ("communities", "social_links"),
    ("communities", "website_url"),
    ("communities", "discord_invite_url"),
    ("communities", "visibility"),
    ("communities", "is_premium"),
    ("communities", "seat_limit"),
    ("commands", "module_url"),
    ("commands", "platforms"),
    ("community_members", "created_at"),
    ("community_members", "last_activity"),
    ("community_members", "removed_at"),
    ("community_members", "removed_by"),
    ("community_members", "removal_reason"),
    ("hub_modules", "is_featured"),
    ("hub_module_installations", "module_name"),
    ("permission_scopes", "scope_key"),
    ("permission_scopes", "display_name"),
    ("vendor_discount_codes", "description"),
    ("community_vendor_installations", "module_id"),
    ("community_vendor_installations", "status"),
    ("community_vendor_installations", "last_active_at"),
    ("community_vendor_installations", "uninstalled_at"),
    ("community_vendor_installations", "discount_code_id"),
    ("vendor_payments", "module_id"),
    ("vendor_payments", "seller_id"),
    ("vendor_payments", "status"),
    ("vendor_payments", "amount_cents"),
    ("vendor_payments", "paid_at"),
}

# Every table this migration's upgrade() must create via
# CREATE TABLE IF NOT EXISTS.
EXPECTED_NEW_TABLES = {
    "support_ticket_categories",
    "support_tickets",
    "support_ticket_comments",
    "platform_admins",
    "oauth_state_tokens",
    "oauth_tokens",
    "collector_modules",
    "community_music_providers",
    "community_music_settings",
    "community_radio_stations",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_0012_schema_drift_columns", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pydal_fields() -> dict[str, set[str]]:
    """Static AST union of every Field() bound per table in schema.py.

    Mirrors the drift-audit extraction methodology: runtime replay is
    unsafe here because `bind_tenant_tables()` calls `dal.define_table(
    "communities", ..., redefine=True)` with only a subset of fields --
    `redefine=True` replaces the field list wholesale rather than merging
    by name, so a runtime bind is call-order-dependent. AST union across
    every `define_table()` call for a given table name sidesteps that.
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
    def test_chains_directly_off_0011_communities_license_cols(self, migration) -> None:
        assert migration.revision == "0012_schema_drift_columns"
        assert migration.down_revision == "0011_communities_license_cols"

    def test_revision_id_fits_alembic_version_num_varchar32(self, migration) -> None:
        # alembic_version.version_num is VARCHAR(32) -- a too-long revision
        # id fails silently truncated or raises at stamp time.
        assert len(migration.revision) <= 32


class TestUpgradeAddsEveryMissingColumnAndTable:
    def test_every_expected_column_gets_an_add_column_if_not_exists(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)

        for table, column in EXPECTED_ADDED_COLUMNS:
            pattern = (
                rf"ALTER TABLE {table}\b.*?ADD COLUMN IF NOT EXISTS {column}\b"
            )
            assert re.search(pattern, sql, re.DOTALL), (
                f"upgrade() missing 'ADD COLUMN IF NOT EXISTS {column}' on {table}"
            )

    def test_every_expected_table_gets_a_create_table_if_not_exists(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)

        for table in EXPECTED_NEW_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {table} " in sql or (
                f"CREATE TABLE IF NOT EXISTS {table}\n" in sql
                or f"CREATE TABLE IF NOT EXISTS {table}(" in sql
            ), f"upgrade() missing 'CREATE TABLE IF NOT EXISTS {table}'"

    def test_no_not_null_or_default_on_backfilled_columns(self, migration) -> None:
        """Existing tables may already have rows -- NOT NULL/DEFAULT on a
        bare ADD COLUMN can fail or silently rewrite every row; every
        added column here must stay nullable, no default (critical-rules.md
        Dependency Pinning is unrelated but the same "never break existing
        rows" principle 0011 establishes for this migration family)."""
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)
        assert "NOT NULL" not in sql.upper()
        assert " DEFAULT " not in sql.upper()


class TestDowngradeRemovesEverythingUpgradeAdded:
    def test_every_expected_column_gets_dropped(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.downgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)

        for _table, column in EXPECTED_ADDED_COLUMNS:
            assert f"DROP COLUMN IF EXISTS {column}" in sql, (
                f"downgrade() missing 'DROP COLUMN IF EXISTS {column}'"
            )

    def test_every_expected_table_gets_dropped(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.downgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)

        for table in EXPECTED_NEW_TABLES:
            assert f"DROP TABLE IF EXISTS {table}" in sql, (
                f"downgrade() missing 'DROP TABLE IF EXISTS {table}'"
            )


class TestAddedColumnsMatchPydalSchema:
    """Cross-check against `hub_api/services/schema.py` itself -- every
    column this migration adds must be a real pydal-bound field (catches
    a typo'd column name or a column added for the wrong table)."""

    def test_every_added_column_is_pydal_bound(self, pydal_fields) -> None:
        for table, column in EXPECTED_ADDED_COLUMNS:
            assert table in pydal_fields, f"{table} is not bound anywhere in schema.py"
            assert column in pydal_fields[table], (
                f"schema.py's {table} table has no Field({column!r}, ...) -- "
                "migration is adding a column pydal doesn't reference"
            )

    def test_every_new_table_is_pydal_bound(self, pydal_fields) -> None:
        for table in EXPECTED_NEW_TABLES:
            assert table in pydal_fields, f"{table} is not bound anywhere in schema.py"
