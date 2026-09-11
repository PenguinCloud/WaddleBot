//! Read-only view of `tenants` (owned by migration 058, not this service).
//! Used only to resolve a JWT `tenant` claim (a slug) to the numeric
//! `tenants.id` that `communities.tenant_id` references -- see
//! [`crate::api::tenancy`].

use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "tenants")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub slug: String,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {}

impl ActiveModelBehavior for ActiveModel {}
