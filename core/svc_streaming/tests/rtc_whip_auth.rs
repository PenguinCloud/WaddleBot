//! `src/ingest/whip.rs` request-validation and auth-rejection paths that
//! don't need a real negotiated `PeerConnection` to exercise: token
//! authorization (401), `Content-Type` validation (400), a structurally
//! invalid offer (400), and the trickle-ICE `PATCH` endpoint (405) --
//! `docs/plans/2026-09-11-svc-streaming-pipeline-matrix.md` §8 chose
//! non-trickle ICE (wait for full gathering before answering), so `PATCH`
//! is a documented "not supported", not a missing feature.

mod rtc_common;

use axum::http::{header, StatusCode};
use tokio::sync::mpsc;
use uuid::Uuid;

use rtc_common::*;
use svc_streaming::ingest::whip::{self, WhipState};
use svc_streaming::rtc::metrics::RtcMetrics;
use svc_streaming::rtc::pc_factory::PeerConnectionFactory;

fn test_state(
    authorizer: std::sync::Arc<dyn svc_streaming::rtc::ingest_auth::WhipTokenAuthorizer>,
    port_range: (u16, u16),
) -> std::sync::Arc<WhipState> {
    let factory =
        std::sync::Arc::new(PeerConnectionFactory::new(loopback_rtc_config(port_range)).unwrap());
    let registry = prometheus::Registry::new();
    let metrics = RtcMetrics::register(&registry).unwrap();
    let (tx, _rx) = mpsc::channel(4);
    let dir = std::env::temp_dir().join(format!("svc-streaming-whip-auth-{}", Uuid::new_v4()));
    std::sync::Arc::new(WhipState::new(
        factory,
        authorizer,
        tx,
        dir,
        loopback_ip(),
        metrics,
    ))
}

#[tokio::test]
async fn unauthorized_token_is_rejected_with_401() {
    let state = test_state(std::sync::Arc::new(DenyAllAuthorizer), (41700, 41705));
    let router = whip::router(state);

    let response = oneshot(
        router,
        post_sdp(
            "/whip/not-allowed",
            "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n",
        ),
    )
    .await;

    assert_status(&response, StatusCode::UNAUTHORIZED);
}

#[tokio::test]
async fn wrong_content_type_is_rejected_with_400() {
    let state = test_state(std::sync::Arc::new(AllowAllAuthorizer), (41710, 41715));
    let router = whip::router(state);

    let request = axum::http::Request::builder()
        .method("POST")
        .uri("/whip/some-token")
        .header(header::CONTENT_TYPE, "application/json")
        .body(axum::body::Body::from("{}"))
        .unwrap();

    let response = oneshot(router, request).await;
    assert_status(&response, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn offer_with_no_media_sections_is_rejected_with_400() {
    let state = test_state(std::sync::Arc::new(AllowAllAuthorizer), (41720, 41725));
    let router = whip::router(state);

    let response = oneshot(
        router,
        post_sdp(
            "/whip/some-token",
            "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\n",
        ),
    )
    .await;

    assert_status(&response, StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn trickle_ice_patch_returns_405_with_allow_header() {
    let state = test_state(std::sync::Arc::new(AllowAllAuthorizer), (41730, 41735));
    let router = whip::router(state);

    let response = oneshot(
        router,
        patch_request(&format!("/whip/some-token/{}", Uuid::new_v4())),
    )
    .await;

    assert_status(&response, StatusCode::METHOD_NOT_ALLOWED);
    assert_eq!(
        response
            .headers()
            .get(header::ALLOW)
            .unwrap()
            .to_str()
            .unwrap(),
        "DELETE"
    );
}

#[tokio::test]
async fn teardown_of_unknown_session_is_404() {
    let state = test_state(std::sync::Arc::new(AllowAllAuthorizer), (41740, 41745));
    let router = whip::router(state);

    let response = oneshot(
        router,
        delete_request(&format!("/whip/some-token/{}", Uuid::new_v4())),
    )
    .await;

    assert_status(&response, StatusCode::NOT_FOUND);
}
