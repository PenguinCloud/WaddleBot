"""Backfill every pydal-bound column/table in `hub_api/services/schema.py`
that no numbered SQL migration or prior Alembic revision ever created.

Closes the schema-drift gap class documented in `hub_api/services/
schema.py`'s module docstring (gaps 1-6) plus every additional instance
found by a full programmatic audit of the same class of bug. Hit #1
(`communities.license_key`/`license_expires_at`/`license_tier`) was fixed
by `0011_communities_license_cols`; hit #2 (`communities.about_extended`/
`social_links`/`website_url`/`discord_invite_url`/`visibility`, the
module docstring's gap 4) broke the Music Station `!sr` enqueue path and
is fixed here, alongside gap (1) (`hub_users.email_verification_expires`),
gap (3) (`platform_configs.enabled`), gap (6) (`support_tickets`/
`support_ticket_comments`, extended with `support_ticket_categories`
which the same `github_sync`/`support` port group also binds), and every
other drift instance the audit surfaced that the module docstring hadn't
yet caught up to (`commands.module_url`/`platforms`, `community_members`
soft-removal columns, the marketplace-vendor tables, `platform_admins`,
the not-yet-wired music-provider/radio tables, and the OAuth token
tables).

Audit methodology (real output, not inferred): statically parsed every
`dal.define_table(...)` call in `schema.py` via `ast` (union of every
`Field()` across the whole file per table name -- NOT a runtime replay,
because `bind_tenant_tables()` calls `dal.define_table("communities", ...,
redefine=True)` with only 11 of `communities`' ~33 fields, and pydal's
`redefine=True` REPLACES the field list wholesale rather than merging by
name; a runtime replay is call-order-dependent and silently loses fields
depending which `bind_*_tables()` function runs last -- a real landmine
in `schema.py` itself, out of scope for this migration, worth a follow-up
issue). Diffed against `information_schema.columns` from a throwaway
Postgres fully migrated via this repo's own `migrations/Dockerfile`
image (`alembic upgrade head` against a fresh DB) -- the live beta/prod
cluster was unreachable for this audit (`postgres` pod `Pending`,
`disk-pressure` node taint), so the freshly-migrated throwaway DB is the
most faithful available proxy for "what a fully-migrated real DB has".

Every column below is added NULLABLE, no default beyond what pydal itself
declares no server-side default for -- matches `0011`'s precedent: NULL
is a legitimate "not configured"/"not yet populated" state for every one
of these (soft-delete/moderation timestamps, OAuth/vendor linkage, ticket
system), never a placeholder to backfill. `community_vendor_installations`
and `vendor_payments` are a partial exception worth flagging explicitly:
their pydal field lists (`module_id`/`status`/`amount_cents`/`seller_id`/
etc.) don't match the real table's actual design at all (real columns are
`vendor_module_id`/`payment_status`/`gross_amount`+`net_amount` as
DECIMAL/no `seller_id`, from `021_add_vendor_submissions.sql`) -- adding
the pydal-named columns here stops the `UndefinedColumn` 500, but every
row will read NULL forever since nothing ever writes these column names;
this looks like `schema.py` modeling a different marketplace-billing
design than what actually shipped, and needs its own follow-up (out of
scope for a schema-drift backfill).

Revision ID: 0012_schema_drift_columns
Revises: 0011_communities_license_cols
Create Date: 2026-09-11
"""

from alembic import op

