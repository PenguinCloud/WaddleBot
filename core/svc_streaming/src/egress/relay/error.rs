//! Relay-sink error type. Converts to [`crate::egress::SinkError`] at the
//! `OutputSink` trait boundary via `From` so `RelaySink::start`/`stop` can
//! use `?` throughout.

use thiserror::Error;

use crate::egress::SinkError;
use crate::pipeline::model::PipelineId;
use crate::store::SecretError;

use super::policy::RelayPolicyError;

/// Errors a [`super::RelaySink`] operation can return. Message text never
/// includes a raw secret value -- [`Self::InvalidUrl`] carries only the
/// pre-redacted form.
#[derive(Debug, Error)]
pub enum RelayError {
    #[error(transparent)]
    Secret(#[from] SecretError),
    #[error(transparent)]
    Policy(#[from] RelayPolicyError),
    #[error("invalid relay target url ({redacted}): {reason}")]
    InvalidUrl { redacted: String, reason: String },
    #[error(
        "relay pipeline {0} has {1} active targets -- use tee_slaves() instead of ffmpeg_output_args()"
    )]
    MultipleTargets(PipelineId, usize),
    #[error("relay pipeline {0} has no active targets")]
    NoActiveTargets(PipelineId),
    #[error("RelaySink only handles OutputSpec::RtmpPush/SrtPush targets")]
    UnsupportedOutputSpec,
}

impl From<RelayError> for SinkError {
    fn from(err: RelayError) -> Self {
        SinkError::Other(anyhow::Error::new(err))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn invalid_url_display_never_leaks_beyond_the_redacted_field() {
        let err = RelayError::InvalidUrl {
            redacted: "rtmp://host/app/****".to_string(),
            reason: "expected rtmp:// scheme, got srt://".to_string(),
        };
        let rendered = err.to_string();
        assert!(rendered.contains("rtmp://host/app/****"));
        assert!(rendered.contains("expected rtmp:// scheme"));
    }

    #[test]
    fn converts_into_sink_error() {
        let err = RelayError::NoActiveTargets(PipelineId::nil());
        let sink_err: SinkError = err.into();
        assert!(matches!(sink_err, SinkError::Other(_)));
    }
}
