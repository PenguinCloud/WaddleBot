//! Integration test for `svc_streaming::run_with_shutdown` -- exercises the
//! real bind/serve/telemetry-init wiring end-to-end (the part `run()`
//! can't otherwise be tested through, since `run()` itself reads process
//! argv via `clap::Parser::parse()` and installs real OS signal handlers).
//! Binds every listener (HTTP, metrics, RTMP, SRT) to an explicit free/
//! ephemeral port and passes already-resolved shutdown futures so the
//! server starts, logs, and stops immediately instead of blocking forever.
//! `--rtmp-port 0`/`--srt-port 0` matter as much as the HTTP/metrics free
//! ports do -- since S12 wiring, `run_with_shutdown` always binds real
//! RTMP/SRT listeners, and the crate's default ports (1935/9000) would
//! otherwise collide with a real svc-streaming instance or another
//! parallel test run on the same host.
//!
//! No env-var lock is needed here: this file contains exactly one test, so
//! there is no cross-test env-var race to serialize against within this
//! process (each `tests/*.rs` file is its own binary/process).

use clap::Parser;

use svc_streaming::config::{CliConfig, Config};

/// Binds a std `TcpListener` to an OS-assigned ephemeral port, reads it
/// back, and immediately releases the socket so `run_with_shutdown` can
/// bind it again moments later.
fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .expect("bind to ephemeral port")
        .local_addr()
        .expect("read local addr")
        .port()
}

#[tokio::test]
async fn run_with_shutdown_binds_serves_and_stops_cleanly() {
    // SAFETY: single test in this process, before any await point.
    unsafe {
        std::env::remove_var("OTEL_EXPORTER_OTLP_ENDPOINT");
        std::env::set_var("DB_PASSWORD", "test-db-pass");
        std::env::set_var("SERVICE_API_KEY", "test-service-key");
    }

    // `CliConfig::validate` rejects port 0 (it's usually a misconfiguration
    // sentinel, not "let the OS pick") -- so find two free ports the same
    // way the OS would assign them, then bind to those explicitly.
    let http_port = free_port();
    let metrics_port = free_port();

    let cli = CliConfig::try_parse_from([
        "svc-streaming",
        "--http-port",
        &http_port.to_string(),
        "--metrics-port",
        &metrics_port.to_string(),
        "--bind-addr",
        "127.0.0.1",
        // Ephemeral -- `CliConfig::validate` only rejects port 0 for
        // http/metrics, so RTMP/SRT can take an OS-assigned port directly
        // instead of needing the same free-port-then-rebind dance.
        "--rtmp-port",
        "0",
        "--srt-port",
        "0",
    ])
    .expect("valid CLI assembly");
    let config = Config::from_cli(cli).expect("required secrets are set");

    let result = svc_streaming::run_with_shutdown(config, async {}, async {}).await;
    assert!(
        result.is_ok(),
        "run_with_shutdown should exit cleanly: {result:?}"
    );

    unsafe {
        std::env::remove_var("DB_PASSWORD");
        std::env::remove_var("SERVICE_API_KEY");
    }
}
