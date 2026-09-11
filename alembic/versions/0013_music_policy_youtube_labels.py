"""Add `music_policy.youtube_allowed_labels` (YouTube content-label allowlist).

Closes gh-313: the Music Station's YouTube provider has no way to restrict
`!sr`/`!songrequest` enqueue to a community-configured allowlist of YouTube
content labels (e.g. `["creativecommons"]`, or a curated set of
category/label strings the community trusts) -- every other music-policy
knob (`song_requests_allowed`, `requests_category_restricted`) already
lives on this table, this is the same per-community configuration surface,
just scoped to the YouTube provider specifically.

`youtube_allowed_labels` is a nullable TEXT column storing a JSON-encoded
list of lowercase label strings (`schema.py`'s pydal `Field` is declared
"text" like every other JSON-blob-in-text column already on this table's
sibling tables -- e.g. `commands.platforms` from 0012 -- pydal has no
native `list:string`/`json` type used elsewhere in this table group, so
this follows that precedent rather than introducing a new column-type
convention for one field). NULL or an empty list means "unrestricted" --
matches this table's existing `updated_by`/`updated_at` nullable-by-default
posture and 0011/0012's "NULL is a legitimate not-configured state, never
a placeholder to backfill" precedent: every existing `music_policy` row
keeps behaving exactly as before (no YouTube label restriction) until a
community explicitly opts in.

Added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, same idempotent
style as 0011/0012, so upgrading an already-patched or partially-migrated
DB is a no-op rather than an error.

Revision ID: 0013_music_policy_yt_labels
Revises: 0012_schema_drift_columns
Create Date: 2026-09-11
"""

from alembic import op

revision = "0013_music_policy_yt_labels"
down_revision = "0012_schema_drift_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # gh-313: per-community YouTube content-label allowlist for the Music
    # Station song-request enqueue path. Nullable, JSON-encoded list of
    # lowercase labels; NULL/empty = unrestricted (matches 011/012's
    # "NULL is a legitimate not-configured state" precedent for this table
    # family -- never a placeholder to backfill).
    op.execute(
        """
        ALTER TABLE music_policy
          ADD COLUMN IF NOT EXISTS youtube_allowed_labels TEXT
        """
    )
    op.execute(
        "COMMENT ON COLUMN music_policy.youtube_allowed_labels IS "
        "'JSON-encoded list of lowercase YouTube content labels allowed for "
        "song requests; NULL/empty = unrestricted (gh-313)'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE music_policy DROP COLUMN IF EXISTS youtube_allowed_labels"
    )
