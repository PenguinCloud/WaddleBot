//! HLS egress sink (issue #287 S7): the [`OutputSink`] implementation that
//! supervises `ffmpeg`-written HLS output on disk (directory lifecycle,
//! segment/byte/playlist-age metrics, delayed cleanup on stop), plus the
//! public serving surface for the files it supervises.
//!
//! - [`output`] -- disk layout + the `ffmpeg` argv fragment (spec §4),
//!   usable synchronously by `pipeline::ffmpeg`'s (S3) argv builder before
//!   this sink's async lifecycle even starts.
//! - [`serve`] -- the public `GET /live/...` axum routes that read back
//!   what ffmpeg wrote; see [`serve::hls_router`] for the mount point.

pub mod output;
pub mod serve;

pub use output::HlsOutputTarget;
pub use serve::{
    hls_router, EmptyRunningPipelines, HlsRouterState, RunningPipeline, RunningPipelines,
};

use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, SystemTime};

use prometheus::{GaugeVec, IntCounterVec, Opts};

use crate::egress::{OutputSink, SinkError};
use crate::pipeline::model::{HlsVariant, OutputSpec, PipelineId};

/// Default background poll interval for the segment/byte/playlist-age
/// tracker -- see [`HlsSink::with_intervals`] to override (tests use a much
/// shorter interval to stay fast and deterministic).
const DEFAULT_POLL_INTERVAL: Duration = Duration::from_secs(2);
/// Spec default: how long a stopped pipeline's directory is kept on disk
/// for late viewers before cleanup removes it (spec §1).
pub const DEFAULT_CLEANUP_DELAY: Duration = Duration::from_secs(30);

/// Prometheus metrics owned by [`HlsSink`], registered once against
/// whichever [`prometheus::Registry`] the caller passes to [`HlsSink::new`]
/// (this service's shared registry, see `http::AppState`). Labeled by
/// `variant`/`profile` only -- never `pipeline_id`, an unbounded
/// per-stream cardinality axis -- matching this crate's `mode` label
/// convention (`rules/critical-rules.md` Observability): operators see the
/// active delivery path, not a per-stream label explosion.
#[derive(Clone)]
struct HlsMetrics {
    segments_written_total: IntCounterVec,
    bytes_total: IntCounterVec,
    playlist_age_seconds: GaugeVec,
}

impl HlsMetrics {
    fn register(registry: &prometheus::Registry) -> Self {
        let segments_written_total = IntCounterVec::new(
            Opts::new(
                "hls_segments_written_total",
                "Total HLS media segments observed written to disk, labeled by variant/profile",
            ),
            &["variant", "profile"],
        )
        .expect("valid metric definition");
        registry
            .register(Box::new(segments_written_total.clone()))
            .expect("register hls_segments_written_total");

        let bytes_total = IntCounterVec::new(
            Opts::new(
                "hls_bytes_total",
                "Total bytes of HLS segment data observed written to disk",
            ),
            &["variant", "profile"],
        )
        .expect("valid metric definition");
        registry
            .register(Box::new(bytes_total.clone()))
            .expect("register hls_bytes_total");

        let playlist_age_seconds = GaugeVec::new(
            Opts::new(
                "hls_playlist_age_s",
                "Seconds since the media playlist file was last modified",
            ),
            &["variant", "profile"],
        )
        .expect("valid metric definition");
        registry
            .register(Box::new(playlist_age_seconds.clone()))
            .expect("register hls_playlist_age_s");

        Self {
            segments_written_total,
            bytes_total,
            playlist_age_seconds,
        }
    }
}

/// One active output target's supervision handle.
struct TrackedTarget {
    poll_handle: tokio::task::JoinHandle<()>,
}

/// One pipeline's HLS state: which community it belongs to (set via
/// [`HlsSink::register_pipeline`]) plus every active output target started
/// for it (one per profile/variant pair).
#[derive(Default)]
struct PipelineState {
    community_id: Option<String>,
    targets: Vec<TrackedTarget>,
}

/// HLS egress sink -- see module docs. Holds no per-request state beyond
/// its own bookkeeping `Mutex`; safe to share as `Arc<HlsSink>` across
/// however many pipelines the supervisor (S3) runs concurrently.
pub struct HlsSink {
    data_dir: PathBuf,
    poll_interval: Duration,
    cleanup_delay: Duration,
    metrics: HlsMetrics,
    state: Mutex<HashMap<PipelineId, PipelineState>>,
}

