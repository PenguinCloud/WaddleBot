//! Integration tests for `HlsSink` (issue #287 S7) through its public API
//! only -- directory lifecycle, `register_pipeline` contract, and delayed
//! cleanup on `stop()`. Segment/byte/playlist-age metric tracking and the
//! `ffmpeg_output_args` fragments themselves are covered by the inline
//! `#[cfg(test)]` modules in `src/egress/hls.rs` / `src/egress/hls/
//! output.rs`, which need access to private fields these integration tests
//! don't.

use std::time::Duration;

use svc_streaming::egress::hls::{HlsOutputTarget, HlsSink};
use svc_streaming::egress::OutputSink;
use svc_streaming::pipeline::model::{HlsVariant, OutputSpec};
use uuid::Uuid;

fn temp_data_dir(tag: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!(
        "svc-streaming-hls-sink-it-{tag}-{}",
        Uuid::new_v4()
    ))
}

fn fast_sink(data_dir: std::path::PathBuf, registry: &prometheus::Registry) -> HlsSink {
    HlsSink::with_intervals(
        data_dir,
        registry,
        Duration::from_millis(20),
        Duration::from_millis(50),
    )
}

#[tokio::test]
async fn register_then_start_creates_the_pipeline_profile_directory() {
    let data_dir = temp_data_dir("layout");
    let sink = fast_sink(data_dir.clone(), &prometheus::Registry::new());
    let pipeline_id = Uuid::new_v4();
    sink.register_pipeline(pipeline_id, "community-42");

    sink.start(
        pipeline_id,
        OutputSpec::Hls {
            variant: HlsVariant::Ll,
            profile: "720p30".into(),
        },
    )
    .await
    .expect("registered pipeline must start");

    let expected_dir = HlsOutputTarget::directory(&data_dir, pipeline_id, "720p30");
    let meta = tokio::fs::metadata(&expected_dir)
        .await
        .expect("output directory must exist after start");
    assert!(meta.is_dir());

    sink.stop(pipeline_id).await.unwrap();
    tokio::fs::remove_dir_all(&data_dir).await.ok();
}

#[tokio::test]
async fn start_without_register_pipeline_is_an_error_not_a_panic() {
    let sink = fast_sink(temp_data_dir("unregistered"), &prometheus::Registry::new());
    let result = sink
        .start(
            Uuid::new_v4(),
            OutputSpec::Hls {
                variant: HlsVariant::Std,
                profile: "1080p60".into(),
            },
        )
        .await;
    assert!(result.is_err());
}

#[tokio::test]
async fn stop_is_idempotent_and_never_errors_for_unknown_pipeline() {
    let sink = fast_sink(temp_data_dir("idempotent"), &prometheus::Registry::new());
    let pipeline_id = Uuid::new_v4();
    assert!(sink.stop(pipeline_id).await.is_ok());
    assert!(
        sink.stop(pipeline_id).await.is_ok(),
        "second stop() must also be Ok"
    );
}

#[tokio::test]
async fn stop_keeps_the_directory_for_late_viewers_then_cleans_it_up() {
    let data_dir = temp_data_dir("cleanup");
    let sink = fast_sink(data_dir.clone(), &prometheus::Registry::new());
    let pipeline_id = Uuid::new_v4();
    sink.register_pipeline(pipeline_id, "community-42");
    sink.start(
        pipeline_id,
        OutputSpec::Hls {
            variant: HlsVariant::Std,
            profile: "1080p60".into(),
        },
    )
    .await
    .unwrap();

    let pipeline_dir = HlsOutputTarget::directory(&data_dir, pipeline_id, "1080p60")
        .parent()
        .unwrap()
        .to_path_buf();

    sink.stop(pipeline_id).await.unwrap();
    assert!(
        tokio::fs::metadata(&pipeline_dir).await.is_ok(),
        "directory must survive immediately after stop() for late viewers"
    );

    tokio::time::sleep(Duration::from_millis(200)).await;
    assert!(
        tokio::fs::metadata(&pipeline_dir).await.is_err(),
        "directory must be removed once the cleanup delay elapses"
    );
}
