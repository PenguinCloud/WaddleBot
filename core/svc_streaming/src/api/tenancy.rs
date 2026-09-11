//! Tenant-scoping helper: resolves a `community_id` path param against the
//! caller's JWT `tenant` claim (a slug) via the shared `tenants`/
//! `communities` tables -- see `src/db/entities/mod.rs` module docs for the
//! DB-grant assumption this makes.

use sea_orm::{ColumnTrait, DatabaseConnection, EntityTrait, QueryFilter};

use crate::db::entities::{community, tenant};
use crate::error::ApiError;

/// Returns `Ok(())` iff `community_id` exists and belongs to `tenant_slug`.
/// A missing community and a tenant mismatch both map to
/// [`ApiError::Forbidden`] (never [`ApiError::NotFound`]) so a caller
/// cannot distinguish "wrong tenant" from "does not exist" -- see
/// `rules/security.md` Tenant Isolation ("Tenant mismatch = immediate
/// 403").
pub async fn assert_tenant_owns_community(
    db: &DatabaseConnection,
    tenant_slug: &str,
    community_id: i32,
) -> Result<(), ApiError> {
    let tenant_row = tenant::Entity::find()
        .filter(tenant::Column::Slug.eq(tenant_slug))
        .one(db)
        .await
        .map_err(|err| ApiError::Internal(err.into()))?
        .ok_or_else(|| ApiError::Forbidden("unknown tenant".into()))?;

    let community_row = community::Entity::find_by_id(community_id)
        .one(db)
        .await
        .map_err(|err| ApiError::Internal(err.into()))?;

    match community_row {
        Some(c) if c.tenant_id == tenant_row.id => Ok(()),
        _ => Err(ApiError::Forbidden(
            "community does not belong to the caller's tenant".into(),
        )),
    }
}
