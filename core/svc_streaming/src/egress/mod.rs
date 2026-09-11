//! Egress sink contract.
//!
//! Each concrete sink (owned by a later chunk: `hls` S7, `whep` S6,
//! `relay` S9, `record` S8, `discord_voice` S11) consumes transcoded
//! pipeline output and delivers it to its target. The pipeline supervisor
//! owns starting/stopping sinks per pipeline via this trait.

pub mod discord_voice;
pub mod hls;
pub mod record;
pub mod relay;
pub mod whep;

use crate::pipeline::model::{OutputSpec, PipelineId};

/// Errors an [`OutputSink`] implementation can return.
#[derive(Debug, thiserror::Error)]
pub enum SinkError {
    #[error("{0} is not yet implemented")]
    Unimplemented(&'static str),
    #[error(transparent)]
    Other(#[from] anyhow::Error),
}

/// Delivers pipeline output to a single [`OutputSpec`] target. Implemented
/// once per egress kind (HLS, WHEP, RTMP/SRT relay, recording, Discord
/// voice).
pub trait OutputSink: Send + Sync {
    /// Starts delivering output for `pipeline_id` to `spec`.
    fn start(
        &self,
        pipeline_id: PipelineId,
        spec: OutputSpec,
    ) -> impl std::future::Future<Output = Result<(), SinkError>> + Send;
    /// Stops delivery for `pipeline_id`. Idempotent.
    fn stop(
        &self,
        pipeline_id: PipelineId,
    ) -> impl std::future::Future<Output = Result<(), SinkError>> + Send;
}
