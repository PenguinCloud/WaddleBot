//! Integration tests for `ingest::srt::SrtListener` rejection paths, over
//! real loopback UDP (no mocks): non-MPEG-TS payload, unknown stream key,
//! and a duplicate publisher for an already-active key.

use std::sync::Arc;
use std::time::Duration;

use bytes::Bytes;
use futures::SinkExt;
use srt_tokio::SrtSocket;
use tokio::sync::mpsc;

use svc_streaming::ingest::srt::{AllowlistAuth, SrtListener};

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
async fn non_mpegts_payload_is_dropped_without_emitting_a_session() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, mut rx) = mpsc::channel(4);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["known-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let mut caller = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), Some("known-key"))
        .await
        .expect("srt caller connects and is accepted (key auth passes pre-accept)");

    // Not MPEG-TS: 188 zero bytes, no 0x47 sync byte.
    let not_ts = Bytes::from(vec![0u8; 188]);
    caller
        .send((std::time::Instant::now(), not_ts))
        .await
        .expect("send non-ts payload");
    caller.close().await.expect("close caller");

    let result = tokio::time::timeout(Duration::from_millis(1500), rx.recv()).await;
    assert!(
        result.is_err(),
        "no IngestSession should be emitted for a non-mpegts payload"
    );
}

#[tokio::test]
async fn missing_streamid_is_rejected_before_accept() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, _rx) = mpsc::channel(4);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["known-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let result = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), None)
        .await;

    assert!(
        result.is_err(),
        "a caller sending no streamid at all has no resolvable key and must be rejected"
    );
}

#[tokio::test]
async fn caller_disconnecting_before_sending_data_emits_no_session() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, mut rx) = mpsc::channel(4);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["known-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let mut caller = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), Some("known-key"))
        .await
        .expect("srt caller connects and is accepted (key auth passes pre-accept)");

    // Disconnect without ever sending a payload chunk.
    caller.close().await.expect("close caller");

    let result = tokio::time::timeout(Duration::from_millis(1500), rx.recv()).await;
    assert!(
        result.is_err(),
        "no IngestSession should be emitted for a caller that never sends data"
    );
}

#[tokio::test]
async fn dropped_pipeline_receiver_does_not_panic_the_connection_handler() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, rx) = mpsc::channel(4);
    // Drop the pipeline-supervisor side of the channel before any publisher
    // connects, so the eventual `tx.send(session)` inside `handle_connection`
    // fails -- exercising that cleanup path without hanging or panicking.
    drop(rx);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["known-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let mut caller = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), Some("known-key"))
        .await
        .expect("srt caller connects and is accepted");

    let mut packet = vec![0u8; 188];
    packet[0] = 0x47;
    caller
        .send((std::time::Instant::now(), Bytes::from(packet)))
        .await
        .expect("send ts packet");

    // If the connection handler panicked or hung on the closed channel, this
    // close (and the whole test) would fail/time out.
    tokio::time::timeout(Duration::from_secs(5), caller.close())
        .await
        .expect("close completes before timeout")
        .expect("close caller");
}

#[tokio::test]
async fn unknown_key_is_rejected_before_accept() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, _rx) = mpsc::channel(4);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["known-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let result = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), Some("unknown-key"))
        .await;

    assert!(
        result.is_err(),
        "unauthorized key must be rejected pre-accept"
    );
}

#[tokio::test]
async fn duplicate_key_is_rejected_while_first_publisher_is_active() {
    let (socket, port) = ephemeral_udp().await;
    let (tx, mut rx) = mpsc::channel(4);
    let listener = SrtListener::new(port).with_auth(Arc::new(AllowlistAuth::new(["shared-key"])));
    let _server = tokio::spawn(listener.run_with_socket(socket, tx));

    let mut first = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), Some("shared-key"))
        .await
        .expect("first publisher is accepted");

    // Keep the first publisher active (send one valid TS packet so its
    // session is emitted and the key stays held) before the second connect
    // attempt -- the accept handshake completing server-side already
    // guarantees the key was inserted into the active set (see
    // `handle_connection`: insert happens before `request.accept()`), so
    // this ordering is deterministic, not a timing-dependent race.
    let mut packet = vec![0u8; 188];
    packet[0] = 0x47;
    first
        .send((std::time::Instant::now(), Bytes::from(packet)))
        .await
        .expect("send ts packet from first publisher");

    let _first_session = tokio::time::timeout(Duration::from_secs(5), rx.recv())
        .await
        .expect("first session received before timeout")
        .expect("channel not closed");

    let second = SrtSocket::builder()
        .call(format!("127.0.0.1:{port}"), Some("shared-key"))
        .await;
    assert!(
        second.is_err(),
        "a second publisher for an already-active key must be rejected"
    );

    first.close().await.expect("close first caller");
}
