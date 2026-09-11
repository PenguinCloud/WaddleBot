//! `GET /communities/{community_id}/live-channels` -- the community's
//! connected Twitch/YouTube channels. Ported from the Python alpha's
//! `blueprints/live_channels.py`; member-gated (any active community
//! member), same posture as `crate::api::lifecycle::status`.

use axum::extract::Path;

use sea_orm::{ColumnTrait, EntityTrait, QueryFilter};
use serde::Serialize;
use utoipa::ToSchema;

use crate::db::entities::community_server;
use crate::error::ApiError;
use crate::http::auth::AuthenticatedClaims;

use super::extract::DbConn;
use super::response::ApiSuccess;
use super::tenancy::assert_tenant_owns_community;

const LIVE_PLATFORMS: [&str; 2] = ["twitch", "youtube"];

/// One connected platform channel.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct ChannelStatusDto {
    pub platform: String,
    pub channel_id: String,
    pub channel_name: String,
    /// Real-time live/offline status against the platform's own API (the
    /// Python alpha's `services/live_channels_service.py` polls Twitch/
    /// YouTube directly). Not implemented here: those platform API
    /// credentials (`TWITCH_CLIENT_ID`/`TWITCH_CLIENT_SECRET`/
    /// `YOUTUBE_API_KEY`) are not present in `crate::config::CliConfig`,
    /// and adding them is outside this chunk's file ownership
    /// (`src/config.rs` is owned by a different chunk). Always `None`.
    pub live: Option<bool>,
    /// Same caveat as `live`.
    pub title: Option<String>,
}

/// `GET /communities/{community_id}/live-channels`.
#[utoipa::path(
    get,
    path = "/communities/{community_id}/live-channels",
    params(("community_id" = i32, Path, description = "Community ID")),
    responses((status = 200, description = "Connected platform channels", body = [ChannelStatusDto])),
    tag = "streaming"
)]
pub async fn get_live_channels(
    Path(community_id): Path<i32>,
    AuthenticatedClaims(claims): AuthenticatedClaims,
    DbConn(db): DbConn,
) -> Result<ApiSuccess<Vec<ChannelStatusDto>>, ApiError> {
    assert_tenant_owns_community(&db, &claims.tenant, community_id).await?;
    let rows = community_server::Entity::find()
        .filter(community_server::Column::CommunityId.eq(community_id))
        .filter(community_server::Column::Platform.is_in(LIVE_PLATFORMS))
        .all(&db)
        .await
        .map_err(|err| ApiError::Internal(err.into()))?;

    let channels = rows
        .into_iter()
        .map(|r| ChannelStatusDto {
            platform: r.platform,
            channel_id: r.platform_server_id,
            channel_name: r.platform_server_name.unwrap_or_default(),
            live: None,
            title: None,
        })
        .collect();
    Ok(ApiSuccess::ok(channels))
}
