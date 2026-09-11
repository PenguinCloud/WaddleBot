//! Prometheus metrics for WHIP/WHEP session lifecycle and RTP flow, per the
//! S6 task spec's required series: `rtc_sessions_active{kind}`,
//! `rtc_rtp_packets_total{direction}`, `rtc_packets_dropped_total`,
//! `rtc_ice_failures_total`.
//!
//! **Integration gap:** `src/http/mod.rs`'s `AppState` owns the single
//! `Arc<prometheus::Registry>` this service scrapes at `/metrics`
//! (`crate::http::AppState::new` -> `crate::telemetry::register_request_metrics`),
//! and that file is outside this chunk's ownership. [`RtcMetrics::register`]
//! mirrors that same registration pattern so wiring it into `AppState` is a
//! one-line follow-up (`rtc::metrics::RtcMetrics::register(&metrics)`
//! alongside the existing `register_request_metrics` call) -- not done here.

use prometheus::{IntCounter, IntCounterVec, IntGaugeVec, Opts, Registry};

/// Registered WHIP/WHEP metric handles, cheap to clone (each inner type is
/// itself a cheap `Arc`-backed handle per the `prometheus` crate).
#[derive(Debug, Clone)]
pub struct RtcMetrics {
    /// Active sessions, labeled `kind` = `"whip"` | `"whep"`.
    pub sessions_active: IntGaugeVec,
    /// RTP packets, labeled `direction` = `"ingress"` (WHIP inbound),
    /// `"egress"` (WHEP outbound to a viewer), or `"transcoded_ingest"`
    /// (local UDP read from an ffmpeg `-f rtp` leg -- see
    /// [`crate::rtc::rtp_leg`]).
    pub rtp_packets_total: IntCounterVec,
    /// Fanout packets dropped because a subscriber (WHEP viewer) fell
    /// behind -- see [`crate::rtc::fanout::TrackFanout`].
    pub packets_dropped_total: IntCounter,
    /// ICE/DTLS connection failures across both WHIP and WHEP sessions.
    pub ice_failures_total: IntCounter,
}

impl RtcMetrics {
    /// Registers every WHIP/WHEP series against `registry`. Safe to call
    /// once per registry; a second registration attempt against the same
    /// registry returns an `AlreadyReg` [`prometheus::Error`].
    pub fn register(registry: &Registry) -> Result<Self, prometheus::Error> {
        let sessions_active = IntGaugeVec::new(
            Opts::new("rtc_sessions_active", "Active WHIP/WHEP WebRTC sessions"),
            &["kind"],
        )?;
        let rtp_packets_total = IntCounterVec::new(
            Opts::new("rtc_rtp_packets_total", "RTP packets processed"),
            &["direction"],
        )?;
        let packets_dropped_total = IntCounter::new(
            "rtc_packets_dropped_total",
            "RTP packets dropped from a fanout subscriber that fell behind",
        )?;
        let ice_failures_total = IntCounter::new(
            "rtc_ice_failures_total",
            "WHIP/WHEP sessions that reached RTCPeerConnectionState::Failed",
        )?;

        registry.register(Box::new(sessions_active.clone()))?;
        registry.register(Box::new(rtp_packets_total.clone()))?;
        registry.register(Box::new(packets_dropped_total.clone()))?;
        registry.register(Box::new(ice_failures_total.clone()))?;

        Ok(Self {
            sessions_active,
            rtp_packets_total,
            packets_dropped_total,
            ice_failures_total,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registers_all_four_series_once() {
        let registry = Registry::new();
        let metrics = RtcMetrics::register(&registry).expect("first registration succeeds");
        metrics.sessions_active.with_label_values(&["whip"]).set(1);
        metrics
            .rtp_packets_total
            .with_label_values(&["ingress"])
            .inc();
        metrics.packets_dropped_total.inc_by(3);
        metrics.ice_failures_total.inc();

        let families = registry.gather();
        let names: Vec<_> = families.iter().map(|f| f.name().to_string()).collect();
        for expected in [
            "rtc_sessions_active",
            "rtc_rtp_packets_total",
            "rtc_packets_dropped_total",
            "rtc_ice_failures_total",
        ] {
            assert!(names.contains(&expected.to_string()), "missing {expected}");
        }
    }

    #[test]
    fn double_registration_against_same_registry_errors() {
        let registry = Registry::new();
        RtcMetrics::register(&registry).unwrap();
        assert!(RtcMetrics::register(&registry).is_err());
    }
}