impl HlsSink {
    /// Builds a sink rooted at `data_dir` (`STREAM_DATA_DIR`), registering
    /// its metrics against `registry`, using the spec-default poll interval
    /// and cleanup delay.
    pub fn new(data_dir: PathBuf, registry: &prometheus::Registry) -> Self {
        Self::with_intervals(
            data_dir,
            registry,
            DEFAULT_POLL_INTERVAL,
            DEFAULT_CLEANUP_DELAY,
        )
    }

    /// Like [`Self::new`], with an overridden cleanup delay (spec default:
    /// 30s after `stop()` before the directory is removed).
    pub fn with_cleanup_delay(
        data_dir: PathBuf,
        registry: &prometheus::Registry,
        cleanup_delay: Duration,
    ) -> Self {
        Self::with_intervals(data_dir, registry, DEFAULT_POLL_INTERVAL, cleanup_delay)
    }

    /// Full constructor: overrides both the segment-tracking poll interval
    /// and the post-stop cleanup delay. Tests use short intervals here to
    /// stay fast and deterministic instead of waiting on real 2s/30s
    /// timers.
    pub fn with_intervals(
        data_dir: PathBuf,
        registry: &prometheus::Registry,
        poll_interval: Duration,
        cleanup_delay: Duration,
    ) -> Self {
        Self {
            data_dir,
            poll_interval,
            cleanup_delay,
            metrics: HlsMetrics::register(registry),
            state: Mutex::new(HashMap::new()),
        }
    }

    /// Associates `pipeline_id` with `community_id` before [`OutputSink::
    /// start`] is called for it.
    ///
    /// Not part of the [`OutputSink`] trait -- `start(pipeline_id, spec)`'s
    /// signature is frozen (`egress::mod`, owned by S1) and never carries
    /// `community_id`, even though the enclosing `PipelineSpec` does
    /// (`pipeline::model`). The pipeline supervisor (S3) is expected to
    /// call this alongside building/dispatching a `PipelineSpec` (which
    /// does carry `community_id`) before invoking `start` for each of its
    /// `OutputSpec::Hls` entries. `start` returns `Err` if this was never
    /// called for a given `pipeline_id` -- a missing association is a
    /// caller bug, surfaced as a `Result`, never a panic.
    pub fn register_pipeline(&self, pipeline_id: PipelineId, community_id: impl Into<String>) {
        let mut state = lock_state(&self.state);
        state.entry(pipeline_id).or_default().community_id = Some(community_id.into());
    }

    fn community_id_for(&self, pipeline_id: PipelineId) -> Option<String> {
        lock_state(&self.state)
            .get(&pipeline_id)
            .and_then(|s| s.community_id.clone())
    }
}

impl OutputSink for HlsSink {
    async fn start(&self, pipeline_id: PipelineId, spec: OutputSpec) -> Result<(), SinkError> {
        let (variant, profile) = match spec {
            OutputSpec::Hls { variant, profile } => (variant, profile),
            other => {
                return Err(SinkError::Other(anyhow::anyhow!(
                    "HlsSink received a non-HLS OutputSpec: {other:?}"
                )));
            }
        };

        if !output::is_safe_path_segment(&profile) {
            return Err(SinkError::Other(anyhow::anyhow!(
                "unsafe HLS profile name: {profile:?}"
            )));
        }

        let community_id = self.community_id_for(pipeline_id).ok_or_else(|| {
            SinkError::Other(anyhow::anyhow!(
                "pipeline {pipeline_id} has no registered community_id -- \
                 call HlsSink::register_pipeline before start"
            ))
        })?;

        let target = HlsOutputTarget::new(&self.data_dir, pipeline_id, &profile, variant);
        create_output_dir(&target.output_dir)
            .await
            .map_err(|err| SinkError::Other(err.into()))?;

        tracing::info!(
            %pipeline_id,
            %community_id,
            profile = %profile,
            ?variant,
            dir = %target.output_dir.display(),
            "HlsSink starting output"
        );

        let poll_handle = spawn_poller(
            target,
            profile,
            variant,
            self.metrics.clone(),
            self.poll_interval,
        );

        let mut state = lock_state(&self.state);
        state
            .entry(pipeline_id)
            .or_default()
            .targets
            .push(TrackedTarget { poll_handle });
        Ok(())
    }

