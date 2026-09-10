# Gazer Mobile 2.0 — Design Specification

Approved 2026-09-07. Branch `feature/gazer-mobile-v2` off `release/v3.0.X`. Product WaddleBot (repo waddlebot). App name Gazer; Android application id `io.waddlebot.gazer` (from 1.0, store listing updates in place).

## Summary

Live-streaming client for phones and tablets (Pixel, Galaxy S/Tab) on Android. Streams phone camera (back or front) or USB UVC HDMI capture card (e.g. UGREEN, AVerMedia) to any RTMP/RTMPS endpoint with H.264 + AAC, adaptive bitrate, automatic reconnect. Standalone: no WaddleBot login, user supplies RTMP URL/key/auth. Status panel only; no preview in v1. iOS/iPadOS deferred to a later phase. Excludes: preview, chat/overlay/community from 1.0, multi-target, H.265/AV1, SRT/WHIP, recording.

## Background

Gazer 1.0 (`mobile/flutter_gazer`) is scaffolding: faked "streaming"/"connected" with no encoder, RTMP library, or USB frame capture. Two disconnected preview UIs; plaintext SharedPreferences for secrets. Nothing fed the texture, so preview never worked. This design starts fresh at `mobile/gazer/` (directory), keeps only reusable ideas: USB permission flow + vendor-ID filter, license-server client shape, settings UI, secure storage pattern.

## Decisions Log

