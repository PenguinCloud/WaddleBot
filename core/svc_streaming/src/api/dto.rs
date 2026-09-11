//! Request/response DTOs for the control-plane API. Never a raw SeaORM
//! `Model` serialized directly -- see `rules/security.md` Output
//! Validation.

use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

use crate::db::entities::streaming_config;
use crate::pipeline::{PipelineState, PipelineStatus};
use crate::store::SecretRef;

fn default_source_type() -> String {
    "rtmp".to_string()
}

fn default_bitrate_kbps() -> i32 {
    4000
}

/// Wire shape for `GET`/list/create/update config responses.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct StreamingConfigDto {
    pub id: i32,
    pub community_id: i32,
    pub source_url: String,
    pub source_type: String,
    pub enabled: bool,
    pub record_enabled: bool,
    pub transcode_enabled: bool,
    pub transcode_bitrate_kbps: i32,
}

impl From<streaming_config::Model> for StreamingConfigDto {
    fn from(m: streaming_config::Model) -> Self {
        Self {
            id: m.id,
            community_id: m.community_id,
            source_url: m.source_url,
            source_type: m.source_type,
            enabled: m.enabled,
            record_enabled: m.record_enabled,
            transcode_enabled: m.transcode_enabled,
            transcode_bitrate_kbps: m.transcode_bitrate_kbps,
        }
    }
}

/// `POST .../configs` request body.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateConfigRequest {
    pub source_url: String,
    #[serde(default = "default_source_type")]
    pub source_type: String,
    #[serde(default)]
    pub record_enabled: bool,
    #[serde(default)]
    pub transcode_enabled: bool,
    #[serde(default = "default_bitrate_kbps")]
    pub transcode_bitrate_kbps: i32,
}

/// `PUT .../configs/{id}` request body -- every field optional, only
/// supplied fields are updated.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateConfigRequest {
    pub source_url: Option<String>,
    pub source_type: Option<String>,
    pub enabled: Option<bool>,
    pub record_enabled: Option<bool>,
    pub transcode_enabled: Option<bool>,
    pub transcode_bitrate_kbps: Option<i32>,
}

/// Wire-compatible mirror of [`crate::store::SecretRef`] carrying its own
/// `ToSchema` derive -- `src/store/secrets.rs` is owned by a different
/// chunk so `SecretRef` itself is not annotated for OpenAPI generation.
/// Identical `#[serde(tag = "source", ...)]` shape; converts losslessly
/// both ways.
#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
#[serde(tag = "source", rename_all = "snake_case")]
pub enum SecretRefDto {
    Env { var: String },
    File { path: String },
}

impl From<SecretRefDto> for SecretRef {
    fn from(dto: SecretRefDto) -> Self {
        match dto {
            SecretRefDto::Env { var } => SecretRef::Env { var },
            SecretRefDto::File { path } => SecretRef::File { path },
        }
    }
}

impl From<SecretRef> for SecretRefDto {
    fn from(sr: SecretRef) -> Self {
        match sr {
            SecretRef::Env { var } => SecretRefDto::Env { var },
            SecretRef::File { path } => SecretRefDto::File { path },
        }
    }
}

/// `POST .../configs/{id}/targets` request body. Deliberately has no
/// `forward_url`/`url` field: only a [`SecretRefDto`] is accepted, so a
/// caller can never submit an inline `rtmp://...key` destination --
/// `#[serde(deny_unknown_fields)]` rejects any extra field (e.g. a raw
/// `forward_url`), and `SecretRefDto`'s tagged-enum shape rejects a bare
/// URL string even under the right field name.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AddTargetRequest {
    pub platform: String,
    pub url_secret_ref: SecretRefDto,
}

/// Wire shape for target list/create responses.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct StreamingTargetDto {
    pub id: i32,
    pub config_id: i32,
    pub platform: String,
    pub url_secret_ref: SecretRefDto,
    pub enabled: bool,
}

/// Wire shape for start/stop/status responses.
#[derive(Debug, Clone, Serialize, ToSchema)]
pub struct PipelineStatusDto {
    pub id: uuid::Uuid,
    pub state: String,
    pub detail: Option<String>,
}

pub(super) fn state_str(state: PipelineState) -> &'static str {
    match state {
        PipelineState::Starting => "starting",
        PipelineState::Running => "running",
        PipelineState::Degraded => "degraded",
        PipelineState::Stopping => "stopping",
        PipelineState::Stopped => "stopped",
        PipelineState::Failed => "failed",
    }
}

impl From<PipelineStatus> for PipelineStatusDto {
    fn from(s: PipelineStatus) -> Self {
        Self {
            id: s.id,
            state: state_str(s.state).to_string(),
            detail: s.detail,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_target_request_rejects_inline_url_field() {
        let raw = r#"{"platform":"custom","url_secret_ref":{"source":"env","var":"X"},"forward_url":"rtmp://evil/key"}"#;
        let err = serde_json::from_str::<AddTargetRequest>(raw).unwrap_err();
        assert!(err.to_string().contains("unknown field"));
    }

    #[test]
    fn add_target_request_rejects_bare_url_string_as_secret_ref() {
        let raw = r#"{"platform":"custom","url_secret_ref":"rtmp://key"}"#;
        assert!(serde_json::from_str::<AddTargetRequest>(raw).is_err());
    }

    #[test]
    fn add_target_request_accepts_env_secret_ref() {
        let raw = r#"{"platform":"custom","url_secret_ref":{"source":"env","var":"RELAY_URL"}}"#;
        let parsed: AddTargetRequest = serde_json::from_str(raw).unwrap();
        assert_eq!(parsed.platform, "custom");
        assert!(matches!(parsed.url_secret_ref, SecretRefDto::Env { .. }));
    }

    #[test]
    fn secret_ref_dto_round_trips_through_secret_ref() {
        let dto = SecretRefDto::File {
            path: "/var/secrets/x".into(),
        };
        let sr: SecretRef = dto.clone().into();
        let back: SecretRefDto = sr.into();
        assert!(matches!(back, SecretRefDto::File { path } if path == "/var/secrets/x"));
        let _ = dto;
    }
}