    async fn stop(&self, pipeline_id: PipelineId) -> Result<(), SinkError> {
        let removed = lock_state(&self.state).remove(&pipeline_id);
        let Some(pipeline_state) = removed else {
            // Idempotent per the trait's contract: stopping an unknown or
            // already-stopped pipeline is not an error.
            return Ok(());
        };
        for tracked in &pipeline_state.targets {
            tracked.poll_handle.abort();
        }

        let dir = output::hls_root(&self.data_dir).join(pipeline_id.to_string());
        let delay = self.cleanup_delay;
        tracing::info!(%pipeline_id, dir = %dir.display(), cleanup_delay_s = delay.as_secs(), "HlsSink stopping output, cleanup scheduled");
        tokio::spawn(async move {
            tokio::time::sleep(delay).await;
            match tokio::fs::remove_dir_all(&dir).await {
                Ok(()) => tracing::debug!(dir = %dir.display(), "HLS directory cleaned up"),
                Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
                Err(err) => {
                    tracing::warn!(dir = %dir.display(), error = %err, "HLS cleanup failed to remove directory");
                }
            }
        });

        Ok(())
    }
}

/// Locks `state`, recovering from poisoning instead of panicking -- a panic
/// while handling one pipeline's start/stop must never permanently wedge
/// the sink for every other pipeline it supervises.
fn lock_state(
    state: &Mutex<HashMap<PipelineId, PipelineState>>,
) -> std::sync::MutexGuard<'_, HashMap<PipelineId, PipelineState>> {
    state
        .lock()
        .unwrap_or_else(std::sync::PoisonError::into_inner)
}

/// Creates `dir` (and its parents) with mode `0750` on Unix -- the
/// ffmpeg-written segment tree is unreadable to other unprivileged users in
/// the container while still readable/writable by this service's own
/// `appuser`, see `rules/client.md` Rootless Containers.
async fn create_output_dir(dir: &std::path::Path) -> std::io::Result<()> {
    tokio::fs::create_dir_all(dir).await?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        tokio::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o750)).await?;
    }
    Ok(())
}

fn variant_label(variant: HlsVariant) -> &'static str {
    match variant {
        HlsVariant::Ll => "ll",
        HlsVariant::Std => "std",
    }
}

