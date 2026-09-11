//! [`TrackFanout`]: the SFU primitive behind every WHEP output --
//! `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md` §4/§9.4 picks
//! "one encode, RTP forwarded to N PeerConnections" over a `-f rtp`-per-viewer
//! ffmpeg process. One [`TrackFanout`] exists per (pipeline, media kind)
//! pair; a single producer (the WHIP publisher's `on_track` handler, or
//! [`crate::rtc::rtp_leg::RtpIngress`] reading a transcoded ffmpeg leg)
//! publishes RTP packets that every subscribed WHEP viewer receives.
//!
//! Built on `webrtc::runtime`'s broadcast primitive (`async-broadcast`
//! under the hood) rather than rolling a bespoke ring buffer: it already
//! gives every subscriber an independent cursor and reports exactly how
//! many packets a slow subscriber missed
//! ([`webrtc::runtime::BroadcastRecvError::Lagged`]), which is the
//! per-subscriber drop count this module needs.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use rtc::rtp::Packet;
use webrtc::runtime::{broadcast_channel, BroadcastReceiver, BroadcastRecvError, BroadcastSender};

use crate::rtc::metrics::RtcMetrics;

/// Bounded broadcast capacity: packets a subscriber may fall behind by
/// before it starts losing them to [`BroadcastRecvError::Lagged`]. 512
/// packets at typical 1200-byte RTP payloads is ~600 KiB per fanout and,
/// at 30fps video, several hundred milliseconds of backlog -- generous
/// enough to absorb a scheduling hiccup without growing unbounded memory
/// under a genuinely stuck subscriber (the point of dropping instead of
/// blocking the publisher).
const FANOUT_CAPACITY: usize = 512;

/// Broadcasts one media track's RTP packets from a single producer to N
/// WHEP viewer subscribers. `Clone`-free by design: shared via `Arc` so
/// every subscriber and the publisher hold the same fanout.
#[derive(Debug)]
pub struct TrackFanout {
    tx: BroadcastSender<Packet>,
    subscriber_count: AtomicUsize,
}

impl TrackFanout {
    /// Creates an empty fanout with no publisher or subscribers yet.
    pub fn new() -> Arc<Self> {
        Arc::new(Self {
            tx: broadcast_channel(FANOUT_CAPACITY),
            subscriber_count: AtomicUsize::new(0),
        })
    }

    /// Publishes one RTP packet to every current subscriber. Never blocks
    /// or fails on a slow subscriber -- `async-broadcast`'s overflow mode
    /// drops the oldest buffered packet for that subscriber instead
    /// (surfaced to it as [`BroadcastRecvError::Lagged`] on its next
    /// `recv`), so one stuck viewer can never stall the publisher or any
    /// other viewer. A publish with zero subscribers is a no-op.
    pub fn publish(&self, packet: Packet) {
        let _ = self.tx.send(packet);
    }

    /// Subscribes a new WHEP viewer, returning a handle whose `recv` drives
    /// that viewer's forwarding loop. Dropping the returned
    /// [`FanoutSubscriber`] unsubscribes and decrements
    /// [`Self::subscriber_count`].
    pub fn subscribe(self: &Arc<Self>) -> FanoutSubscriber {
        self.subscriber_count.fetch_add(1, Ordering::AcqRel);
        FanoutSubscriber {
            rx: self.tx.subscribe(),
            fanout: Arc::clone(self),
        }
    }

    /// Current subscriber (viewer) count -- used to enforce
    /// `WHEP_MAX_VIEWERS` before a new subscription is created.
    pub fn subscriber_count(&self) -> usize {
        self.subscriber_count.load(Ordering::Acquire)
    }
}

impl Default for TrackFanout {
    fn default() -> Self {
        // `Arc::new` is folded into `Self::new`; `Default` exists only so
        // this type satisfies derive bounds elsewhere without callers
        // reaching for `Arc::new(TrackFanout::new_inner())` -- prefer
        // `TrackFanout::new()`, which already returns the `Arc`.
        Self {
            tx: broadcast_channel(FANOUT_CAPACITY),
            subscriber_count: AtomicUsize::new(0),
        }
    }
}

/// One WHEP viewer's subscription to a [`TrackFanout`]. Not `Clone` --
/// each viewer's forwarding task owns exactly one, so `Drop` accurately
/// reflects unsubscription.
pub struct FanoutSubscriber {
    rx: BroadcastReceiver<Packet>,
    fanout: Arc<TrackFanout>,
}

