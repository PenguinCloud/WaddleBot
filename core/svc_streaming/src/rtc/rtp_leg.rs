//! [`RtpLeg`] / [`RtpIngress`]: the transcoded-path counterpart to
//! `src/rtc/sdp_writer.rs`'s WHIP-to-ffmpeg bridge. Where that module feeds
//! RTP *into* a spawned ffmpeg, this one reads RTP *out of* one --
//! `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md` §4's WHEP
//! output recipe: "ffmpeg `-f rtp` -> local UDP -> `webrtc-rs`; **SFU
//! model**: one encode, RTP forwarded to N PeerConnections". [`RtpIngress`]
//! is the "local UDP -> webrtc-rs" half: it republishes what it reads into
//! a [`crate::rtc::fanout::TrackFanout`], and every WHEP viewer subscribed
//! to that fanout receives it identically to a pure-copy WHIP source.

use std::io;
use std::net::IpAddr;
use std::sync::Arc;

use bytes::BytesMut;
use rtc::rtp::Packet;
use rtc::shared::marshal::Unmarshal;
use webrtc::runtime::{JoinHandle, Runtime};

use crate::rtc::fanout::TrackFanout;
use crate::rtc::metrics::RtcMetrics;

/// Media kind of one local RTP leg.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RtpLegKind {
    Audio,
    Video,
}

/// Descriptor for one local RTP leg written by a spawned ffmpeg's `-f rtp`
/// output.
///
/// **This is the contract chunk S3's ffmpeg argv builder
/// (`src/pipeline/ffmpeg.rs::FfmpegRunner`, not yet implemented -- see that
/// file's module docs) is expected to produce**, one `RtpLeg` per
/// transcoded output track, once it exists. Documented here, in this
/// chunk's own module, so S6 has a concrete type to program the WHEP
/// transcoded-egress path against ahead of S3 landing, rather than blocking
/// on it entirely -- see this crate's `README.md` Module Ownership table:
/// `src/pipeline/ffmpeg.rs`/`src/pipeline/supervisor.rs` are both still
/// stubs as of this chunk. **Integration blocked on S3**: nothing in this
/// service yet constructs a real `RtpLeg` or calls
/// [`RtpIngress::spawn`] -- that wiring (deciding a `TranscodeProfile`
/// needs a WHEP output, picking the port, passing it to both the ffmpeg
/// argv and here) belongs to `pipeline::supervisor` once it exists.
#[derive(Debug, Clone)]
pub struct RtpLeg {
    /// Local port ffmpeg's `-f rtp` output writes to
    /// (`rtp://127.0.0.1:<port>`); [`RtpIngress`] binds and listens on this
    /// same port, so ffmpeg must be spawned only after `RtpIngress::spawn`
    /// returns successfully (the bind has to happen first).
    pub local_port: u16,
    /// Interface to bind the listening socket on -- normally loopback,
    /// since ffmpeg and this process share a pod/host.
    pub bind_ip: IpAddr,
    pub kind: RtpLegKind,
}

/// Reads UDP datagrams off one [`RtpLeg`]'s local port, unmarshals them as
/// RTP, and republishes them into a [`TrackFanout`] -- the
/// transcoded-output counterpart to the WHIP copy path's direct `on_track`
/// -> [`TrackFanout::publish`] (`src/ingest/whip.rs`).
pub struct RtpIngress {
    handle: Box<dyn JoinHandle>,
}