/// Background task: every `poll_interval`, scans `target.output_dir` for
/// segment files (`*.m4s`) and increments the sink's Prometheus counters by
/// the *delta* since the last poll (counters are monotonic; a directory
/// that shrinks as `delete_segments` rolls the playlist window must never
/// decrement them), plus refreshes the media playlist's on-disk age gauge.
/// Aborted by [`HlsSink::stop`].
fn spawn_poller(
    target: HlsOutputTarget,
    profile: String,
    variant: HlsVariant,
    metrics: HlsMetrics,
    poll_interval: Duration,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        let label = variant_label(variant);
        let mut seen_segments: HashSet<PathBuf> = HashSet::new();
        let mut interval = tokio::time::interval(poll_interval);
        loop {
            interval.tick().await;

            let mut new_segment_count: u64 = 0;
            let mut new_bytes: u64 = 0;
            if let Ok(mut entries) = tokio::fs::read_dir(&target.output_dir).await {
                while let Ok(Some(entry)) = entries.next_entry().await {
                    let path = entry.path();
                    if path.extension().and_then(|e| e.to_str()) != Some("m4s") {
                        continue;
                    }
                    if !seen_segments.insert(path) {
                        continue;
                    }
                    if let Ok(meta) = entry.metadata().await {
                        new_segment_count += 1;
                        new_bytes += meta.len();
                    }
                }
            }
            if new_segment_count > 0 {
                metrics
                    .segments_written_total
                    .with_label_values(&[label, &profile])
                    .inc_by(new_segment_count);
                metrics
                    .bytes_total
                    .with_label_values(&[label, &profile])
                    .inc_by(new_bytes);
            }

            let age_seconds = tokio::fs::metadata(target.media_playlist_path())
                .await
                .ok()
                .and_then(|meta| meta.modified().ok())
                .and_then(|modified| SystemTime::now().duration_since(modified).ok())
                .map(|age| age.as_secs_f64());
            if let Some(age_seconds) = age_seconds {
                metrics
                    .playlist_age_seconds
                    .with_label_values(&[label, &profile])
                    .set(age_seconds);
            }
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    fn temp_data_dir() -> PathBuf {
        std::env::temp_dir().join(format!("svc-streaming-hls-sink-{}", Uuid::new_v4()))
    }

    fn fast_sink(data_dir: PathBuf, registry: &prometheus::Registry) -> HlsSink {
        HlsSink::with_intervals(
            data_dir,
            registry,
            Duration::from_millis(20),
            Duration::from_millis(50),
        )
    }

    #[tokio::test]
    async fn start_without_register_pipeline_errors() {
        let data_dir = temp_data_dir();
        let sink = fast_sink(data_dir.clone(), &prometheus::Registry::new());
        let err = sink
            .start(
                Uuid::new_v4(),
                OutputSpec::Hls {
                    variant: HlsVariant::Std,
                    profile: "1080p60".into(),
                },
            )
            .await
            .unwrap_err();
        assert!(matches!(err, SinkError::Other(_)));
    }

    #[tokio::test]
    async fn start_creates_pipeline_profile_directory() {
        let data_dir = temp_data_dir();
        let sink = fast_sink(data_dir.clone(), &prometheus::Registry::new());
        let pipeline_id = Uuid::new_v4();
        sink.register_pipeline(pipeline_id, "community-1");

        sink.start(
            pipeline_id,
            OutputSpec::Hls {
                variant: HlsVariant::Std,
                profile: "1080p60".into(),
            },
        )
        .await
        .expect("registered pipeline must start");

        let expected_dir = HlsOutputTarget::directory(&data_dir, pipeline_id, "1080p60");
        assert!(tokio::fs::metadata(&expected_dir).await.unwrap().is_dir());

        sink.stop(pipeline_id).await.unwrap();
        tokio::fs::remove_dir_all(&data_dir).await.ok();
    }

    #[tokio::test]
    async fn stop_is_idempotent_for_unknown_pipeline() {
        let sink = fast_sink(temp_data_dir(), &prometheus::Registry::new());
        assert!(sink.stop(Uuid::new_v4()).await.is_ok());
    }

    #[tokio::test]
    async fn stop_keeps_directory_briefly_then_cleans_it_up() {
        let data_dir = temp_data_dir();
        let sink = fast_sink(data_dir.clone(), &prometheus::Registry::new());
        let pipeline_id = Uuid::new_v4();
        sink.register_pipeline(pipeline_id, "community-1");
        sink.start(
            pipeline_id,
            OutputSpec::Hls {
                variant: HlsVariant::Std,
                profile: "1080p60".into(),
            },
        )
        .await
        .unwrap();

        let pipeline_dir = output::hls_root(&data_dir).join(pipeline_id.to_string());
        sink.stop(pipeline_id).await.unwrap();

        // Immediately after stop() the directory (last playlist) is still
        // present for late viewers -- cleanup_delay is 50ms in this test.
        assert!(tokio::fs::metadata(&pipeline_dir).await.is_ok());

        tokio::time::sleep(Duration::from_millis(200)).await;
        assert!(
            tokio::fs::metadata(&pipeline_dir).await.is_err(),
            "directory should be removed after the cleanup delay elapses"
        );
    }

    #[tokio::test]
    async fn metrics_track_new_segments_and_playlist_age() {
        let data_dir = temp_data_dir();
        let registry = prometheus::Registry::new();
        let sink = fast_sink(data_dir.clone(), &registry);
        let pipeline_id = Uuid::new_v4();
        sink.register_pipeline(pipeline_id, "community-1");
        sink.start(
            pipeline_id,
            OutputSpec::Hls {
                variant: HlsVariant::Std,
                profile: "1080p60".into(),
            },
        )
        .await
        .unwrap();

        let dir = HlsOutputTarget::directory(&data_dir, pipeline_id, "1080p60");
        tokio::fs::write(dir.join("index.m3u8"), b"#EXTM3U\n")
            .await
            .unwrap();
        tokio::fs::write(dir.join("segment_00001.m4s"), vec![0u8; 128])
            .await
            .unwrap();

        // Poll interval is 20ms -- give it several ticks to observe the
        // new segment and playlist file.
        tokio::time::sleep(Duration::from_millis(150)).await;

        let rendered = crate::telemetry::render_metrics(&registry).unwrap();
        assert!(rendered.contains("hls_segments_written_total"));
        assert!(rendered.contains("variant=\"std\""));
        assert!(rendered.contains("profile=\"1080p60\""));
        assert!(rendered.contains("hls_bytes_total"));
        assert!(rendered.contains("hls_playlist_age_s"));

        sink.stop(pipeline_id).await.unwrap();
        tokio::time::sleep(Duration::from_millis(100)).await;
        tokio::fs::remove_dir_all(&data_dir).await.ok();
    }

    #[tokio::test]
    async fn non_hls_output_spec_is_rejected() {
        let sink = fast_sink(temp_data_dir(), &prometheus::Registry::new());
        let pipeline_id = Uuid::new_v4();
        sink.register_pipeline(pipeline_id, "community-1");
        let err = sink
            .start(
                pipeline_id,
                OutputSpec::Whep {
                    profile: "1080p60".into(),
                },
            )
            .await
            .unwrap_err();
        assert!(matches!(err, SinkError::Other(_)));
    }
}
