//! Dyn-compatible adapter over [`crate::pipeline::PipelineEngine`].
//!
//! `PipelineEngine`'s methods return `impl Future` (return-position `impl
//! Trait` in traits), which is not object-safe, but axum handlers need a
//! single concrete `Extension<T>` type regardless of which engine
//! implementation is wired in -- [`UnwiredEngine`] in production (see its
//! own doc comment for why), a fake in tests. This module defines a
//! boxed-future wrapper trait with a blanket impl for any `PipelineEngine`,
//! using only `std::pin`/`std::future` -- no new crate dependency.

use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;

use crate::pipeline::{
    PipelineEngine, PipelineError, PipelineHandle, PipelineId, PipelineSpec, PipelineStatus,
};

type BoxFuture<'a, T> = Pin<Box<dyn Future<Output = T> + Send + 'a>>;

/// Object-safe equivalent of [`PipelineEngine`] -- every method boxes its
/// future so `Arc<dyn DynPipelineEngine>` can be layered as a single
/// concrete axum `Extension` type regardless of the underlying
/// implementation.
pub trait DynPipelineEngine: Send + Sync {
    fn start(&self, spec: PipelineSpec) -> BoxFuture<'_, Result<PipelineHandle, PipelineError>>;
    fn stop(&self, id: PipelineId) -> BoxFuture<'_, Result<(), PipelineError>>;
    fn status(&self, id: PipelineId) -> BoxFuture<'_, Result<PipelineStatus, PipelineError>>;
}

impl<T: PipelineEngine> DynPipelineEngine for T {
    fn start(&self, spec: PipelineSpec) -> BoxFuture<'_, Result<PipelineHandle, PipelineError>> {
        Box::pin(PipelineEngine::start(self, spec))
    }

    fn stop(&self, id: PipelineId) -> BoxFuture<'_, Result<(), PipelineError>> {
        Box::pin(PipelineEngine::stop(self, id))
    }

    fn status(&self, id: PipelineId) -> BoxFuture<'_, Result<PipelineStatus, PipelineError>> {
        Box::pin(PipelineEngine::status(self, id))
    }
}

/// Shared handle to whichever [`DynPipelineEngine`] is wired into the
/// router. [`crate::api::router`] uses [`default_engine`];
/// [`crate::api::router_for_testing`] takes one explicitly so tests can
/// inject a fake that actually succeeds.
pub type SharedEngine = Arc<dyn DynPipelineEngine>;

/// Placeholder engine used until the real supervisor is wired in.
/// `pipeline::supervisor::FfmpegSupervisor` (S3) needs runtime config
/// (`FFMPEG_PATH`/`STREAM_DATA_DIR`/the WebRTC UDP range start/a
/// `SecretResolver`) to construct, none of which reaches this function:
/// `router()` is a synchronous, zero-arg function (its call site,
/// `src/http/mod.rs`'s `.nest("/api/v1", crate::api::router())`, is owned
/// by a different chunk and out of this chunk's file ownership), and
/// `crate::config::Config` is only available later, per-request, via
/// `State<AppState>` -- which is exactly the constraint
/// [`crate::db::get_or_connect`] works around for the DB connection, but
/// there is no per-request "first call wins" equivalent for something that
/// needs to be constructed once and then supervise long-lived processes.
/// Every route in this chunk still calls through [`SharedEngine`] exactly
/// as it would against the real engine, so wiring `FfmpegSupervisor` in
/// here is a mechanical follow-up once `AppState` (or an equivalent
/// injection point) can carry a long-lived engine instance.
struct UnwiredEngine;

impl PipelineEngine for UnwiredEngine {
    async fn start(&self, _spec: PipelineSpec) -> Result<PipelineHandle, PipelineError> {
        Err(PipelineError::Unimplemented(
            "PipelineEngine is not yet wired into the production router",
        ))
    }

    async fn stop(&self, _id: PipelineId) -> Result<(), PipelineError> {
        Err(PipelineError::Unimplemented(
            "PipelineEngine is not yet wired into the production router",
        ))
    }

    async fn status(&self, _id: PipelineId) -> Result<PipelineStatus, PipelineError> {
        Err(PipelineError::Unimplemented(
            "PipelineEngine is not yet wired into the production router",
        ))
    }
}

/// Production default engine.
pub fn default_engine() -> SharedEngine {
    Arc::new(UnwiredEngine)
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[tokio::test]
    async fn default_engine_reports_unimplemented() {
        let engine = default_engine();
        let err = engine.status(Uuid::nil()).await.unwrap_err();
        assert!(matches!(err, PipelineError::Unimplemented(_)));
    }

    #[tokio::test]
    async fn default_engine_start_and_stop_report_unimplemented() {
        let engine = default_engine();
        let spec = PipelineSpec {
            id: Uuid::nil(),
            tenant: "t".into(),
            community_id: "1".into(),
            inputs: vec![],
            profiles: vec![],
            outputs: vec![],
        };
        assert!(matches!(
            engine.start(spec).await.unwrap_err(),
            PipelineError::Unimplemented(_)
        ));
        assert!(matches!(
            engine.stop(Uuid::nil()).await.unwrap_err(),
            PipelineError::Unimplemented(_)
        ));
    }
}
