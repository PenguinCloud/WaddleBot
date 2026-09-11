"""Regression test for 0013_music_policy_yt_labels (gh-313).

Same harness convention as `test_0011_communities_license_columns.py`/
`test_0012_schema_drift_columns.py` -- this repo has no pytest-level
fixture that runs Alembic against a real Postgres (`op.execute()`-based
migrations aren't exercised end-to-end in CI). These tests: (a) mock
`alembic.op.execute` and assert the exact `ADD COLUMN IF NOT EXISTS`/
`DROP COLUMN IF EXISTS` targets 0013's `upgrade()`/`downgrade()` emit;
(b) cross-check that the added column is actually referenced by a
`Field()` call on `music_policy` in `hub_api/services/schema.py` (static
AST parse, zero DB/runtime dependency) -- guards against the migration
drifting away from what pydal actually needs.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "versions"
    / "0013_music_policy_youtube_labels.py"
)
_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "hub_api" / "services" / "schema.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_0013_music_policy_youtube_labels", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pydal_fields_for_table(table_name: str) -> set[str]:
    """Static AST union of every Field() bound to `table_name` in schema.py.

    Mirrors 0012's drift-audit extraction methodology (see that test's own
    `_pydal_fields()` docstring for why a runtime replay is unsafe here).
    """
    tree = ast.parse(_SCHEMA_PATH.read_text(), filename=str(_SCHEMA_PATH))
    fields: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "define_table"):
            continue
        if not node.args:
            continue
        table_arg = node.args[0]
        if not (isinstance(table_arg, ast.Constant) and table_arg.value == table_name):
            continue
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
    return fields


@pytest.fixture
def migration():
    return _load_migration()


class TestMigrationMetadata:
    def test_chains_directly_off_0012_schema_drift_columns(self, migration) -> None:
        assert migration.revision == "0013_music_policy_yt_labels"
        assert migration.down_revision == "0012_schema_drift_columns"

    def test_revision_id_fits_alembic_version_num_varchar32(self, migration) -> None:
        # alembic_version.version_num is VARCHAR(32) -- a too-long revision
        # id fails silently truncated or raises at stamp time.
        assert len(migration.revision) <= 32


class TestUpgradeAddsYoutubeAllowedLabels:
    def test_adds_column_if_not_exists(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)
        assert "ALTER TABLE music_policy" in sql
        assert "ADD COLUMN IF NOT EXISTS youtube_allowed_labels TEXT" in sql

    def test_column_is_nullable_no_default(self, migration) -> None:
        """`music_policy` already has rows -- NOT NULL/DEFAULT on a bare
        ADD COLUMN can fail or silently rewrite every row; NULL/empty must
        mean 'unrestricted', matching 0011/0012's precedent for this table
        family."""
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)
        assert "NOT NULL" not in sql.upper()
        assert " DEFAULT " not in sql.upper()

    def test_documents_the_column_with_a_comment(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.upgrade()

        sql = "\n".join(call.args[0] for call in mock_execute.call_args_list)
        assert "COMMENT ON COLUMN music_policy.youtube_allowed_labels" in sql


class TestDowngradeRemovesYoutubeAllowedLabels:
    def test_drops_column_if_exists(self, migration) -> None:
        with patch("alembic.op.execute") as mock_execute:
            migration.downgrade()

        mock_execute.assert_called_once()
        sql = mock_execute.call_args[0][0]
        assert "ALTER TABLE music_policy" in sql
        assert "DROP COLUMN IF EXISTS youtube_allowed_labels" in sql


class TestAddedColumnMatchesPydalSchema:
    """Cross-check against `hub_api/services/schema.py` itself -- the added
    column must be a real pydal-bound field on `music_policy`."""

    def test_youtube_allowed_labels_is_pydal_bound(self) -> None:
        fields = _pydal_fields_for_table("music_policy")
        assert "youtube_allowed_labels" in fields, (
            "schema.py's music_policy table has no "
            "Field('youtube_allowed_labels', ...) -- migration is adding a "
            "column pydal doesn't reference"
        )