impl FanoutSubscriber {
    /// Waits for the next packet, transparently skipping past any gap and
    /// recording it in `metrics.packets_dropped_total`. Returns `None` once
    /// the fanout's publisher side is gone and the backlog is drained --
    /// the caller's forwarding loop should end.
    pub async fn recv(&mut self, metrics: &RtcMetrics) -> Option<Packet> {
        loop {
            match self.rx.recv().await {
                Ok(packet) => return Some(packet),
                Err(BroadcastRecvError::Lagged(skipped)) => {
                    metrics.packets_dropped_total.inc_by(skipped);
                    continue;
                }
                Err(BroadcastRecvError::Closed) => return None,
            }
        }
    }
}

impl Drop for FanoutSubscriber {
    fn drop(&mut self) {
        self.fanout.subscriber_count.fetch_sub(1, Ordering::AcqRel);
    }
}

/// One video [`TrackFanout`] plus one audio [`TrackFanout`] -- the unit
/// `src/ingest/whip.rs` and `src/egress/whep.rs` register/subscribe as a
/// pair, per this module's own doc comment: "one `TrackFanout` exists per
/// (pipeline, media kind) pair". Kept together so a WHIP token or
/// `PipelineId` maps to exactly one `MediaFanouts` in
/// `WhipState`/`WhepState`'s registries, instead of the two kinds getting
/// mixed into a single fanout (which would forward video packets to an
/// audio viewer track and vice versa).
#[derive(Clone)]
pub struct MediaFanouts {
    pub video: Arc<TrackFanout>,
    pub audio: Arc<TrackFanout>,
}

impl MediaFanouts {
    pub fn new() -> Self {
        Self {
            video: TrackFanout::new(),
            audio: TrackFanout::new(),
        }
    }
}

impl Default for MediaFanouts {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rtc::rtp::Header;

    fn sample_packet(seq: u16) -> Packet {
        Packet {
            header: Header {
                sequence_number: seq,
                ssrc: 42,
                payload_type: 96,
                ..Default::default()
            },
            payload: bytes::Bytes::from_static(b"payload"),
        }
    }

    #[tokio::test]
    async fn subscriber_receives_published_packet() {
        let fanout = TrackFanout::new();
        let mut sub = fanout.subscribe();
        fanout.publish(sample_packet(1));
        let registry = prometheus::Registry::new();
        let metrics = RtcMetrics::register(&registry).unwrap();
        let received = sub.recv(&metrics).await.expect("packet delivered");
        assert_eq!(received.header.sequence_number, 1);
    }

    #[tokio::test]
    async fn subscribe_and_drop_updates_subscriber_count() {
        let fanout = TrackFanout::new();
        assert_eq!(fanout.subscriber_count(), 0);
        let sub = fanout.subscribe();
        assert_eq!(fanout.subscriber_count(), 1);
        drop(sub);
        assert_eq!(fanout.subscriber_count(), 0);
    }

    #[tokio::test]
    async fn multiple_subscribers_each_receive_the_same_packet() {
        let fanout = TrackFanout::new();
        let mut sub_a = fanout.subscribe();
        let mut sub_b = fanout.subscribe();
        fanout.publish(sample_packet(7));
        let registry = prometheus::Registry::new();
        let metrics = RtcMetrics::register(&registry).unwrap();
        assert_eq!(
            sub_a.recv(&metrics).await.unwrap().header.sequence_number,
            7
        );
        assert_eq!(
            sub_b.recv(&metrics).await.unwrap().header.sequence_number,
            7
        );
    }

    #[tokio::test]
    async fn slow_subscriber_records_drops_via_lagged() {
        let fanout = TrackFanout::new();
        let mut sub = fanout.subscribe();
        // Publish well past FANOUT_CAPACITY without ever calling recv(), so
        // the subscriber's cursor falls behind and the next recv() must
        // observe at least one Lagged(_) before catching up.
        for seq in 0..(FANOUT_CAPACITY as u16 * 2) {
            fanout.publish(sample_packet(seq));
        }
        let registry = prometheus::Registry::new();
        let metrics = RtcMetrics::register(&registry).unwrap();
        let _ = sub.recv(&metrics).await.expect("catches up past the gap");
        assert!(metrics.packets_dropped_total.get() > 0);
    }

    #[tokio::test]
    async fn publish_with_no_subscribers_is_a_harmless_no_op() {
        let fanout = TrackFanout::new();
        fanout.publish(sample_packet(1));
        assert_eq!(fanout.subscriber_count(), 0);
    }
}