impl RtpIngress {
    /// Binds `leg.local_port` and spawns the read loop on `runtime`.
    /// Returns as soon as the socket is bound, so a caller can be certain
    /// the port is held *before* telling ffmpeg to start writing to it
    /// (binding is synchronous; the read loop itself runs in the
    /// background for the lifetime of the returned [`RtpIngress`]).
    pub fn spawn(
        runtime: &dyn Runtime,
        leg: RtpLeg,
        fanout: Arc<TrackFanout>,
        metrics: RtcMetrics,
    ) -> io::Result<Self> {
        let std_sock = std::net::UdpSocket::bind((leg.bind_ip, leg.local_port))?;
        let sock = runtime.wrap_udp_socket(std_sock)?;

        let handle = runtime.spawn(Box::pin(async move {
            let mut buf = vec![0u8; 1500];
            loop {
                let (n, _addr) = match sock.recv_from(&mut buf).await {
                    Ok(result) => result,
                    // Socket gone (e.g. process shutdown tearing down the
                    // runtime) -- end the loop rather than spin on errors.
                    Err(_) => break,
                };
                let mut bytes = BytesMut::from(&buf[..n]);
                match <Packet as Unmarshal>::unmarshal(&mut bytes) {
                    Ok(packet) => {
                        metrics
                            .rtp_packets_total
                            .with_label_values(&["transcoded_ingest"])
                            .inc();
                        fanout.publish(packet);
                    }
                    // A malformed datagram on this loopback leg would mean
                    // something other than ffmpeg wrote to the port --
                    // skip it and keep reading rather than tearing down
                    // the whole leg over one bad packet.
                    Err(_) => continue,
                }
            }
        }));

        Ok(Self { handle })
    }
}

impl Drop for RtpIngress {
    fn drop(&mut self) {
        self.handle.abort();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rtc::rtp::Header;
    use rtc::shared::marshal::Marshal;

    fn sample_packet(seq: u16) -> Packet {
        Packet {
            header: Header {
                sequence_number: seq,
                ssrc: 7,
                payload_type: FORWARD_PT,
                ..Default::default()
            },
            payload: bytes::Bytes::from_static(b"h264-nal"),
        }
    }

    const FORWARD_PT: u8 = 96;

    #[tokio::test]
    async fn ingress_republishes_udp_rtp_into_fanout() {
        let runtime = webrtc::runtime::default_runtime().expect("runtime-tokio enabled");
        let registry = prometheus::Registry::new();
        let metrics = RtcMetrics::register(&registry).unwrap();
        let fanout = TrackFanout::new();
        let mut subscriber = fanout.subscribe();

        // Bind port 0 first just to learn a free port, then release it --
        // `RtpIngress::spawn` needs to be the one holding it so its own
        // bind is what we are testing.
        let probe = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        let port = probe.local_addr().unwrap().port();
        drop(probe);

        let leg = RtpLeg {
            local_port: port,
            bind_ip: "127.0.0.1".parse().unwrap(),
            kind: RtpLegKind::Video,
        };
        let _ingress = RtpIngress::spawn(&*runtime, leg, Arc::clone(&fanout), metrics.clone())
            .expect("bind succeeds");

        // Sender: a plain std UDP socket standing in for ffmpeg's `-f rtp`
        // output.
        let sender = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        let packet = sample_packet(42);
        let bytes = <Packet as Marshal>::marshal(&packet).unwrap();
        sender
            .send_to(&bytes, ("127.0.0.1", port))
            .expect("send to ingress port");

        let received =
            tokio::time::timeout(std::time::Duration::from_secs(2), subscriber.recv(&metrics))
                .await
                .expect("no timeout")
                .expect("fanout delivers the packet");
        assert_eq!(received.header.sequence_number, 42);
        assert_eq!(received.header.payload_type, FORWARD_PT);
        assert_eq!(
            metrics
                .rtp_packets_total
                .with_label_values(&["transcoded_ingest"])
                .get(),
            1
        );
    }

    #[tokio::test]
    async fn dropping_ingress_stops_the_read_loop() {
        let runtime = webrtc::runtime::default_runtime().expect("runtime-tokio enabled");
        let registry = prometheus::Registry::new();
        let metrics = RtcMetrics::register(&registry).unwrap();
        let fanout = TrackFanout::new();

        let probe = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        let port = probe.local_addr().unwrap().port();
        drop(probe);

        let leg = RtpLeg {
            local_port: port,
            bind_ip: "127.0.0.1".parse().unwrap(),
            kind: RtpLegKind::Audio,
        };
        let ingress = RtpIngress::spawn(&*runtime, leg, fanout, metrics).expect("bind succeeds");
        drop(ingress);
        // No assertion beyond "this does not panic/hang" -- `abort()` on a
        // background task is fire-and-forget by design (see
        // `webrtc::runtime::JoinHandle::abort` docs).
    }
}
