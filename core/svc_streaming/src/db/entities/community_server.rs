//! Read-only view of `community_servers` (base-schema migration, not this
//! service) -- the community's linked platform channels, used by the
//! `/live-channels` route. Real request-time live-status polling against
//! Twitch/YouTube (as the Python alpha's `services/live_channels_service.py`
//! performs) needs platform API credentials that are not present in
//! `crate::config::CliConfig`; adding them is outside this chunk's file
//! ownership (`src/config.rs` is owned by a different chunk), so the route
//! reports connected channels without a live/title check -- see
//! [`crate::api::live_channels`].

use sea_orm::entity::prelude::*;

#[derive(Clone, Debug, PartialEq, Eq, DeriveEntityModel)]
#[sea_orm(table_name = "community_servers")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub community_id: i32,
    pub platform: String,
    pub platform_server_id: String,
    pub platform_server_name: Option<String>,
}

#[derive(Copy, Clone, Debug, EnumIter, DeriveRelation)]
pub enum Relation {}

impl ActiveModelBehavior for ActiveModel {}
