//! Discord voice-channel bridge sink (owned by a later chunk, S11).
//! Declares the `DiscordVoiceSink` shape against
//! [`crate::egress::OutputSink`]; bridging transcoded audio into a Discord
//! voice channel is not implemented in this scaffold. No Discord
//! gateway/voice client crate is declared in `Cargo.toml` yet -- the owning
//! chunk must propose and pin one (Opus RTP framing + Discord voice
//! websocket/UDP handshake) before implementing this sink.

use crate::egress::{OutputSink, SinkError};
use crate::pipeline::model::{OutputSpec, PipelineId};

/// Discord voice sink configuration.
#[derive(Debug, Clone, Default)]
pub struct DiscordVoiceSink;

impl OutputSink for DiscordVoiceSink {
    async fn start(&self, pipeline_id: PipelineId, _spec: OutputSpec) -> Result<(), SinkError> {
        tracing::debug!(%pipeline_id, "DiscordVoiceSink::start is not yet implemented");
        Err(SinkError::Unimplemented("DiscordVoiceSink::start"))
    }

    async fn stop(&self, pipeline_id: PipelineId) -> Result<(), SinkError> {
        tracing::debug!(%pipeline_id, "DiscordVoiceSink::stop is not yet implemented");
        Err(SinkError::Unimplemented("DiscordVoiceSink::stop"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[tokio::test]
    async fn start_reports_unimplemented() {
        let sink = DiscordVoiceSink;
        let spec = OutputSpec::DiscordVoice {
            guild_id: "guild-1".into(),
            channel_id: "channel-1".into(),
        };
        let err = sink.start(Uuid::nil(), spec).await.unwrap_err();
        assert!(matches!(
            err,
            SinkError::Unimplemented("DiscordVoiceSink::start")
        ));
    }

    #[tokio::test]
    async fn stop_reports_unimplemented() {
        let sink = DiscordVoiceSink;
        let err = sink.stop(Uuid::nil()).await.unwrap_err();
        assert!(matches!(
            err,
            SinkError::Unimplemented("DiscordVoiceSink::stop")
        ));
    }
}
