//! Relay-sink Prometheus metrics, following the explicit-registry pattern
//! established by `crate::telemetry::register_request_metrics` (register
//! once against the shared `prometheus::Registry` created in
//! `telemetry::init`, hand back typed handles) rather than the crate's
//! process-global default registry -- so these metrics actually appear on
//! this service's `/metrics` surface once a later chunk (the pipeline
//! supervisor, S3) constructs a [`RelaySink`](super::RelaySink) with the
//! app's registry.
//!
//! Histograms-for-load-first (`rules/critical-rules.md` Observability)
//! doesn't apply cleanly to a "currently active" gauge or classified
//! failure counter; `relay_bytes_total` is a counter (cumulative forwarded
//! bytes), not a histogram, for the same reason `http_requests_total` is a
//! counter and duration is the histogram -- there is no relay "duration"
//! signal owned by this chunk yet (that belongs to whichever chunk exposes
//! per-session forward duration).

/// Relay-sink metric handles, registered once via
/// [`register_relay_metrics`].
#[derive(Clone)]
pub struct RelayMetrics {
    /// Number of currently-active relay targets, labeled by pipeline.
    pub relay_targets_active: prometheus::IntGaugeVec,
    /// Total relay target failures, labeled by classified reason
    /// (bounded set -- see `super::health::FailureReasonKind`).
    pub relay_target_failures_total: prometheus::IntCounterVec,
    /// Total bytes forwarded per relay target, labeled by the target's
    /// *redacted* URL (never the raw secret).
    pub relay_bytes_total: prometheus::IntCounterVec,
}

/// Registers this sink's metrics against `registry`. Must be called at
/// most once per `registry` (a `prometheus::Registry` errors on duplicate
/// registration, matching `register_request_metrics`'s contract).
pub fn register_relay_metrics(
    registry: &prometheus::Registry,
) -> Result<RelayMetrics, prometheus::Error> {
    let relay_targets_active = prometheus::IntGaugeVec::new(
        prometheus::Opts::new(
            "svc_streaming_relay_targets_active",
            "Number of currently-active RTMP/SRT relay targets, labeled by pipeline",
        ),
        &["pipeline_id"],
    )?;
    registry.register(Box::new(relay_targets_active.clone()))?;

    let relay_target_failures_total = prometheus::IntCounterVec::new(
        prometheus::Opts::new(
            "svc_streaming_relay_target_failures_total",
            "Total relay target failures, labeled by classified reason",
        ),
        &["reason"],
    )?;
    registry.register(Box::new(relay_target_failures_total.clone()))?;

    let relay_bytes_total = prometheus::IntCounterVec::new(
        prometheus::Opts::new(
            "svc_streaming_relay_bytes_total",
            "Total bytes forwarded per relay target, labeled by the target's redacted URL",
        ),
        &["target"],
    )?;
    registry.register(Box::new(relay_bytes_total.clone()))?;

    Ok(RelayMetrics {
        relay_targets_active,
        relay_target_failures_total,
        relay_bytes_total,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn register_relay_metrics_succeeds_once_per_registry() {
        let registry = prometheus::Registry::new();
        let metrics = register_relay_metrics(&registry).expect("first registration succeeds");
        metrics
            .relay_targets_active
            .with_label_values(&["11111111-1111-1111-1111-111111111111"])
            .set(2);
        metrics
            .relay_target_failures_total
            .with_label_values(&["destination refused connection"])
            .inc();
        metrics
            .relay_bytes_total
            .with_label_values(&["rtmp://host/app/****"])
            .inc_by(1024);

        let families = registry.gather();
        let names: Vec<&str> = families.iter().map(|f| f.name()).collect();
        assert!(names.contains(&"svc_streaming_relay_targets_active"));
        assert!(names.contains(&"svc_streaming_relay_target_failures_total"));
        assert!(names.contains(&"svc_streaming_relay_bytes_total"));
    }

    #[test]
    fn register_relay_metrics_errors_on_duplicate_registration() {
        let registry = prometheus::Registry::new();
        register_relay_metrics(&registry).expect("first registration succeeds");
        assert!(register_relay_metrics(&registry).is_err());
    }
}
