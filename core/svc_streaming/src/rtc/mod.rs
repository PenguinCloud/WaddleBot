//! Shared WebRTC (`webrtc-rs` 0.20.5) plumbing for WHIP ingest
//! (`src/ingest/whip.rs`) and WHEP egress (`src/egress/whep.rs`) -- chunk
//! S6 of issue #287, per
//! `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md` §2/§4/§5.
//!
//! # Module map
//!
//! | Module | Owns |
//! |---|---|
//! | [`config`] | [`config::RtcConfig`] -- derives WebRTC transport settings from [`crate::config::Config`] |
//! | [`pc_factory`] | [`pc_factory::PeerConnectionFactory`] -- builds ingest/egress `PeerConnection`s with this service's port-range/NAT policy |
//! | [`fanout`] | [`fanout::TrackFanout`] -- the SFU primitive: one publisher, N WHEP viewer subscribers, per-subscriber drop accounting |
//! | [`sdp_writer`] | [`sdp_writer::WhipTranscodeBridge`] -- WHIP-to-ffmpeg bridge: `input.sdp` + local UDP RTP forwarding, for the transcode path |
//! | [`rtp_leg`] | [`rtp_leg::RtpLeg`] / [`rtp_leg::RtpIngress`] -- ffmpeg-to-WHEP bridge: reads a transcoded `-f rtp` leg back into a [`fanout::TrackFanout`] |
//! | [`metrics`] | [`metrics::RtcMetrics`] -- the four Prometheus series this chunk owns |
//! | [`ingest_auth`] | [`ingest_auth::WhipTokenAuthorizer`] / [`ingest_auth::InternalIngestAuthClient`] -- WHIP token authorization |
//!
//! # `webrtc-rs` 0.20.5 maturity gaps (document per this chunk's task spec)
//!
//! **AV1-over-WebRTC: deferred, matches the pipeline matrix's own default
//! (§9.5).** `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md` §3
//! already calls this open pending confirmation of the crate's AV1 RTP
//! payloader maturity; this chunk uses `MediaEngine::register_default_codecs`
//! (Opus, VP8, H264 -- §3's "H264 preferred; VP8 accepted"), never
//! registers an AV1 payload type for a `PeerConnection`, and the WHEP
//! transcoded-egress path ([`rtp_leg`]) is codec-agnostic RTP forwarding
//! regardless -- so this gap only bites if/when AV1-over-WebRTC output is
//! actually requested, at which point it needs a fresh maturity check
//! against whatever `webrtc-rs`/`rtc-rtp` version is current then.
//!
//! **`SettingEngine::set_udp_network` (ICE ephemeral port range): not a
//! documentation gap, an actual `//TODO:` stub in this crate version.**
//! `rtc-0.20.5/src/peer_connection/configuration/setting_engine.rs` has the
//! whole method (and the `UDPNetwork` type it takes) commented out --
//! `//TODO: use ice::udp_network::UDPNetwork;` / the method body itself is
//! inside a `/* todo: ... */` block. It does not compile if uncommented
//! against this release, so there is no way to hand webrtc-rs a port range
//! and have it enforce `WEBRTC_UDP_RANGE` internally. [`pc_factory::PeerConnectionFactory`]
//! works around this at its own boundary instead: it picks a candidate
//! port itself and passes an explicit `bind_ip:port` (never a `:0`
//! wildcard) to `PeerConnectionBuilder::with_udp_addrs`, retrying the next
//! candidate on a bind failure. See that module's `PortAllocator` docs for
//! the full rationale and the accepted TOCTOU trade-off.
//!
//! **In-process (same-runtime) RTP delivery between two `PeerConnection`s
//! did not work in testing -- a real, reproducible gap, not a
//! documentation nicety.** A minimal two-peer reproduction mirroring
//! `webrtc-rs`'s own `examples/rtp-to-webrtc`/`examples/broadcast`
//! patterns exactly (add a send-only Opus track, negotiate offer/answer,
//! wait for `RTCPeerConnectionState::Connected` on *both* peers, then
//! `write_rtp`) showed **zero packets ever reach the far side's
//! `on_track`**, despite: a valid negotiated SDP (matching payload types,
//! exchanged host candidates, matching fingerprints), and both peers
//! independently reporting `Connected`. This reproduces with plain
//! `PeerConnectionBuilder` calls, outside every abstraction in this
//! module -- it is not a bug in [`pc_factory`], [`fanout`], or either
//! `whip.rs`/`whep.rs` router. `tests/rtc_whip_whep_roundtrip.rs` documents
//! the same finding at the integration-test level and, as a result, proves
//! the WHIP/WHEP HTTP signaling contract and session lifecycle rather than
//! actual RTP delivery through a live `PeerConnection` pair -- the RTP
//! *forwarding* mechanics ([`fanout::TrackFanout`] and
//! [`rtp_leg::RtpIngress`]) are proven independently by their own unit
//! tests, which move packets through the same code without going through a
//! real `PeerConnection`. **Follow-up before relying on this in
//! production:** verify real browser <-> server WHIP/WHEP (not two
//! in-process `webrtc-rs` peers) actually delivers media -- same-process
//! dual-peer testing is an unusual `webrtc-rs` usage pattern (its own
//! examples always run as two separate OS processes exchanging SDP via
//! copy-paste), so this may be a same-process-specific limitation rather
//! than one that affects a real deployment; that distinction is exactly
//! what a live cross-network smoke test would settle and this chunk did
//! not have the means to run.
//!
//! # Not done in this chunk (blocked on S3)
//!
//! [`rtp_leg::RtpLeg`] and the WHEP transcoded-egress wiring in
//! `src/egress/whep.rs` are a **contract**, not a working end-to-end path:
//! nothing in this service yet constructs a real `RtpLeg` or calls
//! `pipeline::ffmpeg::FfmpegRunner::spawn` with a matching `-f rtp` output
//! argument, because `src/pipeline/ffmpeg.rs` and `src/pipeline/supervisor.rs`
//! (chunk S3) are both still stubs as of this chunk (`README.md` Module
//! Ownership: "S3 -- model implemented, `ffmpeg`/`supervisor` are stubs").
//! The **copy** path (WHIP source -> WHEP output, no transcode) has no such
//! dependency and is fully wired: `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md`
//! §1/§7 case 6 -- "no ffmpeg process ... `webrtc-rs` forwards RTP directly
//! (SFU)".

pub mod config;
pub mod fanout;
pub mod ingest_auth;
pub mod metrics;
pub mod pc_factory;
pub mod rtp_leg;
pub mod sdp_writer;

pub use config::RtcConfig;
pub use fanout::{MediaFanouts, TrackFanout};
pub use metrics::RtcMetrics;
pub use pc_factory::{PeerConnectionFactory, RtcError};
