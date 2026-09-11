//! Integration tests for `ingest::srt::SrtListener`'s happy path, over real
//! loopback UDP (no mocks): an authorized SRT caller with a resolvable
//! stream key gets its accepted connection emitted as an `IngestSession`,
//! and MPEG-TS payload bytes pass through the resulting `AsyncRead`
//! unchanged.

use std::sync::Arc;
use std::time::Duration;

use bytes::Bytes;
use futures::SinkExt;
use srt_tokio::SrtSocket;
use tokio::io::AsyncReadExt;
use tokio::sync::mpsc;

use svc_streaming::ingest::srt::{AllowlistAuth, SrtListener};
use svc_streaming::ingest::IngestKind;

const TS_PACKET_LEN: usize = 188;

/// Builds one synthetic 188-byte MPEG-TS packet: sync byte `0x47` followed
/// by `fill` in every remaining byte, so packets from different calls are
/// distinguishable in assertions.
fn ts_packet(fill: u8) -> Bytes {
    let mut buf = vec![fill; TS_PACKET_LEN];
    buf[0] = 0x47;
    Bytes::from(buf)
}

/// Binds a UDP socket to an OS-assigned ephemeral loopback port and returns
/// it alongside the assigned port, so each test's SRT caller can target the
/// listener without a fixed-port collision under parallel test execution.
async fn ephemeral_udp() -> (tokio::net::UdpSocket, u16) {
    let socket = tokio::net::UdpSocket::bind("127.0.0.1:0")
        .await
        .expect("bind ephemeral udp socket");
    let port = socket.local_addr().expect("local addr").port();
    (socket, port)
}

#[tokio::test]
async fn accepted_publisher_with_streamid_emits_session_with_resolved_key() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, mut rx) = mpsc::channel(4);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["known-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let mut caller = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), Some("#!::r=known-key"))
        .await
        .expect("srt caller connects and is accepted");

    caller
        .send((std::time::Instant::now(), ts_packet(1)))
        .await
        .expect("send ts packet");
    caller.close().await.expect("close caller");

    let session = tokio::time::timeout(Duration::from_secs(5), rx.recv())
        .await
        .expect("session received before timeout")
        .expect("channel not closed");

    assert_eq!(session.kind, IngestKind::Srt);
    assert_eq!(session.key, "known-key");
}

#[tokio::test]
async fn mpegts_payload_bytes_pass_through_the_ingest_session_stream_unchanged() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, mut rx) = mpsc::channel(4);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["known-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let packets: Vec<Bytes> = (0..5u8).map(ts_packet).collect();
    let expected: Vec<u8> = packets.iter().flat_map(|p| p.to_vec()).collect();

    let mut caller = SrtSocket::builder()
        // Bare key (no `#!::` prefix) must resolve identically to the ACL form.
        .call(format!("127.0.0.1:{port}"), Some("known-key"))
        .await
        .expect("srt caller connects and is accepted");

    for packet in packets {
        caller
            .send((std::time::Instant::now(), packet))
            .await
            .expect("send ts packet");
    }
    caller.close().await.expect("close caller");

    let mut session = tokio::time::timeout(Duration::from_secs(5), rx.recv())
        .await
        .expect("session received before timeout")
        .expect("channel not closed");

    let mut received = Vec::new();
    tokio::time::timeout(
        Duration::from_secs(5),
        session.stream.read_to_end(&mut received),
    )
    .await
    .expect("read completes before timeout")
    .expect("read succeeds");

    assert_eq!(received, expected);
}
