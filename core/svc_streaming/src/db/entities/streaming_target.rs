//! SeaORM entity for `streaming_targets`
//! (`config/postgres/migrations/079_svc_streaming.sql`) -- this service's
//! own table.
//!
//! `forward_url` (`VARCHAR(1024)`) never holds a raw destination URL with
//! an embedded stream key: the API layer
//! (`crate::api::targets`/`crate::api::dto`) only accepts a
//! `url_secret_ref` in request bodies and persists
//! `serde_json::to_string(&SecretRef)` into this column -- migration 079
//! predates the secret_ref model and has no dedicated column for it, so the
//! existing `VARCHAR(1024)` column is reused to hold the serialized
//! reference rather than a resolved secret, per `rules/client.md` Secrets &
//! Credentials.

use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "streaming_targets")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub config_id: i32,
    pub platform: String,
    /// Serialized [`crate::store::SecretRef`] JSON, never a raw URL.
    pub forward_url: String,
    pub enabled: bool,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {}

impl ActiveModelBehavior for ActiveModel {}
