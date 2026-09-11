# Gazer (mobile/gazer)

Live-streaming client for Android phones and tablets. Streams the device's
back or front camera to any RTMP/RTMPS endpoint (H.264 + AAC, adaptive
bitrate, automatic reconnect). Standalone — no WaddleBot login; you supply
the RTMP URL/key/auth. M1 scope: phone camera only (no USB capture card yet
— see M2/M3 in `docs/superpowers/specs/2026-09-07-gazer-mobile-v2-design.md`).

## What works offline vs. online

| Capability | Offline | Online |
|---|---|---|
| Edit target/quality/audio settings | Yes | Yes |
| View cached license/flag status | Yes (last-fetched shown) | Yes |
| First-ever flag fetch (fresh install) | No — Go Live stays disabled until one succeeds | Yes |
| Go Live / stream to an RTMP endpoint | No (network required) | Yes |
| Update-available check | No (silently skipped) | Yes |
| View last stream stats from this session | Yes | Yes |

A fresh install needs exactly one successful license/flag fetch before Go
Live is enabled — after that, a 7-day offline grace period keeps cached
flags usable without a network round trip.

## Permissions

| Permission | Why |
|---|---|
| `CAMERA` | Capture the phone camera for streaming |
| `RECORD_AUDIO` | Capture the phone microphone for streaming |
| `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_CAMERA`, `FOREGROUND_SERVICE_MICROPHONE` | Keep the stream alive with the screen off, per Android's foreground-service rules |
| `INTERNET` | Publish to the RTMP endpoint |
| `POST_NOTIFICATIONS` (Android 13+) | Show the persistent "streaming — Stop" notification |
| `android.hardware.usb.host` feature (`required="false"`) | Reserved for M2/M3 USB capture-card support; unused in M1 |

## Telemetry

OpenTelemetry logs, metrics, and traces are emitted to an env-configurable
OTLP endpoint — never a hardcoded vendor URL or SDK. Resolution order,
independently per field: a non-empty Settings screen "Telemetry endpoint"
value wins; otherwise the build-time `--dart-define=OTEL_EXPORTER_OTLP_ENDPOINT`
(and `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_SERVICE_NAME`) is used; otherwise
the field is empty and export is disabled — every signal still records to
an in-memory ring buffer, it just never leaves the device. A dead/unreachable
collector never breaks the app: buffered records are retained/dropped per
the ring buffer's own policy, never surfaced as a crash. Debug logs
(verbose diagnostic detail) are off by default and toggled on the Settings
screen's developer section — never on by default in a release build.

## Build / test / run

All commands run inside the pinned toolchain container — never on the bare
host.

```
make mobile-toolchain          # build the toolchain image (once, or after Dockerfile changes)
make mobile-lint                # flutter analyze + dart format --set-exit-if-changed + ktlint
make mobile-test                 # flutter test --coverage, gated >=90%
make mobile-test-android          # gradle testDebugUnitTest + JaCoCo, gated >=90%
make mobile-test-integration        # emulator (needs /dev/kvm): integration_test/ + connectedDebugAndroidTest
make mobile-build                    # apk --split-per-abi + appbundle
make mobile-security                  # osv-scanner + semgrep + gitleaks
make mobile-telemetry-check            # OTel local-sink smoke test (logs/metrics/histograms/spans >=1)
make mobile-screenshots                # docs/screenshots/gazer/ marketing set (needs /dev/kvm)
make seed-mock-data-mobile               # interactive: launch with mock data seeded (needs a running device)
```

## Device matrix (M1 — phone camera only)

| Device | Camera path | Orientation | Status |
|---|---|---|---|
| Pixel 8 | Back/front Camera2 | Portrait + landscape | Supported |
| Pixel 9 | Back/front Camera2 | Portrait + landscape | Supported |
| Galaxy S24 | Back/front Camera2 | Portrait + landscape | Supported |
| Galaxy Tab S9 | Back/front Camera2 | Portrait + landscape | Supported (two-pane layout, >=600dp) |

USB capture-card rows (Camera2-external, libuvc) are out of scope until
M2/M3.

## Troubleshooting

| Error code | Meaning | What to check |
|---|---|---|
| `rtmpConnectFailed` | Couldn't reach the RTMP host (timeout, refused, DNS) | URL/host/port, network reachability, firewall |
| `rtmpAuthFailed` | Server rejected the username/password | Credentials in Settings; confirm the endpoint requires the auth you configured |
| `cameraInUse` | Another app holds the camera | Close the other app, retry Go Live |

## iOS

Deferred to a later, separate project phase (approved exception to
`client-flutter.md` — see the design spec's Rule Exceptions section).
Android-only for now.