| # | Decision | Rationale | Decided By |
|---|----------|-----------|-----------|
| 1 | Fresh app at `mobile/gazer/`, port 1.0's license client shape + security patterns | Clean slate without 1.0's scaffolding burden; reuse proven security/auth approach | User 2026-09-07 |
| 2 | Status panel only, no live preview in v1 | Reduces complexity, preview later behind flag (OFF) | User 2026-09-07 |
| 3 | Standalone, no WaddleBot login | User enters any RTMP/RTMPS URL + optional key/auth | User 2026-09-07 |
| 4 | Android-first; iOS later as separate project | APPROVED EXCEPTION to client-flutter.md (iOS + Android together) | User 2026-09-07 |
| 5 | "As much Flutter as possible; Kotlin only to fill gaps" | Business logic in Dart; Kotlin = bridge/capture/encode/publish | User 2026-09-07 |
| 6 | FPS options 15/30/50/60, default 30 | Common broadcast framerates | User 2026-09-07 |
| 7 | RootEncoder 2.8.1, not custom encoder | Hardware H.264 via MediaCodec; adaptive bitrate; mature RTMP client | Design brief verified 2026-09-07 |
| 8 | Forbid RootEncoder `extra-sources` module (UVC source) | extra-sources depends on com.herohan:UVCAndroid (shiyinghan/UVCAndroid, PRC author, not 16KB-page aligned, RootEncoder #1877) → supply-chain violation | Design brief verified 2026-09-07 |
| 9 | libuvc 2026-09 + libusb 1.0.30 (no device discovery) + libjpeg-turbo + libyuv | Clean provenance (US/BSD authors); no discoverable devices = unrooted Android | Design brief verified 2026-09-07 |
| 10 | Camera2 LENS_FACING_EXTERNAL (Pixel 6+, Pixel Tablet, OEMs with external HAL) AND libuvc (Galaxy) | Pixel/Samsung split; SourceSelector tries Camera2 external 3 s, falls back to libuvc | Design brief + user 2026-09-07 |
| 11 | minSdk 29 (Android 10+), targetSdk 36, compileSdk 36 | User requirement; satisfy house rule floor (21); 16KB page alignment mandated 15+ | User 2026-09-07 |
| 12 | No libusb device discovery, wrap UsbDeviceConnection fd only | Unrooted Android; libusb_set_option(NO_DEVICE_DISCOVERY) then uvc_wrap(fd) | Design brief verified 2026-09-07 |
| 13 | Reconnect: RootEncoder setReTries(0); Dart ReconnectPolicy re-issues start(target) | RootEncoder has no reconnect() API; Dart owns retry logic | Design brief verified 2026-09-07 |
| 14 | libuvc built with DISABLE_JPEG=ON; MJPEG decoded with libjpeg-turbo TurboJPEG; YUY2 with libyuv | Raw frame output from libuvc; decode in bridge for efficiency | Design brief verified 2026-09-07 |
| 15 | Camera2 external: enumerate via CameraManager, filter LENS_FACING_EXTERNAL, open with Camera2Source.openCameraId(id) | CameraHelper.Facing only has BACK/FRONT (no EXTERNAL); contingency: custom Camera2ExternalSource if rotation/mirroring breaks | Design brief verified 2026-09-07 |
| 16 | App-local LicenseClient pending penguin-libs PR | Temporary bridge; promote LicenseClient into flutter_libs when ready; app-local is the unblock | Design brief + user 2026-09-07 |

## Requirements

### Functional

**Sources & targets**
- Video: device back/front camera (all devices), UVC capture card (Pixel 6+/Pixel Tablet native, Galaxy via libuvc)
- Audio: phone microphone, USB audio (if card exposes UAC), silence
- Output: RTMP or RTMPS; URL, stream key, optional username/password; no multi-target in v1
- Resolution: short edge {180, 360, 540, 720, 1080} @ 16:9 (320x180 ... 1920x1080); camera respects device orientation at Go Live, locks for session; UVC always landscape
- FPS: {15, 30, 50, 60} default 30
- Video bitrate: 500–5000 kbps step 100, default 2000; adaptive bitrate ON by default (ceiling is selected bitrate)
- Audio: AAC 128 kbps 48 kHz stereo (mono if mic only); H.264 AVC profile per resolution

**Settings screen**
- Target: URL (rtmp/rtmps scheme validation, host non-empty, path present), stream key (optional, auto-append as /<key> if URL lacks it, no double-append), username & password (both-or-neither, optional)
- Quality: resolution (dropdown {180…1080}), FPS (picker {15,30,50,60}), bitrate (slider 500–5000, step 100), adaptive toggle
- Audio: dropdown (auto = camera→mic / UVC→USB audio if available else mic, mic, USB audio, silence)
- Developer: toggle "force libuvc" (override 3 s Camera2 external wait)
- Validation: all range constraints enforced; secrets never logged (mask username/password in UI, last 4 chars visible); test-connection button NOT in v1
- Storage: URL, stream key, username, password → flutter_secure_storage (keys gazer.target.*); non-secret settings → shared_preferences; never plaintext

**Status panel**
- Camera on/off, UVC connected/streaming/off (+ device name, negotiated format e.g. MJPEG 1920x1080@30)
- Stream live/connecting/reconnecting/off
- Connection details: protocol, host, app, key (masked), auth on/off
- Live stats: bitrate kbps, FPS, dropped frames, uptime, reconnect count, congestion %
- Connectivity indicator (online/offline via connectivity_plus)
- License + flags status (last-fetched time)
- Update-available notice
- Foreground-service state
- Responsive: 600dp breakpoint; phone = single column + bottom sheet; tablet = two-pane (controls left, status right)

**Licensing & feature flags**
- App-local LicenseClient (dio) against https://license.penguintech.io/api/v2/{validate, features, keepalive}
- Device ID = SHA-256(ANDROID_ID + package name)
- Validate at startup (non-blocking, show result in panel); cache result; 7-day offline grace
- Flag keys: `waddlebot.gazer.camera-stream`, `waddlebot.gazer.uvc-capture`, `waddlebot.gazer.adaptive-bitrate`, `waddlebot.gazer.rtmp-auth` (all Free tier, no tier gating in v1)
- Never-seen flags default OFF; cached flags used offline
- **First-launch consequence**: fresh install needs one successful flag fetch before streaming allowed; UI explains why
- Keepalive every 5 min while foregrounded
- Transition plan: promote LicenseClient into flutter_libs via penguin-libs PR; app-local only as temporary bridge

**Update check**
- Startup + non-blocking: GET GitHub Releases for penguintechinc/waddlebot, filter gazer-v* tags, compare to package_info_plus version
- Notify in status panel only; Play Store auto-update remains primary

**Offline behavior**
- Everything except first flag fetch works offline
- Streaming requires network (obvious)
- Connectivity indicator in panel
- Last-fetched timestamps shown
- Analytics: none in v1

### Non-Functional

- Android 10+ (minSdk 29), targetSdk 36, compileSdk 36
- Phones (Pixel 8/9, Galaxy S24) + tablets (Galaxy Tab S9) in device matrix
- 16KB page alignment mandatory (Android 15+/Play): build native `.so` with `-Wl,-z,max-page-size=16384`
- Secure storage: platform-native only (SharedPreferences for non-secret; flutter_secure_storage for secrets)
- Coverage ≥90% mandatory: Dart enforced in CI via lcov threshold; Kotlin via JaCoCo on testDebugUnitTest; native C++ helpers unit-tested on host with googletest + llvm-cov ≥90%; JNI glue covered by instrumented + manual matrix (no coverage number claimed)
- Supply-chain: no PRC-origin, no dead/archived libraries (ffmpeg-kit, apivideo_live_stream out); all third-party pinned by commit/tag + SHA256
- Foreground service (types: camera, microphone, connectedDevice): user-initiated start only, persistent notification with Stop action, partial wake lock, screen-off preserves stream
- Permissions: CAMERA, RECORD_AUDIO, FOREGROUND_SERVICE (+ _CAMERA, _MICROPHONE, _CONNECTED_DEVICE), INTERNET, FEATURE_USB_HOST (not required=false), POST_NOTIFICATIONS (13+)

## Architecture

### Layout Tree

```
mobile/gazer/
├── lib/
│   ├── main.dart, app.dart (go_router, Material 3, dark default)
│   ├── config/        flavor config, constants (license URL, flag keys, update-check URL)
│   ├── models/        StreamSettings, StreamTarget, VideoSourceSpec, AudioSourceSpec,
│   │                  PipelineState (sealed), StreamStats, GazerError (freezed)
│   ├── pigeon/        generated from pigeons/pipeline.dart
│   ├── services/      PipelineController (Pigeon facade + event stream), SettingsRepository
│   │                  (secure + non-secret), LicenseClient (validate/features/keepalive),
│   │                  FeatureFlags, ReconnectPolicy, UpdateChecker, SourceSelector
│   ├── providers/     Riverpod (code-gen): settings, devices, pipeline state, stats,
│   │                  license/flags, connectivity
│   ├── screens/       HomeScreen (source picker, Go Live/Stop, status chip),
│   │                  SettingsScreen, StatusPanel (bottom sheet <600dp, side pane ≥600dp)
│   ├── widgets/
│   └── l10n/          intl .arb (en)
├── pigeons/pipeline.dart   Pigeon channel contract (single source of truth)
├── android/app/src/main/kotlin/io/waddlebot/gazer/
│   ├── PigeonHostApi.kt (implements host API, forwards to GazerPipeline, emits events)
│   ├── pipeline/      GazerPipeline.kt (RootEncoder GenericStream glue), StreamService.kt
│   │                  (foreground service), sources/ (PhoneCameraSource, Camera2ExternalSource,
│   │                  LibuvcVideoSource, UsbAudioSource), StatsSampler.kt
│   └── uvc/           UvcDeviceManager.kt (UsbManager enumerate/permission/attach-detach),
│                      UvcNative.kt (JNI bindings)
├── android/app/src/main/cpp/  CMakeLists.txt, libuvc_bridge.cpp
│                               (libusb+libuvc+libjpeg-turbo+libyuv; -z max-page-size=16384)
├── android/app/src/main/res/xml/usb_device_filter.xml (UVC class filter + vendor IDs)
├── android/app/src/test/       JUnit
├── android/app/src/androidTest/  instrumented
├── test/                        unit + widget + goldens
├── integration_test/
├── Dockerfile          toolchain (digest-pinned Ubuntu, Flutter 3.47.2 SHA, Android SDK)
├── Makefile (repo root targets): mobile-lint, mobile-test, mobile-build, mobile-security
├── pubspec.yaml        exact pins (no ^/~), pubspec.lock committed, .flutter-version = 3.47.2
├── .github/workflows/gazer-mobile.yml (repo root)  path-filtered, analyze → test → android-unit → build → security
└── README.md           offline vs online, device matrix, permissions
```

### Boundary Rule (Normative)

Kotlin bridges only: capture, encode, publish, USB permission, foreground service, per-second raw stats. Emits facts (state transitions, samples, error codes); takes commands. Every decision is Dart: settings validation, source selection, reconnect policy, flag gating, stats aggregation, user messaging. Rationale: encoded frames never leave GPU/MediaCodec path; Dart-side muxing would copy frames across the channel for nothing. No business logic in Kotlin; every Kotlin change has a JUnit test.

### Pigeon Contract (Sketch)

**Host API (Dart→Kotlin)**
- `listVideoDevices() -> List<VideoDevice{id, kind: backCamera|frontCamera|uvcCamera2|uvcLibuvc, name, vendorId?, productId?, formats?}>`
- `listAudioDevices() -> List<AudioDevice{id, kind: mic|usbAudio, name}>`
- `requestUsbPermission(deviceId) -> bool`
- `prepare(StreamConfig{videoDevice, audioDevice, width, height, fps, videoBitrateKbps, adaptive, audioBitrateKbps, orientation}) -> PrepareResult`
- `start(target: StreamTarget{url, streamKey?, username?, password?})`
- `stop()`
- `setVideoBitrate(kbps)`
- `getState() -> PipelineState`

**Flutter API (Kotlin→Dart Events)**
- `onStateChanged(PipelineState, errorCode?, detail?)`
- `onStats(StatsSample{bitrateKbps, fps, droppedFrames, sentBytes, congestion})`
- `onUsbAttached(VideoDevice)`
- `onUsbDetached(deviceId)`
- `onAuthResult(ok)`

**Pipeline States (Native, Minimal)**
- idle, preparing, ready, connecting, streaming, stopping, error
- Dart's sealed PipelineState adds `reconnecting(attempt, nextIn)` (Dart-owned state)

### Native Pipeline Flow

```
Video Source (Camera2 / Camera2 External / libuvc)
    ↓
[SurfaceTexture input]
    ↓
RootEncoder GenericStream
    ├─ prepareVideo(width, height, bitrate, fps, iFrameInterval=2, rotation, profile, level)
    ├─ MediaCodec H.264 (hardware, AVC per resolution)
    ├─ keyframe interval 2 s
    └─→ RTMP / RTMPS + ConnectChecker callbacks + BitrateAdapter
         ├─ onConnectionStarted, onConnectionSuccess, onConnectionFailed, onDisconnect,
         │  onAuthError, onAuthSuccess
         └─→ TCP → user's RTMP endpoint

Audio Source (Phone Mic / USB Audio / Silence)
    ↓
prepareAudio(sampleRate=48000, isStereo, bitrate=128, echoCanceler, noiseSuppressor)
    ↓
AAC encoding
    └─→ multiplexed into RTMP stream
```

### Video Sources

| Source | Mechanism | Devices | Decision |
|--------|-----------|---------|----------|
| Back/front camera | RootEncoder Camera2 source, facing selectable | all | standard |
| UVC via Camera2 external | enumerate via CameraManager, filter LENS_FACING_EXTERNAL, open with Camera2Source.openCameraId(id), rotation 0; contingency: custom Camera2ExternalSource if rotation/mirroring breaks | Pixel 6+, Pixel Tablet, OEMs with external camera HAL | verified 2026-09-07 |
| UVC via libuvc | UsbDeviceConnection fd → libusb (no discovery, wrap fd) → libuvc: negotiate MJPEG preferred (else YUY2) at requested size/fps (fallback to nearest, report negotiated) → decode (libjpeg-turbo MJPEG→RGBA; libyuv YUY2→ARGB) → ANativeWindow lock/post to SurfaceTexture (custom VideoSource) | Galaxy phones/tablets, everything else | fallback when Camera2 external absent |
| SourceSelector logic | After USB attach, wait up to 3 s for LENS_FACING_EXTERNAL camera to appear; if present use Camera2 external, else libuvc. Developer setting "force libuvc" overrides wait | runtime choice | Dart SourceSelector |

### Audio Sources

| Source | Mechanism | Default | Override |
|--------|-----------|---------|----------|
| Phone mic | RootEncoder microphone source | camera → mic | user setting |
| USB audio | AudioRecord.setPreferredDevice(TYPE_USB_DEVICE/TYPE_USB_HEADSET), 48 kHz PCM16, custom AudioSource via GetMicrophoneData.inputPCMData(Frame) | UVC → USB audio if card exposes UAC, else mic | user setting |
| Silence | muted | only if user selects | user setting |

### Output Geometry

- Resolution: short edge {180, 360, 540, 720, 1080}, 16:9 aspect (320x180 … 1920x1080)
- Camera output follows device orientation at Go Live — landscape 16:9 or portrait 9:16 with the same short edge — and locks for the session; UVC always landscape 16:9
- FPS: {15, 30, 50, 60} default 30
- Video bitrate: 500–5000 kbps step 100, default 2000; adaptive ON by default (ceiling is selected, BitrateAdapter lowers on congestion and recovers)
- Keyframe interval: 2 s
- H.264 profile: per resolution (baseline/main/high + appropriate level)

### Foreground Service

- Type: FOREGROUND_SERVICE + _CAMERA + _MICROPHONE + _CONNECTED_DEVICE (Android 14+)
- Started only from user tap (Go Live)
- Persistent notification with Stop action
- Partial wake lock while live
- Screen off: stream continues
- App killed: stream stops cleanly
- USB detach while streaming: stop with error `usbDetached`

### Permissions

```
CAMERA, RECORD_AUDIO, FOREGROUND_SERVICE (+_CAMERA, +_MICROPHONE, +_CONNECTED_DEVICE),
INTERNET, POST_NOTIFICATIONS (13+), feature USB host:
  <uses-feature android:name="android.hardware.usb.host" android:required="false"/>
```

## Native Details

### RootEncoder API Surface (Verbatim)

Used from 2.8.1:
- `StreamBase.prepareVideo(width, height, bitrate, fps, iFrameInterval=2, rotation, profile, level) -> boolean`
- `prepareAudio(sampleRate, isStereo, bitrate, echoCanceler, noiseSuppressor) -> boolean`
- `startStream(url)`, `stopStream()`
- `changeVideoSource(VideoSource)`, `changeAudioSource(AudioSource)`
- `setVideoBitrateOnFly(bitrate)` (called by BitrateAdapter)
- `getStreamClient() -> StreamClient` (for `setAuthorization`, `setReTries`, `getSentVideoFrames`, `getDroppedVideoFrames` + audio equivalents)
- `GenericStream(context, connectChecker: ConnectChecker, videoSource: VideoSource, audioSource: AudioSource)`
- `ConnectChecker { onConnectionStarted(url), onConnectionSuccess(), onConnectionFailed(reason), onDisconnect(), onAuthError(), onAuthSuccess() }` (ConnectChecker extends BitrateChecker)
- `BitrateChecker.onNewBitrate(bitrate: Long)` (called when bitrate changes)
- `BitrateAdapter(listener: BitrateAdapter.Listener) { adaptBitrate(actualBitrate: Long, hasCongestion: Boolean) }` where `Listener.onBitrateAdapted(bitrate: Int)`
- RTMPS: `addCertificates(TrustManager?)` (null = system trust). Verified 2026-09-07: `GenericStreamClient` does not expose `setTlsHostVerification`; hostname verification is the platform default, and `RootEncoderEngine.setTlsHostVerification` is a documented no-op kept on the `StreamEngine` interface.
- `setAuthorization(user: String?, password: String?)`
- `setReTries(n)` — DECISION: always 0; Dart owns retry logic via ReconnectPolicy
- `hasCongestion(percentUsed: Float) -> boolean`
- Maven: JitPack `com.github.pedroSG94.RootEncoder:library:2.8.1` ONLY (never `:extra-sources`)

### Custom VideoSource Interface

```kotlin
abstract class VideoSource {
    fun create(width: Int, height: Int, fps: Int, rotation: Int): Boolean
    fun start(surfaceTexture: SurfaceTexture)
    fun stop()
    fun release()
    fun isRunning(): Boolean
}
```
Libuvc source draws into `Surface(surfaceTexture)` via ANativeWindow lock/post after decode.

### Custom AudioSource Interface

```kotlin
abstract class AudioSource {
    fun create(sampleRate: Int, isStereo: Boolean, echoCanceler: Boolean, noiseSuppressor: Boolean): Boolean
    fun start(getMicrophoneData: GetMicrophoneData)
    fun stop()
    fun isRunning(): Boolean
    fun release()
}
```
USB audio source feeds PCM16 frames via `GetMicrophoneData.inputPCMData(Frame)`.

### libuvc Bridge (Native C++)

**Initialization**
- libusb: `libusb_set_option(NULL, LIBUSB_OPTION_NO_DEVICE_DISCOVERY)` then `uvc_wrap(fd)` where `fd = UsbDeviceConnection.getFileDescriptor()`
- libuvc: `uvc_init(&ctx, usb_ctx)` → `uvc_wrap(fd, ctx, &devh)`

**Format Negotiation** — algorithm:
- (a) Try MJPEG: `uvc_get_stream_ctrl_format_size(devh, &ctrl, UVC_FRAME_FORMAT_MJPEG, width, height, fps)` at requested W×H@fps
- (b) If MJPEG fails, try YUY2: `uvc_get_stream_ctrl_format_size(devh, &ctrl, UVC_FRAME_FORMAT_YUYV, width, height, fps)` at requested W×H@fps
- (c) If both fail, walk `uvc_get_format_descs(devh)` and pick nearest supported mode: same 16:9 aspect preferred, size ≤ requested, highest fps ≤ requested, MJPEG preferred over YUY2
- (d) Nothing usable → error `uvcNoUsableFormat`; else report negotiated mode (format + W×H@fps) to Dart for user awareness

**Streaming & Decode**
- libuvc built with `DISABLE_JPEG=ON` (raw frames only from libuvc)
- MJPEG: decode via libjpeg-turbo 3 API: `tj3DecompressHeader(handle, jpegBuf, jpegSize)` then `tj3Decompress8(handle, jpegBuf, jpegSize, dstBuf, pitch, TJPF_RGBA)` → RGBA
- YUY2: decode via libyuv `YUY2ToARGB(src, stride, dst, dst_stride, width, height)` → ARGB
- Output: lock ANativeWindow, write decoded frame, post to SurfaceTexture
- `uvc_start_streaming(devh, &ctrl, callback, user, 0)` with a per-frame callback
- `uvc_stop_streaming(devh)` on cleanup

**Signatures Used**
```c
uvc_init(&ctx, usb_ctx)
uvc_wrap(fd, ctx, &devh)
uvc_get_format_descs(devh)
uvc_get_stream_ctrl_format_size(devh, &ctrl, UVC_FRAME_FORMAT_MJPEG|UVC_FRAME_FORMAT_YUYV, w, h, fps)
uvc_start_streaming(devh, &ctrl, cb, user, 0)
uvc_stop_streaming(devh)
```

### Camera2 External Fallback

If Camera2Source's rotation/mirroring assumption breaks for external cameras on Pixel: replace `Camera2Source.openCameraId(id)` path with a custom `Camera2ExternalSource : VideoSource` that opens the external camera ID directly and targets the SurfaceTexture without RootEncoder's abstraction layer. Verified 2026-09-07 against source: `openCameraId(id)` re-opens only while the source is already running, so the M2 implementation starts the source on the default camera and then calls `openCameraId(externalId)`; initial back/front selection in M1 uses `switchCamera()`.

## Error Handling & Reconnect

### GazerError Enum (Dart/Pigeon)

| Code | Source | User Action | Retry Policy |
|------|--------|-------------|--------------|
| usbPermissionDenied | UVC permission prompt rejected | Retry → tap source again | manual only |
| uvcNoUsableFormat | libuvc can't negotiate MJPEG/YUY2 | Switch to camera or try different card | manual |
| uvcOpenFailed | UsbDeviceConnection.getFileDescriptor() fails or libuvc init fails | Reconnect card or restart app | manual |
| cameraUnavailable | Camera2 LENS_FACING_* not available | Switch to other source | manual |
| cameraInUse | Another app holding camera | Close competing app | manual |
| encoderFailed | RootEncoder prepare/start internal error | Retry or reduce quality | manual |
| audioSourceFailed | prepare audio fails | Try different audio source | manual |
| rtmpAuthFailed | StreamClient.onAuthError (credentials invalid) | Fix URL/key/auth in settings | manual (no retry) |
| rtmpConnectFailed | StreamClient.onConnectionFailed (network/host unreachable) | Check URL, network, firewall | exponential backoff |
| rtmpDisconnected | StreamClient.onDisconnect (normal close or unexpected) | Retry or check endpoint | exponential backoff |
| usbDetached | USB device physically removed while streaming | Reconnect card | manual |
| serviceStartDenied | foreground service start() rejected by OS | Retry or check device policies | manual |
| unknown(detail) | unclassified error | Retry or restart app | manual |

### ReconnectPolicy (Dart)

- On `rtmpDisconnected` or `rtmpConnectFailed` while user wants live: exponential backoff 1, 2, 4, 8, 16, 30, 30… seconds, max 10 attempts, jitter ±20%
- Never on `rtmpAuthFailed`, `usbDetached`, permission errors, camera errors
- State visible in status panel (reconnecting, attempt N of 10, next retry in Xs)
- User tapping Stop cancels reconnect loop
- Stats: track reconnect count (cumulative per session)

### Statistics & Logging

- Native emits 1 Hz samples: (bitrateKbps, fps, droppedFrames, sentBytes, congestion%)
- Dart aggregates rolling averages and session totals
- Logging: structured, sanitized; debug logs only when developer toggle ON
- Secrets never logged; mask username/password (show last 4 chars)

## Observability (OpenTelemetry)

- Every app emits logs, metrics (histograms/counters/gauges), and traces; OTLP is the wire format — `GazerTelemetry` facade (`lib/telemetry/`)
- **Packages evaluated (2026-09-09):** `opentelemetry` (Workiva, US, Apache-2.0, 0.18.11) — traces Beta, metrics Alpha, logs unimplemented; `dartastic_opentelemetry` (Dartastic.io/MindfulSoftwareLLC, 0.11.0, 12 days old, 13 likes) claims full traces+metrics+logs OTLP but is too new/unproven to depend on for M1. Neither adopted.
- **Decision:** hand-rolled `OtlpHttpExporter` — OTLP/HTTP JSON per the OTLP spec's JSON Protobuf Encoding mapping (opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding), built on the already-pinned `dio` — zero new pub.dev dependencies
- No process env on mobile: `--dart-define` (`OTEL_EXPORTER_OTLP_ENDPOINT`/`_PROTOCOL`/`_HEADERS`, `OTEL_SERVICE_NAME`, `GAZER_ENV`) is the build-time default, overridden by Settings > Developer "Telemetry endpoint" (`shared_preferences` key `gazer.telemetry.endpoint`; headers in `flutter_secure_storage` key `gazer.telemetry.headers`, since they may carry auth)
- Empty endpoint = export disabled, zero network calls; every signal still records to a capped (1000), drop-oldest in-memory ring buffer — status panel shows disabled/exporting/last-export-failed
- Export scheduler: every 10s, batched per signal type to `/v1/logs`, `/v1/metrics`, `/v1/traces`; a dead collector increments `exportFailures` and never throws — a bad endpoint never breaks streaming
- Metrics: histograms first (`gazer.app.startup_ms`, `gazer.rtmp.connect_latency_ms`, `gazer.stream.bitrate_kbps`), counter (`gazer.pipeline.state_change`); traces span pipeline prepare/start/stop
- Resource attrs: `service.name` (default `gazer`), `service.version` (`package_info_plus`), `deployment.environment` (`GAZER_ENV`, default `dev`), `device.model`; never ANDROID_ID or a masked secret
- Logs funnel through the existing sanitized `GazerLog` path — no attribute is ever telemetry-only unsanitized; DEBUG-level telemetry logs stay gated by the same `debugLogs` toggle, off by default
- **Test gate (blocking):** `test/telemetry/otlp_sink_test.dart` runs a local `HttpServer` as an OTLP sink, drives one log/counter/histogram/span, asserts ≥1 received of each, and prints the counts; `make mobile-telemetry-check` greps them — zero or a missing sink is a FAIL, not a pass

## Flutter App

### Screens

**HomeScreen**
- Source picker: Back camera, Front camera, each attached UVC device by product name
- Go Live button (enabled if settings valid + license allows), Stop button (visible while streaming)
- Status chip: color indicates state (idle=gray, preparing=yellow, connecting=blue, streaming=green, error=red, reconnecting=orange)
- Settings gear icon

**SettingsScreen**
- Target: URL input (rtmp/rtmps, non-empty host, path validation), stream key (optional), username & password (both-or-neither, optional)
- Quality: resolution picker {180…1080}, FPS picker {15,30,50,60}, bitrate slider 500–5000 step 100, adaptive bitrate toggle
- Audio: dropdown (auto, phone mic, USB audio, silence)
- Developer: toggle "force libuvc" (hidden by default, reveal via debug settings or long-press)
- Validation runs on every change; UI blocks Go Live if validation fails

**StatusPanel**
- Camera: on/off, back/front/UVC (name)
- UVC: connected/streaming/off, device name, negotiated format
- Stream: live/connecting/reconnecting/offline
- Connection: protocol, host, app path, stream key (masked), auth yes/no
- Stats: bitrate kbps, FPS, dropped frames, uptime, reconnect count, congestion %
- Connectivity: online/offline indicator
- License & flags: status, last-fetched time (show when feature fetch is pending at startup)
- Update: notice if newer version available; link to GitHub Release
- Foreground service: visible state
- Responsive: 600dp breakpoint; <600dp = bottom sheet, ≥600dp = side pane

### State Model (Sealed PipelineState)

```dart
sealed class PipelineState {
  const PipelineState();
}

class IdleState extends PipelineState { const IdleState(); }
class PreparingState extends PipelineState { const PreparingState(); }
class ReadyState extends PipelineState { const ReadyState(); }
class ConnectingState extends PipelineState { const ConnectingState(); }
class StreamingState extends PipelineState { const StreamingState(); }
class ReconnectingState extends PipelineState {
  final int attempt;
  final Duration nextIn;
  const ReconnectingState(this.attempt, this.nextIn);
}
class StoppingState extends PipelineState { const StoppingState(); }
class ErrorState extends PipelineState {
  final GazerError error;
  const ErrorState(this.error);
}
```

Dart owns `ReconnectingState`; native sends `connecting` → Dart transitions to `ReconnectingState` on retry.

### Storage Split

| Key | Storage | Sensitive | Validator |
|-----|---------|-----------|-----------|
| target.url | flutter_secure_storage | Yes (may embed the key) | rtmp/rtmps scheme, non-empty host |
| target.streamKey | flutter_secure_storage | Yes | optional |
| target.username | flutter_secure_storage | Yes | both-or-neither with password |
| target.password | flutter_secure_storage | Yes | both-or-neither with username |
| quality.resolution | shared_preferences | No | {180…1080} |
| quality.fps | shared_preferences | No | {15,30,50,60} |
| quality.bitrate | shared_preferences | No | 500–5000 |
| quality.adaptive | shared_preferences | No | bool |
| audio.source | shared_preferences | No | enum (auto/mic/usbAudio/silence) |
| developer.forceLibuvc | shared_preferences | No | bool |

### Validation Rules

- URL: scheme rtmp/rtmps, host non-empty, path present (e.g. /live/mystream)
- Stream key: optional; if provided and URL lacks /<key>, auto-append; never double-append
- Username/password: both-or-neither; optional pair
- Quality: resolution in {180…1080}, fps in {15,30,50,60}, bitrate in 500–5000, adaptive boolean
- Audio: source in {auto, mic, usbAudio, silence}

### Licensing & Feature Flags

- LicenseClient (app-local, temporary pending penguin-libs PR): validate + features, keepalive every 5 min while foregrounded
- Device ID: SHA-256(ANDROID_ID + package name)
- Validate at startup (non-blocking): cache result, 7-day offline grace
- Flag keys: `waddlebot.gazer.camera-stream`, `waddlebot.gazer.uvc-capture`, `waddlebot.gazer.adaptive-bitrate`, `waddlebot.gazer.rtmp-auth` (all Free tier)
- **First-launch consequence**: fresh install needs one successful flag fetch before streaming allowed; UI in StatusPanel shows "fetching features… (required to stream)" until validate succeeds
- Offline: never-seen flags default OFF; cached flags used if server unreachable

### Update Checker

- Startup + non-blocking: GET https://api.github.com/repos/penguintechinc/waddlebot/releases, filter tags matching gazer-v*.*.*, compare latest tag to package_info_plus.version
- Notify in StatusPanel only: "Update available: v1.2.3"
- Play Store auto-update remains primary
- Link opens GitHub Release page

### Responsive Layout

- Breakpoint: 600dp (MediaQuery.of(context).size.width)
- <600dp (phones): HomeScreen fullscreen, StatusPanel as bottom sheet, portrait primary
- ≥600dp (tablets): HomeScreen left pane (controls), StatusPanel right pane, landscape primary
- Shared widgets, responsive font sizes (respect MediaQuery textScaler; no fixed text sizes; no extra layout package)

### Localization

- intl + lib/l10n/app_en.arb
- No hardcoded strings
- English only in v1

## Testing Strategy

### Dart (Unit + Widget)

- Unit: validation (settings, URL, auth), ReconnectPolicy (backoff sequence, max attempts), SourceSelector (3 s wait, fallback logic), LicenseClient (cache, grace period, offline), UpdateChecker (parse GitHub releases, compare versions)
- Widget: HomeScreen (source picker, Go Live/Stop enable/disable), SettingsScreen (validation feedback), StatusPanel (state → UI mapping, stats display, both phone + tablet sizes)
- Goldens: StatusPanel phone portrait, StatusPanel tablet landscape, error states, reconnecting state
- Mocking: PigeonHostApi via test API (setMockMethodCallHandler or pigeon test_helpers), dio (MockSpec), SharedPreferences (FakeSharedPreferences), flutter_secure_storage (FakeFlutterSecureStorage)
- Coverage: ≥90% (lcov threshold in CI)

### Kotlin (JUnit)

- PigeonHostApi: verifies mapping StreamConfig → RootEncoder prepare calls, PipelineState → Dart event, GazerError codes
- SourceFactory: Camera2 external enumerate/filter/open logic, libuvc fallback decision
- Config: settings → quality/audio params validation
- Error mapping: native errors → GazerError enum
- StatsSampler: sample collection, 1 Hz emission
- No tests require a real USB device (mocking or absent device paths)

### Instrumented (androidTest)

- StreamService: lifecycle (start/stop), foreground notification appearance, partial wake lock, clean shutdown on USB detach
- Pigeon round-trip: Dart → Kotlin → Dart event loop
- Emulator only (no USB in CI)

### Native (C++)

- libuvc format-negotiation helper: MJPEG negotiation, YUY2 fallback, nearest-supported reporting
- libjpeg-turbo decode: sample MJPEG frame → RGBA verification (if cheap; else covered by instrumented test with USB absent expecting uvcOpenFailed)
- Build for arm64-v8a, armeabi-v7a, x86_64 in CI

### Manual Device Matrix (Release Gate)

Test configurations documented in README:
- Pixel 8 / Pixel 9 (Camera2 external, native UVC support)
- Galaxy S24 (libuvc fallback)
- Galaxy Tab S9 (libuvc, tablet layout, landscape)
- UGREEN HDMI capture (MS2109/MS2130)
- AVerMedia UVC card
- Both portrait and landscape orientations on phone

### Mock Data

4 seeded presets/targets for widget tests and screenshots:
- Target 1: rtmp://ingest-a.example.com/live, streamKey=demo-key-0001, no auth
- Target 2: rtmps://ingest-b.example.com/app, streamKey=demo-key-0002, username=demo / password (masked)
- Target 3: rtmp://10.0.2.2:1935/live (emulator host loopback), no key, no auth (offline test)
- Target 4: http://bad.example.com (invalid scheme, for validation tests)
- Camera: back, front, simulated UVC device (vendor/product ID from usb_device_filter.xml UGREEN entry)

### Coverage Gates

- Dart: `flutter test --coverage` → lcov summary, threshold ≥90%, fail CI if below
- Kotlin: `gradle testDebugUnitTest` with JaCoCo coverage, threshold ≥90%
- Native C++: format-negotiation and decode helpers unit-tested on host with googletest + llvm-cov, threshold ≥90% on those units; JNI/device path covered by instrumented tests + manual matrix (no coverage number required)

## Toolchain, CI, Versioning

### Dockerfile

- Base: digest-pinned Ubuntu 24.04
- Flutter 3.47.2 stable: download Linux tarball, SHA256 verify `447878859d01ca9bfdb99a85f245af07ed8a15fedcd9d189c4749e8e92d1f185`, extract
- Android cmdline-tools: download `commandlinetools-linux-15859902_latest.zip`, SHA256 verify `4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583` (RE-VERIFY before pinning)
- sdkmanager: platform 36, build-tools 36.0.x, NDK 28.2.13676358
- Java 17 (temurin or eclipse-adoptium)
- CMake 3.28+
- rootless USER appuser
- Entrypoint: make target (mobile-lint, mobile-test, mobile-build, mobile-security)

### Make Targets (repo root)

- `make mobile-lint`: flutter analyze + dart format --set-exit-if-changed + gradle lint + ktlint
- `make mobile-test`: flutter test --coverage + coverage ≥90% gate + gradle testDebugUnitTest
- `make mobile-build`: flutter build apk --split-per-abi --obfuscate --split-debug-info + flutter build appbundle
- `make mobile-security`: osv-scanner pubspec.lock + gradle deps + semgrep + gitleaks
- All targets run inside Dockerfile (no local machine setup)
- No masking of failures (no `|| true`)

### GitHub Workflow

Path-filtered to `mobile/gazer/**`:
1. **analyze**: flutter analyze
2. **test**: flutter test --coverage + coverage gate ≥90%
3. **android-unit**: gradle testDebugUnitTest
4. **build**: apk + appbundle (arm64-v8a, armeabi-v7a, x86_64), artifacts uploaded
5. **security**: osv-scanner, semgrep, gitleaks
6. **release** (on tag gazer-v*.*.* only): upload artifacts to GitHub Release
7. All actions pinned by full commit SHA

### Signing

- Upload key (internal, CI secrets): for upload to Play Store (not committed)
- App signing key (Play managed): app signing at Play Store
- CI secrets: `ANDROID_UPLOAD_KEY_STORE_B64` (base64 of the keystore file, decoded in CI), `ANDROID_UPLOAD_KEY_STORE_PASSWORD`, `ANDROID_UPLOAD_KEY_ALIAS`, `ANDROID_UPLOAD_KEY_ALIAS_PASSWORD`

### Versioning

- pubspec.yaml: `version: X.Y.Z+B` where B is the epoch build number per the house versioning skill
- Git tags: `gazer-vX.Y.Z` (separate from backend v* tags)
- Release artifacts tagged gazer-v* in GitHub Releases
- Play Store: internal build number auto-increments; public version = X.Y.Z

## Dependencies & Pins

### pub.dev Exact Versions (2026-09-07 stable, no ^/~)

| Package | Version | Purpose |
|---------|---------|---------|
| pigeon | 28.0.0 | Dart↔Kotlin channel |
| flutter_riverpod | 3.4.3 | State management (code-gen) |
| riverpod_annotation | 4.0.7 | @Riverpod annotation |
| riverpod_generator | 4.0.9 | code generation |
| go_router | 18.0.1 | Navigation |
| freezed | 4.0.1 | Code generation (models) |
| freezed_annotation | 3.1.0 | @freezed annotation (verify compat with 4.0.1) |
| json_annotation | 4.12.0 | @JsonSerializable |
| json_serializable | 6.14.1 | JSON code gen |
| build_runner | 2.16.1 | Code gen runner |
| flutter_secure_storage | 11.0.0 | Secure storage (target keys) |
| shared_preferences | 2.5.5 | Non-secret settings |
| connectivity_plus | 7.3.1 | Online/offline indicator |
| intl | 0.20.3 | Localization (match flutter_localizations version for 3.47.2) |
| package_info_plus | 10.2.1 | App version, device info |
| mocktail | 1.0.5 | Mocking in tests |
| flutter_lints | 6.0.0 | Linting |
| dio | 5.11.1 | HTTP client (LicenseClient) |
| url_launcher | 6.3.2 | Open URLs (update checker) |
| permission_handler | 13.0.2 | Runtime permissions |
| device_info_plus | 13.2.0 | ANDROID_ID, device metadata |
| crypto | 3.0.7 | SHA-256 for device ID |
| flutter_libs | git: penguintechinc/penguin-libs, path: packages/flutter_libs, ref: (commit SHA selected at implementation) | theme (ElderThemeData), FormBuilder, ConsoleVersion |

**Note**: freezed_annotation 3.1.0 compat with freezed 4.0.1 must be verified during pubspec setup.

### Android / Gradle

| Item | Version | Purpose |
|------|---------|---------|
| compileSdk | 36 | Target API level |
| targetSdk | 36 | Runtime target |
| minSdk | 29 | Android 10+ (user requirement) |
| NDK | 28.2.13676358 | Native C++ toolchain |
| AGP | 9.1.0 | Gradle plugin (from Flutter 3.47.2 template) |
| Gradle | 9.3.1 | Build tool |
| Kotlin | 2.4.0 | Language version |
| Java | 17 | Runtime (temurin/eclipse-adoptium) |
| RootEncoder | 2.8.1 | RTMP encoder (JitPack only, no extra-sources) |

### Native Third-Party (Fetched by CMake FetchContent/ExternalProject)

| Library | Pin | Provenance | Role | 16KB? |
|---------|-----|-----------|------|-------|
| libusb | v1.0.30 (2026-05-17, tarball github.com/libusb/libusb/releases/download/v1.0.30/libusb-1.0.30.tar.bz2) | US, BSD | USB device access | ✓ built with -Wl,-z,max-page-size=16384 |
| libuvc | commit d2b41e451b13206c108a38c5966b78fb718528f9 (2026-09-07, BSD) | US (Ken Tossell), BSD | UVC camera access | ✓ built with -z max-page-size=16384 |
| libjpeg-turbo | 3.2.0 (2026-06-30) | US, BSD | MJPEG → RGBA |  ✓ built with -z max-page-size=16384 |
| libyuv | commit SHA (selected from chromium.googlesource.com/libyuv/libyuv at implementation) | Google, BSD | YUY2 → ARGB | ✓ built with -z max-page-size=16384 |

All fetched with URL + SHA256 in CMakeLists.txt; built for arm64-v8a, armeabi-v7a, x86_64 with `-Wl,-z,max-page-size=16384` (Android 15+/Play Store requirement).

### Toolchain Pins

| Item | Version | Source | SHA256 |
|------|---------|--------|--------|
| Flutter Linux | 3.47.2 | https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.47.2-stable.tar.xz | 447878859d01ca9bfdb99a85f245af07ed8a15fedcd9d189c4749e8e92d1f185 |
| Android cmdline-tools | 15859902_latest | https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip | 4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583 (RE-VERIFY before use) |
| Java | 17 (temurin) | temurin 17.0.x | — |
| CMake | 3.28+ | system or download | — |
| Clang/LLVM | 18+ (Android NDK 28.2) | included in NDK | — |

## Supply-Chain Provenance

All dependencies vetted for provenance (US/international, no PRC-origin, no dead/archived):

| Library | Status | Verdict | Reason |
|---------|--------|---------|--------|
| RootEncoder | 2.8.1 (pedroSG94, Spain, 2026-09-01) | ✓ approved | active, clean author, no supply-chain red flags |
| RootEncoder `extra-sources` | — | ✗ FORBIDDEN | depends on com.herohan:UVCAndroid (shiyinghan/UVCAndroid, PRC author, 16KB-page issue, RootEncoder #1877) → supply-chain violation |
| ernestp/AndroidUSBCamera | — | ✗ FORBIDDEN | continuation of PRC-origin library → violates supply-chain rule |
| saki4510t/UVCCamera (Japan) | — | reference only | dead since 2018, no longer maintained |
| libusb | 1.0.30 (2026-05-17) | ✓ approved | US, BSD, active (GitHub) |
| libuvc | master (2026-09) | ✓ approved | US/BSD, Ken Tossell, active (GitHub) |
| libjpeg-turbo | 3.2.0 | ✓ approved | US, BSD, active (GitHub) |
| libyuv | chromium source | ✓ approved | Google, BSD, active |
| ffmpeg-kit | — | ✗ archived (2025-01) | dead, excluded |
| apivideo_live_stream | — | ✗ stale (16KB issue) | unmaintained, excluded |
| Flutter | 3.47.2 stable | ✓ approved | Google, active |
| Dart | 3.13.2 | ✓ approved | Google, active |
| pub.dev packages | [see table above] | ✓ all approved | popular, actively maintained |
| penguin-libs (flutter_libs) | — | ✓ approved | internal PenguinTech, SHA pinned |

**Decision**: Never add RootEncoder's `extra-sources` module or any PRC-origin libraries. All native dependencies fetched by CMake with immutable pins (commit SHA or release tag) + SHA256 hash verification.

## Milestones M1–M4

### M1: Shell + Settings + Status Panel + Licensing + Phone Camera → RTMP

- Pigeon channel (list devices, prepare, start, stop, events)
- HomeScreen (source picker phone cameras, Go Live/Stop)
- SettingsScreen (URL, key, quality, audio)
- StatusPanel (compact state + stats)
- LicenseClient (app-local, validate + keepalive)
- Feature flags (cache, first-launch block until fetch succeeds)
- RootEncoder: phone camera (back/front) → Camera2Source + MediaCodec H.264 → RTMP
- Adaptive bitrate + BitrateAdapter
- ReconnectPolicy (Dart): exponential backoff, max 10 attempts
- Foreground service (types: camera, microphone, connectedDevice)
- Error mapping (GazerError enum)
- Kotlin JUnit tests
- Dart unit tests (validation, LicenseClient, ReconnectPolicy)
- Widget tests (HomeScreen, SettingsScreen)
- Coverage ≥90%
- Artifacts: APK + AAB

### M2: UVC via Camera2 External + USB Audio

- CameraManager enumerate, filter LENS_FACING_EXTERNAL, open with Camera2Source.openCameraId
- SourceSelector: wait 3 s for LENS_FACING_EXTERNAL, use if present
- AudioRecord + setPreferredDevice(TYPE_USB_DEVICE/TYPE_USB_HEADSET) for USB audio
- Audio dropdown in SettingsScreen (auto/mic/USB audio/silence)
- Instrumented tests (emulator)
- Manual device: Pixel 8/9 (Camera2 external), both orientations

### M3: libuvc Path (JNI, MJPEG/YUY2)

- Native bridge: libusb + libuvc + libjpeg-turbo + libyuv
- UvcNative.kt JNI bindings, libuvc_bridge.cpp
- Format negotiation: MJPEG preferred, YUY2 fallback
- libjpeg-turbo decode (MJPEG → RGBA), libyuv (YUY2 → ARGB)
- ANativeWindow draw, SurfaceTexture input to RootEncoder
- SourceSelector: fallback to libuvc if Camera2 external absent
- Developer toggle "force libuvc" (hidden, override 3 s wait)
- Manual device: Galaxy S24, Galaxy Tab S9 (tablet layout)
- UGREEN HDMI capture, AVerMedia UVC card
- 16KB page alignment all ABIs (arm64-v8a, armeabi-v7a, x86_64)

### M4: Remove 1.0, Documentation, Release

- Remove `mobile/flutter_gazer` directory
- README: device matrix, offline vs online, permissions, troubleshooting
- docs/screenshots/: seeded presets, both orientations, error states
- docs/APP_STANDARDS.md: entry justifying native modules per building-mobile-apps skill
- Update pubspec, versions finalized
- First production release gazer-v1.0.0

## Deferred (Explicitly Out of v1)

- Live preview (flag `waddlebot.gazer.preview`, OFF, additive second render surface behind flag)
- iOS / iPadOS (later project, native modules separate per approved exception to client-flutter.md)
- WaddleBot sign-in + hub-api stream targets
- 1.0's chat, overlay, community features (may return post-v1)
- H.265/AV1 video codec
- SRT, WHIP
- Multi-target forwarding
- Recording to device storage
- Test-connection button
- Crash reporting / analytics

## Rule Exceptions & Assumptions

### APPROVED EXCEPTION: Android-First Only

Per client-flutter.md rule: "mobile apps are never split, iOS + Android together." **APPROVED EXCEPTION**: Gazer v1 is Android-first; iOS/iPadOS follows as its own project phase that adds Swift native modules (AVFoundation camera, iPadOS external UVC) to this same Flutter app; the Dart layer is platform-neutral so no redesign is needed. Cite in native-module exception entry in docs/APP_STANDARDS.md (M4).

### TEMPORARY BRIDGE: App-Local License Client

LicenseClient (validate, features, keepalive) implemented app-local (dio, SharedPreferences cache) pending a penguin-libs PR to promote it into flutter_libs. This v1 approach is temporary; the follow-up PR moves LicenseClient to penguin-libs and updates all future apps to use the shared version. Plan the PR after M1 ships. Rationale: flutter_libs exists but does not yet expose a license client; app-local is the unblock that lets development proceed without waiting for the PR.

### NATIVE MODULES JUSTIFICATION

Per building-mobile-apps skill: custom Kotlin + C++ code fills gaps (UVC support via libusb+libuvc not available in Dart ecosystem, foreground service for background streaming). No native code is written without JUnit/instrumented test coverage. Dart retains all business logic; Kotlin is bridge only. Documented in docs/APP_STANDARDS.md (M4).

### ASSUMPTIONS

- Only UVC-compliant capture cards supported (vendor-driver cards out of scope)
- Capture-card audio requires USB Audio Class exposure
- Phones and tablets share one APK (responsive layout, not separate builds)
- English only in v1 (intl framework in place for future locales)
- Foreground service start always originates from a user tap in the foreground activity, so Android 12+ background-start restrictions never apply
- RTMP/RTMPS endpoints are user-supplied; no validation of endpoint availability before Go Live (pre-flight check deferred)
- Stats sampled at 1 Hz; UI aggregates locally (no server-side telemetry)
