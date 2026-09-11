"""Add missing `communities.license_key`/`license_expires_at`/`license_tier`.

Closes the schema-drift gap documented in `hub_api/services/schema.py`
(module docstring gap 5): `bind_auth_tables()` already `define_table()`s
these three pydal `Field`s on `communities` (added by the M-automation
port group for `workflowController.js::validateLicense()`), but no
numbered SQL migration or Alembic revision ever created the real Postgres
columns -- confirmed by `grep -rl license_key config/postgres/migrations/`
returning no hits. Any query that does `SELECT *`/`.select()` against
`communities` (e.g. the Music Station `!sr` enqueue path,
`hub_api/blueprints/v1/community_music_queue.py::
internal_enqueue_song_request()`) 500s with `psycopg2.errors.UndefinedColumn:
column communities.license_key does not exist` before this migration.

Column shapes match the pydal `Field` definitions verbatim (`string`
length 255 -> `VARCHAR(255)`, `datetime` -> `TIMESTAMP`, `string` length
50 -> `VARCHAR(50)`, all nullable -- no `notnull=True`/default on any of
the three `Field()` calls) and the sibling `ALTER TABLE communities ADD
COLUMN IF NOT EXISTS ...` style already used by
`050_add_community_premium.sql`. NULL is the correct default, not a
placeholder to backfill: `workflowController.js::validateLicense()`
treats `!community.license_key` as `{valid: false, reason: 'No license
configured'}` -- a graceful deny, not a crash -- so every existing
community starts unlicensed for the workflow-automation feature until a
license is explicitly issued, and non-workflow readers of `communities`
(like the music enqueue path) never inspect these columns at all, they
only need the columns to exist so `SELECT *` stops erroring.

Revision ID: 0011_communities_license_cols
Revises: 0010_music_bot_token_ref
Create Date: 2026-09-10
"""

from alembic import op

revision = "0011_communities_license_cols"
down_revision = "0010_music_bot_token_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE communities
          ADD COLUMN IF NOT EXISTS license_key VARCHAR(255),
          ADD COLUMN IF NOT EXISTS license_expires_at TIMESTAMP,
          ADD COLUMN IF NOT EXISTS license_tier VARCHAR(50)
        """
    )
    op.execute(
        "COMMENT ON COLUMN communities.license_key IS "
        "'Workflow-automation license key; NULL = no license configured "
        "(workflowController.js::validateLicense() denies gracefully)'"
    )
    op.execute(
        "COMMENT ON COLUMN communities.license_expires_at IS "
        "'Workflow-automation license expiry; NULL = no expiry set'"
    )
    op.execute(
        "COMMENT ON COLUMN communities.license_tier IS "
        "'Workflow-automation license tier (pro/enterprise/premium); "
        "NULL = no license configured'"
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE communities
          DROP COLUMN IF EXISTS license_key,
          DROP COLUMN IF EXISTS license_expires_at,
          DROP COLUMN IF EXISTS license_tier
        """
    )
