//! Hand-written SeaORM entities for the tables this service actually reads
//! or writes. No `sea-orm-cli` was run against the cluster (schema/DDL is
//! owned by Alembic-equivalent SQL migrations under
//! `config/postgres/migrations/`, not this crate) -- each `Model` below
//! only declares the columns this service touches, which is sufficient
//! because SeaORM's generated queries always select the declared columns
//! explicitly, never `SELECT *`.
//!
//! `streaming_configs`/`streaming_targets` (migration 079) are this
//! service's own tables (`rules/backend-database.md` Per-Service Database
//! Accounts). `tenants`/`communities`/`community_servers` (migrations 000,
//! 058) are owned by other services sharing the same Postgres instance --
//! read-only here, used only to resolve tenant ownership of a
//! `community_id` path param and to list a community's linked platform
//! channels. This assumes the per-service DB account has been granted
//! `SELECT` on those specific columns; if it has not, every route that
//! calls [`crate::api::tenancy::assert_tenant_owns_community`] will fail
//! closed with a DB error mapped to `ApiError::Internal`, not silently
//! bypass tenant scoping.

pub mod community;
pub mod community_server;
pub mod streaming_config;
pub mod streaming_target;
pub mod tenant;
