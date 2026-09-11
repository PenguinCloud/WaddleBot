//! Read-only view of `communities` (owned by the base-schema migration, not
//! this service). Used only to resolve a `community_id` path param to its
//! owning `tenant_id` for tenant scoping -- see [`crate::api::tenancy`].

use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "communities")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub tenant_id: i32,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {}

impl ActiveModelBehavior for ActiveModel {}