revision = "0012_schema_drift_columns"
down_revision = "0011_communities_license_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Gap (1): hub_users.email_verification_expires (module docstring
    # gap 1) -- referenced by authController.js register()/verifyEmail()/
    # resendVerification(), defined only in the drifted config/postgres/
    # init.sql bootstrap, never in a numbered migration.
    op.execute(
        """
        ALTER TABLE hub_users
          ADD COLUMN IF NOT EXISTS email_verification_expires TIMESTAMP
        """
    )

    # -- Gap (3): platform_configs.enabled (module docstring gap 3) --
    # queried by authController.js's getTenantLoginInfo().
    op.execute(
        """
        ALTER TABLE platform_configs
          ADD COLUMN IF NOT EXISTS enabled BOOLEAN
        """
    )

    # -- Gap (4): communities profile columns (module docstring gap 4) --
    # communityProfileController.js reads/writes these exact column names;
    # 037's `social_links` column is on `community_members`, a different
    # table. Broke the Music Station `!sr` enqueue path's `SELECT *
    # communities` (this audit's hit #2). Also backfills `is_premium`/
    # `seat_limit`, bound by the same M3 Platform-admin group's `communities`
    # extension but not previously covered by any migration.
    op.execute(
        """
        ALTER TABLE communities
          ADD COLUMN IF NOT EXISTS about_extended TEXT,
          ADD COLUMN IF NOT EXISTS social_links JSONB,
          ADD COLUMN IF NOT EXISTS website_url VARCHAR(500),
          ADD COLUMN IF NOT EXISTS discord_invite_url VARCHAR(500),
          ADD COLUMN IF NOT EXISTS visibility VARCHAR(30),
          ADD COLUMN IF NOT EXISTS is_premium BOOLEAN,
          ADD COLUMN IF NOT EXISTS seat_limit INTEGER
        """
    )

    # -- New finds: commands table -- module_url/platforms are bound by
    # schema.py's `commands` definition but no migration ever adds them.
    op.execute(
        """
        ALTER TABLE commands
          ADD COLUMN IF NOT EXISTS module_url VARCHAR(500),
          ADD COLUMN IF NOT EXISTS platforms JSONB
        """
    )

    # -- New finds: community_members soft-removal/activity columns --
    # bound by `bind_community_authz_tables()`'s moderation extension,
    # no migration adds them (037/058 only add `social_links`/`claims_cache`
    # /`community_role_id`, a different column set on this same table).
    op.execute(
        """
        ALTER TABLE community_members
          ADD COLUMN IF NOT EXISTS created_at TIMESTAMP,
          ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP,
          ADD COLUMN IF NOT EXISTS removed_at TIMESTAMP,
          ADD COLUMN IF NOT EXISTS removed_by INTEGER,
          ADD COLUMN IF NOT EXISTS removal_reason TEXT
        """
    )

    # -- New finds: hub_modules.is_featured, hub_module_installations.
    # module_name -- bound by schema.py, no migration adds them.
    op.execute(
        """
        ALTER TABLE hub_modules
          ADD COLUMN IF NOT EXISTS is_featured BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE hub_module_installations
          ADD COLUMN IF NOT EXISTS module_name VARCHAR(255)
        """
    )

    # -- New finds: permission_scopes.display_name/scope_key -- bound by
    # schema.py, `011_add_scoped_tokens.sql` creates the table without them.
    op.execute(
        """
        ALTER TABLE permission_scopes
          ADD COLUMN IF NOT EXISTS scope_key VARCHAR(100),
          ADD COLUMN IF NOT EXISTS display_name VARCHAR(255)
        """
    )

    # -- New finds: vendor_discount_codes.description -- bound by
    # schema.py, `064_vendor_discount_codes.sql` creates the table without it.
    op.execute(
        """
        ALTER TABLE vendor_discount_codes
          ADD COLUMN IF NOT EXISTS description TEXT
        """
    )

    # -- New finds: community_vendor_installations / vendor_payments --
    # see module docstring: pydal's field names don't match
    # `021_add_vendor_submissions.sql`'s real columns at all (different
    # marketplace-billing design). Added nullable to stop the
    # UndefinedColumn 500; reads will be NULL until reconciled.
    op.execute(
        """
        ALTER TABLE community_vendor_installations
          ADD COLUMN IF NOT EXISTS module_id INTEGER,
          ADD COLUMN IF NOT EXISTS status VARCHAR(50),
          ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP,
          ADD COLUMN IF NOT EXISTS uninstalled_at TIMESTAMP,
          ADD COLUMN IF NOT EXISTS discount_code_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE vendor_payments
          ADD COLUMN IF NOT EXISTS module_id INTEGER,
          ADD COLUMN IF NOT EXISTS seller_id INTEGER,
          ADD COLUMN IF NOT EXISTS status VARCHAR(50),
          ADD COLUMN IF NOT EXISTS amount_cents INTEGER,
          ADD COLUMN IF NOT EXISTS paid_at TIMESTAMP
        """
    )

    # -- Gap (6): support_tickets/support_ticket_comments (module docstring
    # gap 6) -- queried by githubSyncService.js's syncTicketToGithub()/
    # processInboundIssueComment(), bound by bind_github_sync_tables() but
    # owned by a not-yet-ported Support module: no numbered migration
    # creates either table at all. support_ticket_categories is the same
    # port group's third table (bind_github_sync_tables() references
    # category_id), also missing entirely.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_ticket_categories (
          id SERIAL PRIMARY KEY,
          community_id INTEGER,
          name VARCHAR(255),
          description TEXT,
          form_fields JSONB,
          sort_order INTEGER,
          is_active BOOLEAN,
          created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
          id SERIAL PRIMARY KEY,
          community_id INTEGER,
          category_id INTEGER,
          ticket_number VARCHAR(20),
          subject VARCHAR(500),
          description TEXT,
          status VARCHAR(20),
          priority VARCHAR(20),
          reporter_user_id INTEGER,
          reporter_name VARCHAR(255),
          reporter_email VARCHAR(255),
          assignee_user_id INTEGER,
          custom_fields JSONB,
          resolved_at TIMESTAMP,
          created_at TIMESTAMP,
          updated_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_ticket_comments (
          id SERIAL PRIMARY KEY,
          ticket_id INTEGER,
          author_user_id INTEGER,
          author_name VARCHAR(255),
          content TEXT,
          is_internal BOOLEAN,
          source VARCHAR(50),
          created_at TIMESTAMP
        )
        """
    )

    # -- New find: platform_admins -- bound by bind_platform_tables(), the
    # M3 group's own gap (5) (see that function's docstring: platformController
    # .js's entire route group is unreachable without this table), no
    # numbered migration creates it.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_admins (
          id SERIAL PRIMARY KEY,
          user_id INTEGER,
          role VARCHAR(50),
          is_active BOOLEAN,
          deactivated_at TIMESTAMP,
          created_at TIMESTAMP,
          updated_at TIMESTAMP
        )
        """
    )

    # -- New finds: OAuth linkage tables bound by schema.py, never migrated.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_state_tokens (
          id SERIAL PRIMARY KEY,
          community_id INTEGER,
          provider VARCHAR(50),
          state_token VARCHAR(255),
          redirect_uri TEXT,
          expires_at TIMESTAMP,
          created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oauth_tokens (
          id SERIAL PRIMARY KEY,
          community_id INTEGER,
          provider VARCHAR(50)
        )
        """
    )

    # -- New finds: Music Station provider/settings/radio tables bound by
    # schema.py's bind_music_tables() but never migrated -- the same port
    # group 0009/0010 already partially covered (app_tenant_availability
    # config only), these three are the per-community configuration side.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS collector_modules (
          id SERIAL PRIMARY KEY,
          module_name VARCHAR(255),
          module_version VARCHAR(50),
          platform VARCHAR(50),
          status VARCHAR(50),
          endpoint_url TEXT,
          last_heartbeat TIMESTAMP,
          created_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_music_providers (
          id SERIAL PRIMARY KEY,
          community_id INTEGER,
          provider_name VARCHAR(50),
          is_connected BOOLEAN,
          is_active BOOLEAN,
          oauth_expires_at TIMESTAMP,
          last_sync TIMESTAMP,
          config TEXT,
          created_at TIMESTAMP,
          updated_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_music_settings (
          id SERIAL PRIMARY KEY,
          community_id INTEGER,
          default_provider VARCHAR(50),
          autoplay_enabled BOOLEAN,
          require_dj_approval BOOLEAN,
          volume_limit INTEGER,
          allowed_genres JSONB,
          blocked_artists JSONB,
          is_active BOOLEAN,
          created_at TIMESTAMP,
          updated_at TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_radio_stations (
          id SERIAL PRIMARY KEY,
          community_id INTEGER,
          name VARCHAR(255),
          url VARCHAR(2048),
          genre VARCHAR(100),
          description TEXT,
          is_active BOOLEAN,
          created_by INTEGER,
          created_at TIMESTAMP,
          updated_at TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS community_radio_stations")
    op.execute("DROP TABLE IF EXISTS community_music_settings")
    op.execute("DROP TABLE IF EXISTS community_music_providers")
    op.execute("DROP TABLE IF EXISTS collector_modules")
    op.execute("DROP TABLE IF EXISTS oauth_tokens")
    op.execute("DROP TABLE IF EXISTS oauth_state_tokens")
    op.execute("DROP TABLE IF EXISTS platform_admins")
    op.execute("DROP TABLE IF EXISTS support_ticket_comments")
    op.execute("DROP TABLE IF EXISTS support_tickets")
    op.execute("DROP TABLE IF EXISTS support_ticket_categories")

    op.execute(
        """
        ALTER TABLE vendor_payments
          DROP COLUMN IF EXISTS paid_at,
          DROP COLUMN IF EXISTS amount_cents,
          DROP COLUMN IF EXISTS status,
          DROP COLUMN IF EXISTS seller_id,
          DROP COLUMN IF EXISTS module_id
        """
    )
    op.execute(
        """
        ALTER TABLE community_vendor_installations
          DROP COLUMN IF EXISTS discount_code_id,
          DROP COLUMN IF EXISTS uninstalled_at,
          DROP COLUMN IF EXISTS last_active_at,
          DROP COLUMN IF EXISTS status,
          DROP COLUMN IF EXISTS module_id
        """
    )
    op.execute(
        "ALTER TABLE vendor_discount_codes DROP COLUMN IF EXISTS description"
    )
    op.execute(
        """
        ALTER TABLE permission_scopes
          DROP COLUMN IF EXISTS display_name,
          DROP COLUMN IF EXISTS scope_key
        """
    )
    op.execute(
        "ALTER TABLE hub_module_installations DROP COLUMN IF EXISTS module_name"
    )
    op.execute("ALTER TABLE hub_modules DROP COLUMN IF EXISTS is_featured")
    op.execute(
        """
        ALTER TABLE community_members
          DROP COLUMN IF EXISTS removal_reason,
          DROP COLUMN IF EXISTS removed_by,
          DROP COLUMN IF EXISTS removed_at,
          DROP COLUMN IF EXISTS last_activity,
          DROP COLUMN IF EXISTS created_at
        """
    )
    op.execute(
        """
        ALTER TABLE commands
          DROP COLUMN IF EXISTS platforms,
          DROP COLUMN IF EXISTS module_url
        """
    )
    op.execute(
        """
        ALTER TABLE communities
          DROP COLUMN IF EXISTS seat_limit,
          DROP COLUMN IF EXISTS is_premium,
          DROP COLUMN IF EXISTS visibility,
          DROP COLUMN IF EXISTS discord_invite_url,
          DROP COLUMN IF EXISTS website_url,
          DROP COLUMN IF EXISTS social_links,
          DROP COLUMN IF EXISTS about_extended
        """
    )
    op.execute("ALTER TABLE platform_configs DROP COLUMN IF EXISTS enabled")
    op.execute(
        "ALTER TABLE hub_users DROP COLUMN IF EXISTS email_verification_expires"
    )
