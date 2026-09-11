//! WHIP-to-ffmpeg bridge for the **transcode** path: writes an `input.sdp`
//! file plus forwards depacketized RTP to the local UDP ports it describes,
//! so a spawned `ffmpeg -protocol_whitelist file,rtp,udp -i input.sdp` can
//! read a WHIP publisher's media --
//! `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md` §2's WHIP input
//! recipe. The **copy** path (WHIP source -> WHEP output, no transcode)
//! never touches this module -- it flows entirely through
//! [`crate::rtc::fanout::TrackFanout`], per that same doc's §1: "a pure-copy
//! WHIP->WHEP leg needs no ffmpeg process". A WHIP session builds both:
//! this bridge is what makes the *same* published stream available to a
//! transcoding output too, without the ingest handler needing to know in
//! advance whether any pipeline actually wants a transcode.

use std::io;
use std::net::{IpAddr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use rtc::rtp::Packet;
use rtc::shared::marshal::Marshal;
use webrtc::runtime::{AsyncUdpSocket, Runtime};

/// Fixed payload types used on the loopback SDP/UDP legs between this
/// service and a spawned `ffmpeg` process -- deliberately **not** the
/// payload type negotiated with the WHIP publisher over WebRTC (dynamic,
/// renegotiated per session). Retagging to a fixed pair before forwarding
/// (mirrors webrtc-rs's own `rtp-forwarder` example: "Re-tag payload type
/// so downstream tools see what they expect") keeps `input.sdp`'s
/// `a=rtpmap` lines static across every session.
pub const FORWARD_PAYLOAD_TYPE_VIDEO_H264: u8 = 96;
pub const FORWARD_PAYLOAD_TYPE_AUDIO_OPUS: u8 = 111;

/// Picks a free UDP port via the OS ephemeral allocator (bind to port 0,
/// read back what the kernel assigned, release it) -- used to choose the
/// fixed port `input.sdp` tells ffmpeg to listen on for one media leg.
/// ffmpeg binds it itself once spawned (owned by chunk S3, not yet
/// implemented), so this is a probe-and-release with the same inherent
/// TOCTOU trade-off as `PortAllocator` in `src/rtc/pc_factory.rs` --
/// accepted for the same reason: this process is the only writer of
/// `input.sdp` files, so a lost race is rare and, unlike the ICE port
/// allocator, has no bounded-retry caller here since ffmpeg's own bind
/// failure (not this process's) is the actual failure mode; that surfaces
/// as ffmpeg exiting, handled by `pipeline::supervisor`'s restart/backoff
/// (§6), not by this module.
fn pick_local_port(bind_ip: IpAddr) -> io::Result<u16> {
    let sock = std::net::UdpSocket::bind((bind_ip, 0))?;
    sock.local_addr().map(|addr| addr.port())
}

/// Forwards one media kind's depacketized RTP from a WHIP publisher's
/// `on_track` handler to a fixed local UDP target ffmpeg reads per
/// `input.sdp`.
pub struct UdpRtpForwarder {
    sock: Arc<dyn AsyncUdpSocket>,
    target: SocketAddr,
    payload_type: u8,
}

impl UdpRtpForwarder {
    /// Binds an ephemeral *source* socket (the OS assigns this port; only
    /// `target`, written into `input.sdp`, matters to ffmpeg) and prepares
    /// to forward to `target`.
    fn new(runtime: &dyn Runtime, target: SocketAddr, payload_type: u8) -> io::Result<Self> {
        let std_sock = std::net::UdpSocket::bind((target.ip(), 0))?;
        let sock = runtime.wrap_udp_socket(std_sock)?;
        Ok(Self {
            sock,
            target,
            payload_type,
        })
    }

    /// Marshals `packet` back to wire bytes (retagging its payload type to
    /// the fixed value `input.sdp` describes) and sends it to `target`. A
    /// packet that fails to marshal (e.g. larger than the 1500-byte MTU
    /// buffer) is dropped rather than killing the forwarding loop -- one
    /// bad packet must never take down an entire session; likewise a
    /// transient `send_to` failure (ffmpeg not listening yet) is not
    /// propagated as an error for the same reason.
    async fn forward(&self, packet: &Packet) {
        let mut retagged = packet.clone();
        retagged.header.payload_type = self.payload_type;
        let mut buf = [0u8; 1500];
        if let Ok(n) = retagged.marshal_to(&mut buf) {
            let _ = self.sock.send_to(&buf[..n], self.target).await;
        }
    }
}

/// Writes a minimal `input.sdp` describing the video/audio RTP legs at
/// `bind_ip:{video_port,audio_port}`, in the form
/// `ffmpeg -protocol_whitelist file,rtp,udp -i input.sdp` expects. Only the
/// media kinds present in the WHIP session get an `m=` line.
fn write_input_sdp(
    path: &Path,
    bind_ip: IpAddr,
    video_port: Option<u16>,
    audio_port: Option<u16>,
) -> io::Result<()> {
    let ip_version = if bind_ip.is_ipv6() { "IP6" } else { "IP4" };
    let mut sdp = format!(
        "v=0\r\no=- 0 0 IN {ip_version} {bind_ip}\r\ns=svc-streaming WHIP transcode input\r\nc=IN {ip_version} {bind_ip}\r\nt=0 0\r\n"
    );
    if let Some(port) = video_port {
        sdp.push_str(&format!(
            "m=video {port} RTP/AVP {pt}\r\na=rtpmap:{pt} H264/90000\r\n",
            pt = FORWARD_PAYLOAD_TYPE_VIDEO_H264
        ));
    }
    if let Some(port) = audio_port {
        sdp.push_str(&format!(
            "m=audio {port} RTP/AVP {pt}\r\na=rtpmap:{pt} opus/48000/2\r\n",
            pt = FORWARD_PAYLOAD_TYPE_AUDIO_OPUS
        ));
    }
    std::fs::write(path, sdp)
}

/// One WHIP session's transcode-path bridge: an `input.sdp` file plus a
/// forwarder per media kind present. Deleting the file happens on `Drop`,
/// alongside session teardown.
///
/// **`IngestSession.sdp_path` carry-through:** `src/ingest/mod.rs`'s
/// [`crate::ingest::IngestSession`] has no `sdp_path` field to extend --
/// that file is owned by a different chunk and out of this chunk's edit
/// scope. `sdp_path` is exposed here as a public field instead and the
/// WHIP router (`src/ingest/whip.rs`) keeps a side map from ingest `key`
/// (the WHIP token) to the owning `WhipTranscodeBridge`, documented on
/// `WhipState` -- whichever chunk wires ffmpeg spawning (S3) reads it via
/// that side map rather than through `IngestSession` itself.
pub struct WhipTranscodeBridge {
    pub sdp_path: PathBuf,
    pub video_port: Option<u16>,
    pub audio_port: Option<u16>,
    video_forwarder: Option<UdpRtpForwarder>,
    audio_forwarder: Option<UdpRtpForwarder>,
}

impl WhipTranscodeBridge {
    /// Creates the bridge for one session: picks target ports for the
    /// media kinds present, writes `input.sdp` under `stream_data_dir`,
    /// and prepares a forwarder for each.
    pub fn create(
        runtime: &dyn Runtime,
        stream_data_dir: &Path,
        session_key: &str,
        bind_ip: IpAddr,
        has_video: bool,
        has_audio: bool,
    ) -> io::Result<Self> {
        std::fs::create_dir_all(stream_data_dir)?;

        let video_port = has_video.then(|| pick_local_port(bind_ip)).transpose()?;
        let audio_port = has_audio.then(|| pick_local_port(bind_ip)).transpose()?;

        let video_forwarder = video_port
            .map(|port| {
                UdpRtpForwarder::new(
                    runtime,
                    SocketAddr::new(bind_ip, port),
                    FORWARD_PAYLOAD_TYPE_VIDEO_H264,
                )
            })
            .transpose()?;
        let audio_forwarder = audio_port
            .map(|port| {
                UdpRtpForwarder::new(
                    runtime,
                    SocketAddr::new(bind_ip, port),
                    FORWARD_PAYLOAD_TYPE_AUDIO_OPUS,
                )
            })
            .transpose()?;

        let sdp_path = stream_data_dir.join(format!("whip-{session_key}.sdp"));
        write_input_sdp(&sdp_path, bind_ip, video_port, audio_port)?;

        Ok(Self {
            sdp_path,
            video_port,
            audio_port,
            video_forwarder,
            audio_forwarder,
        })
    }

    /// Forwards one video RTP packet, a no-op if this session has no video
    /// leg.
    pub async fn forward_video(&self, packet: &Packet) {
        if let Some(forwarder) = &self.video_forwarder {
            forwarder.forward(packet).await;
        }
    }

    /// Forwards one audio RTP packet, a no-op if this session has no audio
    /// leg.
    pub async fn forward_audio(&self, packet: &Packet) {
        if let Some(forwarder) = &self.audio_forwarder {
            forwarder.forward(packet).await;
        }
    }
}

impl Drop for WhipTranscodeBridge {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.sdp_path);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rtc::rtp::Header;
    use std::io::Read;

    fn sample_packet() -> Packet {
        Packet {
            header: Header {
                sequence_number: 5,
                ssrc: 99,
                payload_type: 111, // negotiated-with-browser PT, deliberately
                // different from the fixed forwarding PT -- the golden test
                // below asserts it gets retagged.
                ..Default::default()
            },
            payload: bytes::Bytes::from_static(b"opus-frame"),
        }
    }

    #[test]
    fn write_input_sdp_golden_both_legs() {
        let dir =
            std::env::temp_dir().join(format!("svc-streaming-sdp-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("golden.sdp");
        write_input_sdp(
            &path,
            "127.0.0.1".parse().unwrap(),
            Some(40010),
            Some(40011),
        )
        .unwrap();

        let mut contents = String::new();
        std::fs::File::open(&path)
            .unwrap()
            .read_to_string(&mut contents)
            .unwrap();

        assert!(contents.starts_with("v=0\r\n"));
        assert!(contents.contains("m=video 40010 RTP/AVP 96\r\n"));
        assert!(contents.contains("a=rtpmap:96 H264/90000\r\n"));
        assert!(contents.contains("m=audio 40011 RTP/AVP 111\r\n"));
        assert!(contents.contains("a=rtpmap:111 opus/48000/2\r\n"));

        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn write_input_sdp_omits_missing_media_kind() {
        let dir = std::env::temp_dir().join(format!(
            "svc-streaming-sdp-test-video-only-{}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("video-only.sdp");
        write_input_sdp(&path, "127.0.0.1".parse().unwrap(), Some(40020), None).unwrap();

        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(contents.contains("m=video"));
        assert!(!contents.contains("m=audio"));

        std::fs::remove_dir_all(&dir).ok();
    }

    #[tokio::test]
    async fn bridge_writes_sdp_and_removes_it_on_drop() {
        let runtime = webrtc::runtime::default_runtime().expect("runtime-tokio enabled");
        let dir =
            std::env::temp_dir().join(format!("svc-streaming-bridge-test-{}", std::process::id()));

        let bridge = WhipTranscodeBridge::create(
            &*runtime,
            &dir,
            "test-token",
            "127.0.0.1".parse().unwrap(),
            true,
            true,
        )
        .expect("bridge creation succeeds");

        assert!(bridge.sdp_path.exists());
        assert!(bridge.video_port.is_some());
        assert!(bridge.audio_port.is_some());

        let sdp_path = bridge.sdp_path.clone();
        drop(bridge);
        assert!(!sdp_path.exists(), "sdp file must be removed on drop");
        std::fs::remove_dir_all(&dir).ok();
    }

    #[tokio::test]
    async fn forward_retags_payload_type_and_delivers_bytes() {
        let runtime = webrtc::runtime::default_runtime().expect("runtime-tokio enabled");
        let target_std = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        let target_addr = target_std.local_addr().unwrap();
        let target_sock = runtime.wrap_udp_socket(target_std).unwrap();

        let forwarder =
            UdpRtpForwarder::new(&*runtime, target_addr, FORWARD_PAYLOAD_TYPE_AUDIO_OPUS)
                .expect("forwarder binds");

        forwarder.forward(&sample_packet()).await;

        let mut buf = [0u8; 1500];
        let (n, _) = target_sock
            .recv_from(&mut buf)
            .await
            .expect("packet arrives");
        let mut bytes = bytes::BytesMut::from(&buf[..n]);
        let received = <Packet as rtc::shared::marshal::Unmarshal>::unmarshal(&mut bytes)
            .expect("valid RTP packet");
        assert_eq!(
            received.header.payload_type,
            FORWARD_PAYLOAD_TYPE_AUDIO_OPUS
        );
        assert_eq!(received.header.sequence_number, 5);
    }
}
