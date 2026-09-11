//! Prometheus metrics for the recording sink.
//!
//! Registered into a caller-supplied [`prometheus::Registry`] the same way
//! `telemetry::register_request_metrics` registers the service's base HTTP
//! metrics -- this chunk doesn't own `AppState`/`main.rs` wiring (S1/S2), so
//! it exposes [`register_metrics`] for whichever later chunk wires
//! [`super::RecordSink`] into the running service to call once against the
//! shared registry, instead of this module reaching into `http::AppState`
//! itself.

use prometheus::{
    HistogramOpts, HistogramVec, IntCounter, IntCounterVec, IntGauge, Opts, Registry,
};

/// Handles for the recording sink's Prometheus series. All four series
/// named in the S8 task scope, plus an upload-latency histogram per
/// `rules/critical-rules.md` Observability ("histograms for load/latency
/// first").
#[derive(Clone)]
pub struct RecordMetrics {
    pub segments_uploaded_total: IntCounter,
    pub upload_bytes_total: IntCounter,
    /// Labeled by failure `reason` (`endpoint_unreachable`,
    /// `access_denied`, `bucket_not_found`, `spool_exhausted`,
    /// `upload_failed`).
    pub upload_failures_total: IntCounterVec,
    /// Current bytes held in the local spool (segments written but not yet
    /// uploaded), summed per pipeline's watcher poll cycle.
    pub spool_bytes: IntGauge,
    pub upload_duration_seconds: HistogramVec,
}

/// Registers the recording sink's metrics against `registry` and returns
/// handles for the watcher loop to record into. Must be called at most once
/// per `registry` (a `prometheus::Registry` panics on duplicate
/// registration) -- mirrors
/// [`crate::telemetry::register_request_metrics`]'s contract.
pub fn register_metrics(registry: &Registry) -> RecordMetrics {
    let segments_uploaded_total = IntCounter::new(
        "recording_segments_uploaded_total",
        "Total recording segments successfully uploaded to object storage",
    )
    .expect("valid metric definition");
    registry
        .register(Box::new(segments_uploaded_total.clone()))
        .expect("register recording_segments_uploaded_total");

    let upload_bytes_total = IntCounter::new(
        "recording_upload_bytes_total",
        "Total bytes of recording segments uploaded to object storage",
    )
    .expect("valid metric definition");
    registry
        .register(Box::new(upload_bytes_total.clone()))
        .expect("register recording_upload_bytes_total");

    let upload_failures_total = IntCounterVec::new(
        Opts::new(
            "recording_upload_failures_total",
            "Total recording segment upload failures, labeled by reason",
        ),
        &["reason"],
    )
    .expect("valid metric definition");
    registry
        .register(Box::new(upload_failures_total.clone()))
        .expect("register recording_upload_failures_total");

    let spool_bytes = IntGauge::new(
        "recording_spool_bytes",
        "Current bytes held in the local recording spool awaiting upload",
    )
    .expect("valid metric definition");
    registry
        .register(Box::new(spool_bytes.clone()))
        .expect("register recording_spool_bytes");

    let upload_duration_seconds = HistogramVec::new(
        HistogramOpts::new(
            "recording_upload_duration_seconds",
            "Recording segment upload duration in seconds, labeled by outcome",
        ),
        &["outcome"],
    )
    .expect("valid metric definition");
    registry
        .register(Box::new(upload_duration_seconds.clone()))
        .expect("register recording_upload_duration_seconds");

    RecordMetrics {
        segments_uploaded_total,
        upload_bytes_total,
        upload_failures_total,
        spool_bytes,
        upload_duration_seconds,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn register_metrics_produces_all_four_named_series_plus_the_latency_histogram() {
        let registry = Registry::new();
        let metrics = register_metrics(&registry);
        metrics.segments_uploaded_total.inc();
        metrics.upload_bytes_total.inc_by(1024);
        metrics
            .upload_failures_total
            .with_label_values(&["access_denied"])
            .inc();
        metrics.spool_bytes.set(4096);
        metrics
            .upload_duration_seconds
            .with_label_values(&["success"])
            .observe(0.25);

        let families = registry.gather();
        let names: Vec<&str> = families.iter().map(|f| f.name()).collect();
        assert!(names.contains(&"recording_segments_uploaded_total"));
        assert!(names.contains(&"recording_upload_bytes_total"));
        assert!(names.contains(&"recording_upload_failures_total"));
        assert!(names.contains(&"recording_spool_bytes"));
        assert!(names.contains(&"recording_upload_duration_seconds"));
    }

    #[test]
    #[should_panic(expected = "register recording_segments_uploaded_total")]
    fn registering_twice_against_the_same_registry_panics() {
        let registry = Registry::new();
        register_metrics(&registry);
        register_metrics(&registry);
    }
}
