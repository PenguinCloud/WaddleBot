# Gazer Mobile 2.0 — M1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Gazer Mobile 2.0 Milestone 1 — a working, shippable Android app (shell + settings + status panel + licensing/feature-flags + phone camera → RTMP with adaptive bitrate, Dart-owned reconnect, and a foreground service) built at `mobile/gazer/`, replacing 1.0's non-functional scaffolding.

**Architecture:** Flutter/Dart owns all business logic, state, validation, settings persistence, licensing, and reconnect policy; a thin Kotlin layer (Pigeon-generated channel) wraps RootEncoder 2.8.1 (`library` module only) for MediaCodec H.264/AAC capture-and-publish and a foreground `StreamService`. Riverpod (codegen) wires providers over the services layer; go_router drives navigation; freezed models give the app's sealed `PipelineState` and settings/stats value types. All builds, lints, tests, and scans run inside a single digest- and checksum-pinned Ubuntu 24.04 toolchain container via repo-root `make mobile-*` targets — never on the host.

**Tech Stack:** Flutter 3.47.2 / Dart 3.13.2, Riverpod 3.4.3 (codegen), go_router 18.0.1, freezed 4.0.1, Pigeon 28.0.0, flutter_secure_storage 11.0.0 + shared_preferences 2.5.5, dio 5.11.1; Android: Kotlin 2.4.0, AGP 9.1.0, Gradle 9.3.1, compileSdk/targetSdk 36, minSdk 29, RootEncoder 2.8.1 (JitPack); JUnit 5 + MockK + JaCoCo on the Kotlin side; GitHub Actions CI building a shared toolchain container image once per Dockerfile-content hash.

**Spec:** `/home/penguin/code/waddlebot/.worktrees/gazer-mobile-v2/docs/superpowers/specs/2026-09-07-gazer-mobile-v2-design.md`

## Global Constraints

Every task's requirements implicitly include these (copied from the spec unless noted as a process rule):

- **Android floors:** "Android 10+ (minSdk 29), targetSdk 36, compileSdk 36" (spec, Non-Functional).
- **Flutter/Dart pin:** Flutter `3.47.2 stable` / Dart `3.13.2` — "✓ approved" in Supply-Chain Provenance; both authoritative, no substitutions.
- **Exact pins, no ranges:** pub.dev table is headed "pub.dev Exact Versions (2026-09-07 stable, no ^/~)" — every `pubspec.yaml` entry is a literal version, never `^`/`~`.
- **RootEncoder scope:** "RootEncoder 2.8.1, not custom encoder" (Decision #7) and "Forbid RootEncoder `extra-sources` module (UVC source)" (Decision #8) — only `com.github.pedroSG94.RootEncoder:library:2.8.1` may ever be depended on; `extra-sources` is never added, in M1 or later milestones.
- **Supply chain:** "Supply-chain: no PRC-origin, no dead/archived libraries (ffmpeg-kit, apivideo_live_stream out); all third-party pinned by commit/tag + SHA256" (spec, Non-Functional).
- **Secrets storage:** "Secure storage: platform-native only (SharedPreferences for non-secret; flutter_secure_storage for secrets)" (spec, Non-Functional) — target URL/key/username/password never touch shared_preferences or plaintext files.
- **Coverage gates:** "Coverage ≥90% mandatory: Dart enforced in CI via lcov threshold; Kotlin via JaCoCo on testDebugUnitTest; native C++ helpers unit-tested on host with googletest + llvm-cov ≥90%" (spec, Non-Functional).
- **Kotlin test discipline:** "No native code is written without JUnit/instrumented test coverage." (spec, NATIVE MODULES JUSTIFICATION) — every Kotlin change in this plan ships with a JUnit (or androidTest) test in the same task.
- **Dart owns decisions, Kotlin is bridge only:** Decision #5 — "As much Flutter as possible; Kotlin only to fill gaps" — business logic, validation, retry policy, and state ownership live in Dart; Kotlin only captures/encodes/publishes and reports events back.
- **Banned word:** the word "restream" (and any casing/spacing variant of it) never appears in code, comments, strings, commit messages, or docs in this app — use "stream"/"publish"/"RTMP target" instead.
- **Container-only tooling:** "All targets run inside Dockerfile (no local machine setup)" and "No masking of failures (no `|| true`)" (spec, Make Targets) — every lint/test/build/security command in this plan runs through a `make mobile-*` target, which runs inside `gazer-toolchain:3.47.2`; the host's snap Flutter is never invoked directly.
- **Commit trailers:** every commit created while executing this plan ends with:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  ```
- **Commit prefixes:** `feat(gazer):`, `test(gazer):`, `chore(gazer):`, `ci(gazer):`, `docs(gazer):` per the nature of the change.

## Environment & Commands

- Host: Linux x86_64, 16 cores, 92 GB RAM, Docker 29.8, `/dev/kvm` present (emulator OK later), snap Flutter present on host — **do not use it for anything in this plan; container only.**
- Toolchain image: `gazer-toolchain:3.47.2`, built by `make mobile-toolchain` from `mobile/gazer/Dockerfile`.
- Every other `mobile-*` target runs:
  ```
  docker run --rm --user $(id -u):$(id -g) \
    -v $(PWD)/mobile/gazer:/work \
    -v gazer-pub-cache:/home/appuser/.pub-cache \
    -v gazer-gradle:/home/appuser/.gradle \
    -w /work gazer-toolchain:3.47.2 <cmd>
  ```
- `make mobile-lint` — `flutter analyze` + `dart format --set-exit-if-changed .` + `gradlew ktlintCheck lint` (once Task 2's Android project exists).
- `make mobile-test` — `flutter test --coverage` then `scripts/coverage_gate.sh 90` (lcov mode); fails the build below 90% or on a zero-file report.
- `make mobile-test-android` — `gradlew testDebugUnitTest jacocoTestReport` then `scripts/coverage_gate.sh 90 <jacoco xml> jacoco`.
- `make mobile-build` — `flutter build apk --split-per-abi --obfuscate --split-debug-info` + `flutter build appbundle` (same flags).
- `make mobile-security` — `osv-scanner` (pubspec.lock + gradle deps), `semgrep`, `gitleaks`.
- `make mobile-codegen` — Pigeon + `build_runner` + `intl`/l10n generation, all inside the container.
- `make mobile-run CMD="..."` — passthrough for a single ad hoc in-container command, e.g. `make mobile-run CMD="flutter test test/services/reconnect_policy_test.dart"`.
- Repo-root `Makefile` already exists (backend targets) — this plan **adds** `mobile-*` targets, never rewrites the file. Repo-root `.github/workflows/flutter-gazer.yml` is the 1.0 workflow — leave it untouched; this plan adds a new `.github/workflows/gazer-mobile.yml`.

## File Map (M1) — create unless marked Modify

```
mobile/gazer/
  .flutter-version                       3.47.2
  Dockerfile                             toolchain (Ubuntu 24.04 digest-pinned, Flutter 3.47.2 tar.xz sha256 447878859d01ca9bfdb99a85f245af07ed8a15fedcd9d189c4749e8e92d1f185, cmdline-tools zip (RE-VERIFY sha), platforms;android-36, build-tools;36.0.0, ndk;28.2.13676358, Temurin 17, CMake, USER appuser)
  .dockerignore
  pubspec.yaml                           exact pins (see Pins), pubspec.lock committed
  analysis_options.yaml                  flutter_lints + house rules (prefer_const_constructors, avoid_print, prefer_single_quotes, use_build_context_synchronously)
  l10n.yaml                              arb-dir lib/l10n, template app_en.arb, output-class AppLocalizations, nullable-getter false
  README.md                              what works offline vs online, permissions, device matrix, how to build/test (writer E)
  pigeons/pipeline.dart                  Pigeon contract (below)
  lib/main.dart                          runApp(ProviderScope(child: GazerApp()))
  lib/app.dart                           GazerApp: MaterialApp.router, ElderThemeData dark, go_router routes '/', '/settings'
  lib/config/constants.dart              licenseBaseUrl, flag keys, github releases url, keepalive interval, grace days
  lib/config/flag_keys.dart              const class FlagKeys { cameraStream='waddlebot.gazer.camera-stream', uvcCapture=..., adaptiveBitrate=..., rtmpAuth=... }
  lib/models/quality.dart                enum Resolution, enum FrameRate, class QualitySettings (freezed)
  lib/models/stream_target_settings.dart StreamTargetSettings (freezed) + effectiveUrl logic lives in TargetValidator (not the model)
  lib/models/gazer_settings.dart         GazerSettings (freezed): target, quality, audio (AudioSourceChoice), forceLibuvc
  lib/models/pipeline_state.dart         sealed PipelineState + GazerError
  lib/models/stream_stats.dart           StreamStats (freezed)
  lib/models/license_state.dart          LicenseState, LicenseStatus, FlagSnapshot
  lib/models/update_info.dart            UpdateInfo
  lib/pigeon/pipeline.g.dart             GENERATED (commit it)
  lib/services/target_validator.dart     TargetValidator
  lib/services/settings_repository.dart  abstract SettingsRepository + SecureSettingsRepository
  lib/services/reconnect_policy.dart     ReconnectPolicy
  lib/services/device_id.dart            DeviceIdProvider (sha256(ANDROID_ID + packageName))
  lib/services/license_client.dart       LicenseClient + LicenseCache (shared_preferences JSON)
  lib/services/feature_flags.dart        FeatureFlags
  lib/services/update_checker.dart       UpdateChecker
  lib/services/native_event_bridge.dart  NativeEventBridge implements GazerFlutterApi → broadcast streams
  lib/services/pipeline_controller.dart  PipelineController
  lib/providers/settings_provider.dart   SettingsNotifier (Riverpod codegen)
  lib/providers/license_provider.dart    licenseProvider, featureFlagsProvider
  lib/providers/connectivity_provider.dart
  lib/providers/devices_provider.dart    videoDevicesProvider, audioDevicesProvider
  lib/providers/pipeline_provider.dart   pipelineControllerProvider, pipelineStateProvider, streamStatsProvider
  lib/providers/update_provider.dart
  lib/screens/home_screen.dart
  lib/screens/settings_screen.dart
  lib/screens/status_panel.dart          StatusPanel widget + showStatusPanel(context) (bottom sheet <600dp) / side pane ≥600dp handled in HomeScreen layout
  lib/widgets/status_chip.dart, lib/widgets/source_picker.dart, lib/widgets/masked_text.dart
  lib/l10n/app_en.arb
  test/... (mirror lib/ paths), test/goldens/, test/fixtures/mock_targets.dart, test/helpers/fake_host_api.dart
  integration_test/go_live_unreachable_test.dart
  android/app/build.gradle.kts, android/build.gradle.kts, android/settings.gradle.kts, android/gradle.properties, android/gradle/libs.versions.toml
  android/app/src/main/AndroidManifest.xml
  android/app/src/main/kotlin/io/waddlebot/gazer/MainActivity.kt
  android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/Pipeline.g.kt   GENERATED (commit it)
  android/app/src/main/kotlin/io/waddlebot/gazer/PigeonHostApiImpl.kt
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamEngine.kt        interface + RootEncoderEngine
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/GazerPipeline.kt
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/PipelineListener.kt
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/ErrorMapper.kt
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StatsSampler.kt
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamService.kt
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/VideoSourceFactory.kt   PhoneCameraSource
  android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/AudioSourceFactory.kt   mic / SilenceAudioSource
  android/app/src/test/kotlin/io/waddlebot/gazer/...   JUnit5 + MockK
  android/app/src/androidTest/kotlin/io/waddlebot/gazer/StreamServiceTest.kt
Modify:
  Makefile (repo root)                   add mobile-* targets
  .github/workflows/gazer-mobile.yml     new (repo root)
  .gitignore (repo root)                 add mobile/gazer/build/, mobile/gazer/.dart_tool/, mobile/gazer/coverage/, mobile/gazer/android/.gradle/ if not covered
```

## Shared Contract

Executors of Tasks 2 onward, and every other writer's tasks, read this plan — not the skeleton. Names and signatures below are used **verbatim**; never invent alternatives.

### Pigeon (pigeons/pipeline.dart) — Task 6 creates it; every later task consumes the generated APIs
```dart
import 'package:pigeon/pigeon.dart';

@ConfigurePigeon(PigeonOptions(
  dartOut: 'lib/pigeon/pipeline.g.dart',
  dartTestOut: 'test/pigeon/pipeline_test.g.dart',
  kotlinOut: 'android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/Pipeline.g.kt',
  kotlinOptions: KotlinOptions(package: 'io.waddlebot.gazer.pigeon'),
))
library;

enum VideoDeviceKind { backCamera, frontCamera, uvcCamera2, uvcLibuvc }
enum AudioDeviceKind { mic, usbAudio, silence }
enum NativePipelineState { idle, preparing, ready, connecting, streaming, stopping, error }
enum GazerErrorCode {
  usbPermissionDenied, uvcNoUsableFormat, uvcOpenFailed, cameraUnavailable, cameraInUse,
  encoderFailed, audioSourceFailed, rtmpAuthFailed, rtmpConnectFailed, rtmpDisconnected,
  usbDetached, serviceStartDenied, unknown,
}
enum OutputOrientation { landscape, portrait }

class VideoDevice { late String id; late VideoDeviceKind kind; late String name; int? vendorId; int? productId; }
class AudioDevice { late String id; late AudioDeviceKind kind; late String name; }
class StreamConfig {
  late String videoDeviceId; late String audioDeviceId;
  late int width; late int height; late int fps;
  late int videoBitrateKbps; late bool adaptiveBitrate; late int audioBitrateKbps;
  late OutputOrientation orientation;
}
class StreamTarget { late String url; String? username; String? password; }   // url already has the key appended by Dart
class PrepareResult { late bool ok; GazerErrorCode? error; String? detail; int? negotiatedWidth; int? negotiatedHeight; int? negotiatedFps; String? negotiatedFormat; }
class StatsSample { late int bitrateKbps; late double fps; late int droppedVideoFrames; late int sentBytes; late double congestionPercent; }
class StateEvent { late NativePipelineState state; GazerErrorCode? error; String? detail; }

@HostApi()
abstract class GazerHostApi {
  List<VideoDevice> listVideoDevices();
  List<AudioDevice> listAudioDevices();
  @async bool requestUsbPermission(String deviceId);   // M1: always false (no USB devices listed)
  @async PrepareResult prepare(StreamConfig config);
  @async void start(StreamTarget target);
  @async void stop();
  void setVideoBitrate(int kbps);
  NativePipelineState getState();
}

@FlutterApi()
abstract class GazerFlutterApi {
  void onStateChanged(StateEvent event);
  void onStats(StatsSample sample);
  void onUsbAttached(VideoDevice device);
  void onUsbDetached(String deviceId);
  void onAuthResult(bool ok);
}
```
Device ids in M1: "camera:back", "camera:front" (Kotlin resolves to Camera2 ids by LENS_FACING), audio "audio:mic", "audio:silence".

### Dart models (freezed 4: `@freezed abstract class X with _$X`)
- `enum Resolution { p180(320,180), p360(640,360), p540(960,540), p720(1280,720), p1080(1920,1080); final int width; final int height; String get label => '${height}p'; }` default `Resolution.p540`.
- `enum FrameRate { fps15(15), fps30(30), fps50(50), fps60(60); final int value; }` default `FrameRate.fps30`.
- `enum AudioSourceChoice { auto, mic, usbAudio, silence }` default `auto`.
- `QualitySettings({required Resolution resolution, required FrameRate frameRate, required int videoBitrateKbps, required bool adaptiveBitrate})`; `QualitySettings.defaults()` = p540/fps30/2000/true; constants `kMinBitrateKbps = 500`, `kMaxBitrateKbps = 5000`, `kBitrateStepKbps = 100`, `kAudioBitrateKbps = 128`.
- `StreamTargetSettings({required String url, String? streamKey, String? username, String? password})`; `StreamTargetSettings.empty()`.
- `GazerSettings({required StreamTargetSettings target, required QualitySettings quality, required AudioSourceChoice audio, required bool forceLibuvc})`; `GazerSettings.defaults()`.
- `GazerError({required GazerErrorCode code, String? detail})`.
- `sealed class PipelineState` with subclasses exactly: `IdleState`, `PreparingState`, `ReadyState`, `ConnectingState`, `StreamingState`, `ReconnectingState(int attempt, Duration nextIn)`, `StoppingState`, `ErrorState(GazerError error)`; all `const`, with `==`/hashCode (freezed or manual).
- `StreamStats({required int currentBitrateKbps, required int averageBitrateKbps, required double fps, required int droppedFrames, required int sentBytes, required Duration uptime, required int reconnectCount, required double congestionPercent})`; `StreamStats.zero()`.
- `enum LicenseStatus { unknown, valid, gracePeriod, invalid }`; `LicenseState({required LicenseStatus status, required Map<String,bool> flags, DateTime? lastFetched, required String deviceId})`; `LicenseState.initial(deviceId)`.
- `UpdateInfo({required String latestVersion, required String currentVersion, required Uri releaseUrl})`.
- `ValidationIssue({required String field, required String messageKey})` — messageKey is an l10n key.

### Dart services (exact public API)
- `class TargetValidator { const TargetValidator(); List<ValidationIssue> validate(StreamTargetSettings t); static String effectiveUrl(StreamTargetSettings t); }` — rules: scheme rtmp|rtmps; host non-empty; path present (at least '/app'); key optional: if non-empty and the url's last path segment != key, append '/<key>'; never double-append; username/password both-or-neither. `effectiveUrl` never logs.
- `abstract class SettingsRepository { Future<GazerSettings> load(); Future<void> save(GazerSettings s); }`; `class SecureSettingsRepository implements SettingsRepository { SecureSettingsRepository({required FlutterSecureStorage secure, required SharedPreferencesAsync prefs}); }` keys: secure `gazer.target.url|streamKey|username|password`; prefs `gazer.quality.resolution|fps|bitrate|adaptive`, `gazer.audio.source`, `gazer.developer.forceLibuvc`.
- `class ReconnectPolicy { ReconnectPolicy({int maxAttempts = 10, Duration base = const Duration(seconds: 1), Duration cap = const Duration(seconds: 30), double jitter = 0.2, Random? random}); bool shouldRetry(GazerErrorCode code); /* true only for rtmpConnectFailed, rtmpDisconnected */ Duration? delayFor(int attempt); /* attempt is 1-based; null when attempt > maxAttempts; base*2^(attempt-1) capped, ± jitter */ }`
- `abstract class DeviceIdProvider { Future<String> deviceId(); }`; `class AndroidDeviceIdProvider implements DeviceIdProvider { AndroidDeviceIdProvider({required DeviceInfoPlugin deviceInfo, required PackageInfo packageInfo}); }` → sha256 hex of `'$androidId:$packageName'`.
- `class LicenseClient { LicenseClient({required Dio dio, required LicenseCache cache, required DeviceIdProvider deviceIdProvider, required Clock clock, String baseUrl = kLicenseBaseUrl}); Future<LicenseState> validateAndFetchFlags(); Future<void> keepalive(); }` — POST `$baseUrl/validate` {device_id, product:'waddlebot', component:'gazer'}; POST `$baseUrl/features` → {features: {key: bool}}; POST `$baseUrl/keepalive`. On network error: return cache if lastFetched within 7 days → status gracePeriod, else status unknown with cached flags (or empty). Never throws to callers.
- `class LicenseCache { LicenseCache(SharedPreferencesAsync prefs); Future<LicenseState?> read(); Future<void> write(LicenseState s); }` key `gazer.license.state` (JSON).
- `class FeatureFlags { const FeatureFlags(LicenseState state); bool isEnabled(String key) => state.flags[key] ?? false; bool get hasFetchedOnce => state.lastFetched != null; }`
- `class UpdateChecker { UpdateChecker({required Dio dio, required String currentVersion, String releasesUrl = kGithubReleasesUrl}); Future<UpdateInfo?> check(); }` — GET releases, tags matching `^gazer-v(\d+)\.(\d+)\.(\d+)$`, semver compare, null when up-to-date or on any error.
- `class NativeEventBridge implements GazerFlutterApi { Stream<StateEvent> get stateEvents; Stream<StatsSample> get stats; Stream<VideoDevice> get usbAttached; Stream<String> get usbDetached; Stream<bool> get authResults; void dispose(); }` (broadcast StreamControllers).
- `class PipelineController { PipelineController({required GazerHostApi host, required NativeEventBridge events, required ReconnectPolicy policy, required Clock clock}); Stream<PipelineState> get state; PipelineState get current; Stream<StreamStats> get stats; Future<void> goLive(GazerSettings settings, {required List<VideoDevice> devices, required String videoDeviceId}); Future<void> stop(); void dispose(); }` — goLive: validate (throws ArgumentError if issues), build StreamConfig from settings (orientation from a `OutputOrientation orientation` param defaulting to landscape — HomeScreen passes device orientation), prepare → start(StreamTarget(url: TargetValidator.effectiveUrl(t), username, password)); state mapping native→Dart; on error with shouldRetry → ReconnectingState(attempt, delay) → after delay call host.start again; stop() cancels timers. Uses `package:clock` — NO: use an injectable `Future<void> Function(Duration) delay` named `sleeper` instead of adding a package; signature `PipelineController({..., Future<void> Function(Duration) sleeper = Future.delayed})` — and drop `Clock` everywhere; for LicenseClient use `DateTime Function() now = DateTime.now` instead of Clock.
- Providers (riverpod_annotation, `part` files): `@Riverpod(keepAlive: true) class SettingsNotifier extends _$SettingsNotifier { Future<GazerSettings> build(); Future<void> update(GazerSettings s); }`, `@Riverpod(keepAlive: true) Future<LicenseState> license(Ref ref)`, `@riverpod FeatureFlags featureFlags(Ref ref)`, `@riverpod Stream<bool> isOnline(Ref ref)`, `@riverpod Future<List<VideoDevice>> videoDevices(Ref ref)`, `@riverpod Future<List<AudioDevice>> audioDevices(Ref ref)`, `@Riverpod(keepAlive: true) PipelineController pipelineController(Ref ref)`, `@riverpod Stream<PipelineState> pipelineState(Ref ref)`, `@riverpod Stream<StreamStats> streamStats(Ref ref)`, `@riverpod Future<UpdateInfo?> updateInfo(Ref ref)`, plus overridable leaf providers `gazerHostApiProvider`, `settingsRepositoryProvider`, `licenseClientProvider`, `updateCheckerProvider`, `connectivityProvider` for tests.
- Go Live enablement rule (HomeScreen + controller): enabled iff settings valid AND `featureFlags.hasFetchedOnce && featureFlags.isEnabled(FlagKeys.cameraStream)` AND pipeline state is Idle/Ready/Error. Adaptive bitrate honoured only if `isEnabled(FlagKeys.adaptiveBitrate)`; username/password sent only if `isEnabled(FlagKeys.rtmpAuth)` (else validation issue 'rtmpAuthDisabled').

### Kotlin (package io.waddlebot.gazer)
- `interface StreamEngine { fun prepareVideo(width: Int, height: Int, bitrateBps: Int, fps: Int, rotation: Int): Boolean; fun prepareAudio(sampleRate: Int, stereo: Boolean, bitrateBps: Int): Boolean; fun startStream(url: String); fun stopStream(): Boolean; fun setVideoBitrateOnFly(bitrateBps: Int); fun setAuthorization(user: String?, password: String?); fun setReTries(n: Int); fun setTlsHostVerification(enabled: Boolean); fun sentVideoFrames(): Long; fun droppedVideoFrames(): Long; fun hasCongestion(percentUsed: Float): Boolean; fun release() }`
- `class RootEncoderEngine(context: Context, listener: ConnectChecker, video: VideoSource, audio: AudioSource) : StreamEngine` wraps `GenericStream`.
- `interface PipelineListener { fun onState(state: NativePipelineState, error: GazerErrorCode? = null, detail: String? = null); fun onStats(sample: StatsSample); fun onAuthResult(ok: Boolean) }`
- `class GazerPipeline(private val engineFactory: (ConnectChecker, VideoSource, AudioSource) -> StreamEngine, private val videoSources: VideoSourceFactory, private val audioSources: AudioSourceFactory, private val listener: PipelineListener, private val statsSampler: StatsSampler)` with `fun prepare(config: StreamConfig): PrepareResult`, `fun start(target: StreamTarget)`, `fun stop()`, `fun setVideoBitrate(kbps: Int)`, `val state: NativePipelineState`; implements ConnectChecker mapping: onConnectionStarted→connecting, onConnectionSuccess→streaming, onConnectionFailed(reason)→error(ErrorMapper.fromReason(reason)), onDisconnect→ if state==streaming error(rtmpDisconnected) else idle, onAuthError→error(rtmpAuthFailed)+onAuthResult(false), onAuthSuccess→onAuthResult(true), onNewBitrate(bitrate)→ BitrateAdapter.adaptBitrate(bitrate, engine.hasCongestion(20f)) when adaptive. Always `engine.setReTries(0)`.
- `class VideoSourceFactory(context: Context) { fun list(): List<VideoDevice>; fun create(deviceId: String): VideoSource /* Camera2Source + openCameraId(resolved id) */ }`, `class AudioSourceFactory { fun list(): List<AudioDevice>; fun create(deviceId: String): AudioSource /* MicrophoneSource or SilenceAudioSource */ }`, `class SilenceAudioSource : AudioSource()` feeding zeroed PCM16 frames at the configured rate.
- `object ErrorMapper { fun fromReason(reason: String): GazerErrorCode }` — contains "401"/"auth"/"unauthorized"→rtmpAuthFailed; "timeout"/"refused"/"unreachable"/"failed to connect"/"UnknownHost"→rtmpConnectFailed; "encoder"/"codec"→encoderFailed; else unknown.
- `class StatsSampler(private val engine: () -> StreamEngine?, private val intervalMs: Long = 1000, private val onSample: (StatsSample) -> Unit)` computes bitrateKbps from onNewBitrate values fed via `fun onBitrate(bps: Long)`, fps from sentVideoFrames delta, dropped, sentBytes accumulator, congestionPercent 0/100 from hasCongestion.
- `class StreamService : Service()` foreground (types camera|microphone), `companion object { fun start(context: Context); fun stop(context: Context); const val ACTION_STOP = "io.waddlebot.gazer.action.STOP" }`, binder exposes `val pipeline: GazerPipeline`; notification channel `gazer.stream`; partial wake lock while streaming.
- `class PigeonHostApiImpl(private val context: Context, private val flutterApi: GazerFlutterApi, private val mainHandler: Handler) : GazerHostApi` — binds to StreamService on prepare; forwards; PipelineListener → flutterApi on main thread.
- `MainActivity : FlutterActivity` → `configureFlutterEngine` sets up `GazerHostApi.setUp(messenger, PigeonHostApiImpl(...))` and `GazerFlutterApi(messenger)`.
- Tests: JUnit5 + MockK: `GazerPipelineTest` (state transitions, setReTries(0) always, adaptive on/off, auth callbacks), `ErrorMapperTest` (table), `StatsSamplerTest`, `VideoSourceFactoryTest` (device id resolution with a fake CameraManager wrapper `interface CameraIds { fun byFacing(facing: Int): String? }`), `AudioSourceFactoryTest`. androidTest: `StreamServiceTest` (start/stop, notification present, stops cleanly).

### CI (.github/workflows/gazer-mobile.yml) jobs, in this order
toolchain (build mobile/gazer/Dockerfile, tag ghcr.io/penguintechinc/waddlebot/gazer-toolchain:<sha256 of Dockerfile first 12>, push if absent; output image ref) → analyze, test (Dart, coverage gate ≥90% via lcov summary script scripts/coverage_gate.sh; fails on zero files examined), android-unit (gradle testDebugUnitTest + jacocoTestReport + gate ≥90%), build (apk --split-per-abi + appbundle; upload artifacts), security (osv-scanner on pubspec.lock + gradle dependency lock, semgrep, gitleaks), integration (emulator API 34 x86_64 via reactivecircus/android-emulator-runner, runs integration_test/ — **added by writer E in Task 21, not this task**), release (on tag gazer-v*). Triggers: push to any branch + pull_request, paths mobile/gazer/**, Makefile, .github/workflows/gazer-mobile.yml. All `uses:` pinned to full commit SHA. No `|| true` anywhere; every gate asserts a non-zero denominator.

---

### Task 1: Toolchain image and make targets

**Files:**
- Create: `mobile/gazer/Dockerfile`
- Create: `mobile/gazer/.dockerignore`
- Create: `mobile/gazer/scripts/coverage_gate.sh`
- Modify: `Makefile` (repo root — append `mobile-*` targets, do not touch existing targets)
- Test: `mobile/gazer/scripts/coverage_gate.sh` is exercised directly against synthetic fixtures in Step 9 below (no `mobile/gazer/test/` Dart tree exists yet — that starts in Task 2)

**Interfaces:**
- Consumes: nothing (first task; no prior Gazer code exists).
- Produces: Docker image tag `gazer-toolchain:3.47.2` (built by `make mobile-toolchain` from `mobile/gazer/Dockerfile`); make targets `mobile-toolchain`, `mobile-run`, `mobile-lint`, `mobile-test`, `mobile-test-android`, `mobile-build`, `mobile-security`, `mobile-codegen`, `mobile-clean` (all other writers' tasks assume these exist and behave exactly per Environment & Commands above); `mobile/gazer/scripts/coverage_gate.sh <threshold> [report-path] [lcov|jacoco]` (exit 0 = pass, exit 1 = fail, used by both `mobile-test` and `mobile-test-android`).

- [ ] **Step 1: Confirm the target doesn't exist yet (failing check)**

Run: `make mobile-toolchain`
Expected: `make: *** No rule to make target 'mobile-toolchain'.  Stop.`

- [ ] **Step 2: Scaffold the app directory and `.dockerignore`**

```bash
mkdir -p mobile/gazer/scripts
```

`mobile/gazer/.dockerignore`:
```
.dart_tool/
.flutter-plugins
.flutter-plugins-dependencies
.packages
build/
coverage/
android/.gradle/
android/app/build/
android/build/
android/local.properties
*.iml
.idea/
.vscode/
.DS_Store
.git/
```

Run: `test -f mobile/gazer/.dockerignore && echo OK`
Expected: `OK`

- [ ] **Step 3: Obtain the Ubuntu 24.04 base image digest**

Run:
```bash
docker buildx imagetools inspect ubuntu:24.04 --format '{{json .Manifest.Digest}}'
```
Expected: a single JSON string like `"sha256:xxxxxxxx...64 hex chars...xxxx"`. Strip the quotes and the leading `sha256:` — that hex string is `$DIGEST` used in Step 5. If this command fails (no network, no buildx), stop and report; do not fabricate a digest.

- [ ] **Step 4: Re-verify the Android cmdline-tools SHA256 before trusting it**

The pin `4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583` was carried over from the design spec. Re-verify it independently before it goes in the Dockerfile:

```bash
set -euo pipefail
curl -fsSL -o /tmp/cmdline-tools-verify.zip \
  https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip
ACTUAL_SHA=$(sha256sum /tmp/cmdline-tools-verify.zip | awk '{print $1}')
EXPECTED_SHA=4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583
echo "actual:   $ACTUAL_SHA"
echo "expected: $EXPECTED_SHA"
if [ "$ACTUAL_SHA" != "$EXPECTED_SHA" ]; then
  echo "MISMATCH -- STOP. Do not write this SHA into the Dockerfile. Re-check https://developer.android.com/studio#command-line-tools-only for the currently-published hash, update the pin in this plan and in libs.versions.toml comments, and re-run this step." >&2
  exit 1
fi
echo "cmdline-tools sha256 re-verified OK"
rm /tmp/cmdline-tools-verify.zip
```
Expected: `cmdline-tools sha256 re-verified OK`. Cross-check by fetching `https://developer.android.com/studio#command-line-tools-only` (WebFetch or manual) and confirming the published SHA-256 for `commandlinetools-linux-15859902_latest.zip` matches; the direct download+`sha256sum` check above is authoritative if the page cannot be scraped (it is heavily JS-rendered). On any mismatch, halt Task 1 — do not proceed to Step 5.

- [ ] **Step 5: Write the Dockerfile, substituting the real Ubuntu digest**

```bash
set -euo pipefail
cat > mobile/gazer/Dockerfile <<'DOCKERFILE_EOF'
# syntax=docker/dockerfile:1.7
#
# Gazer Mobile 2.0 toolchain image. Every mobile-* make target in the
# repo-root Makefile runs inside this image -- nothing in mobile/gazer is
# ever built, linted, tested, or packaged with the host's Flutter/Android
# SDK. Single stage: this image ships no runtime app of its own, it *is*
# the build tool, so there is no separate "runtime" half to split into a
# second stage.
FROM ubuntu@sha256:__UBUNTU24_04_DIGEST__

LABEL org.opencontainers.image.title="gazer-toolchain" \
      org.opencontainers.image.description="Flutter 3.47.2 + Android SDK 36 + Temurin 17 toolchain for mobile/gazer" \
      org.opencontainers.image.source="https://github.com/penguintechinc/waddlebot"

ARG DEBIAN_FRONTEND=noninteractive

# --- Base OS packages (rarely changes -> keep first for cache reuse) ------
# cmake here satisfies the spec's "CMake 3.28+ system or download" pin
# (Ubuntu 24.04's repo cmake is 3.28.x); clang/ninja are pre-installed now
# so the same image serves M2/M3's native libuvc bridge without a rebuild.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        gnupg \
        unzip \
        xz-utils \
        cmake \
        ninja-build \
        clang \
        python3 \
        file \
    && rm -rf /var/lib/apt/lists/*

# --- Temurin 17 (Eclipse Adoptium apt repo; GPG key pinned by fingerprint) -
# Fingerprint verified 2026-09-07 by downloading
# https://packages.adoptium.net/artifactory/api/gpg/key/public and running
# `gpg --show-keys --with-fingerprint --with-colons` on the result; this is
# Eclipse Adoptium's Temurin apt signing key fingerprint.
ENV ADOPTIUM_GPG_FPR="3B04D753C9050D9A5D343F39843C48A565F8F04B"
RUN curl -fsSL https://packages.adoptium.net/artifactory/api/gpg/key/public -o /tmp/adoptium.asc \
    && ACTUAL_FPR=$(gpg --show-keys --with-fingerprint --with-colons /tmp/adoptium.asc | awk -F: '/^fpr:/ {print $10; exit}') \
    && if [ "$ACTUAL_FPR" != "$ADOPTIUM_GPG_FPR" ]; then \
         echo "Adoptium GPG key fingerprint mismatch: got $ACTUAL_FPR, expected $ADOPTIUM_GPG_FPR -- ABORT" >&2; \
         exit 1; \
       fi \
    && gpg --dearmor -o /usr/share/keyrings/adoptium.gpg /tmp/adoptium.asc \
    && rm /tmp/adoptium.asc \
    && echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(awk -F= '/^VERSION_CODENAME/{print $2}' /etc/os-release) main" > /etc/apt/sources.list.d/adoptium.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends temurin-17-jdk \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/temurin-17-jdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# --- Non-root user (UID 1000) ----------------------------------------------
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

# --- Flutter 3.47.2 (sha256-verified tarball) ------------------------------
ENV FLUTTER_SDK_SHA256="447878859d01ca9bfdb99a85f245af07ed8a15fedcd9d189c4749e8e92d1f185"
RUN curl -fsSL https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.47.2-stable.tar.xz -o /tmp/flutter.tar.xz \
    && echo "${FLUTTER_SDK_SHA256}  /tmp/flutter.tar.xz" | sha256sum -c - \
    && tar -xJf /tmp/flutter.tar.xz -C /opt \
    && rm /tmp/flutter.tar.xz \
    && chown -R appuser:appuser /opt/flutter
ENV PATH="/opt/flutter/bin:${PATH}"

# --- Android cmdline-tools (sha256-verified zip; independently re-verified
# as Task 1 Step 4 before this pin was trusted) -----------------------------
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME="${ANDROID_SDK_ROOT}"
ENV ANDROID_NDK_HOME="${ANDROID_SDK_ROOT}/ndk/28.2.13676358"
ENV CMDLINE_TOOLS_SHA256="4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583"
RUN mkdir -p "${ANDROID_SDK_ROOT}/cmdline-tools" \
    && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip -o /tmp/cmdline-tools.zip \
    && echo "${CMDLINE_TOOLS_SHA256}  /tmp/cmdline-tools.zip" | sha256sum -c - \
    && unzip -q /tmp/cmdline-tools.zip -d "${ANDROID_SDK_ROOT}/cmdline-tools" \
    && mv "${ANDROID_SDK_ROOT}/cmdline-tools/cmdline-tools" "${ANDROID_SDK_ROOT}/cmdline-tools/latest" \
    && rm /tmp/cmdline-tools.zip \
    && chown -R appuser:appuser "${ANDROID_SDK_ROOT}"
ENV PATH="${ANDROID_SDK_ROOT}/cmdline-tools/latest/bin:${ANDROID_SDK_ROOT}/platform-tools:${ANDROID_SDK_ROOT}/build-tools/36.0.0:${PATH}"

# --- SDK packages (as appuser: sdkmanager writes under $ANDROID_SDK_ROOT,
# which is already chown'd to appuser above) --------------------------------
# Two separate RUN layers -- not chained with `&&` -- so writer E's Task 21 can find and modify
# the package-install invocation on its own (it appends "system-images;android-34;google_apis;
# x86_64" and "emulator" to this exact list for the integration-test emulator). cmdline-tools is
# deliberately NOT re-listed as an sdkmanager package here: it was already unpacked directly at
# ${ANDROID_SDK_ROOT}/cmdline-tools/latest above, which IS the "cmdline-tools;latest" package as
# far as sdkmanager is concerned -- asking sdkmanager to install it again is redundant.
RUN yes | sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" --licenses > /dev/null

RUN sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" \
      "platforms;android-36" \
      "build-tools;36.0.0" \
      "ndk;28.2.13676358" \
      "platform-tools"

# --- flutter config (as appuser so caches land under $HOME, matching the
# gazer-pub-cache / gazer-gradle named volumes mounted by every mobile-*
# make target) ---------------------------------------------------------------
RUN flutter config --no-analytics \
    && flutter precache --android

USER root
RUN mkdir -p /work && chown appuser:appuser /work
WORKDIR /work
USER appuser

# No ENTRYPOINT: every mobile-* make target passes its full command as the
# container CMD (`docker run ... gazer-toolchain:3.47.2 <cmd>`). This CMD
# only matters for `docker run gazer-toolchain:3.47.2` with no arguments.
CMD ["bash", "-lc", "flutter --version"]
DOCKERFILE_EOF

DIGEST_JSON=$(docker buildx imagetools inspect ubuntu:24.04 --format '{{json .Manifest.Digest}}')
DIGEST=$(echo "$DIGEST_JSON" | tr -d '"' | sed 's/^sha256://')
if [ -z "$DIGEST" ]; then
  echo "Empty digest from docker buildx imagetools inspect -- STOP, do not proceed" >&2
  exit 1
fi
sed -i "s/__UBUNTU24_04_DIGEST__/${DIGEST}/" mobile/gazer/Dockerfile
if grep -q '__UBUNTU24_04_DIGEST__' mobile/gazer/Dockerfile; then echo "sentinel still present -- substitution failed" >&2; exit 1; fi
grep '^FROM ubuntu@sha256:' mobile/gazer/Dockerfile
```
Expected final line printed: `FROM ubuntu@sha256:<64 hex chars>` with no `__UBUNTU24_04_DIGEST__` remaining anywhere in the file.

- [ ] **Step 6: Write `scripts/coverage_gate.sh`**

`mobile/gazer/scripts/coverage_gate.sh`:
```bash
#!/usr/bin/env bash
# Fails the build when line coverage is below the given threshold, or when
# the coverage report contains zero examined source files -- a scanner
# pointed at nothing is a FAILURE, not a pass (critical-rules.md
# Verification Integrity: assert a non-zero denominator).
#
# Usage: coverage_gate.sh <threshold-percent> [report-path] [lcov|jacoco]
#   lcov mode (default): report-path defaults to coverage/lcov.info
#   jacoco mode: report-path defaults to
#     android/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml
set -euo pipefail

THRESHOLD="${1:?usage: coverage_gate.sh <threshold-percent> [report-path] [lcov|jacoco]}"
REPORT_TYPE="${3:-lcov}"

if [[ "${REPORT_TYPE}" == "jacoco" ]]; then
  REPORT_PATH="${2:-android/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml}"
  if [[ ! -f "${REPORT_PATH}" ]]; then
    echo "coverage_gate: jacoco report not found at ${REPORT_PATH}" >&2
    exit 1
  fi
  read -r MISSED COVERED <<PYOUT
$(python3 - "${REPORT_PATH}" <<'PYEOF'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
counters = [c for c in root.findall("counter") if c.get("type") == "LINE"]
if not counters:
    print("0 0")
else:
    counter = counters[0]
    print(f"{counter.get('missed')} {counter.get('covered')}")
PYEOF
)
PYOUT
  TOTAL=$((MISSED + COVERED))
  if [[ "${TOTAL}" -eq 0 ]]; then
    echo "coverage_gate: zero lines examined in ${REPORT_PATH} -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  PERCENT=$(python3 -c "print(f'{${COVERED} / ${TOTAL} * 100:.2f}')")
  echo "coverage_gate: ${TOTAL} lines examined (jacoco LINE counter), ${COVERED} covered"
else
  REPORT_PATH="${2:-coverage/lcov.info}"
  if [[ ! -f "${REPORT_PATH}" ]]; then
    echo "coverage_gate: lcov report not found at ${REPORT_PATH}" >&2
    exit 1
  fi
  SF_COUNT=$(grep -c '^SF:' "${REPORT_PATH}" || :)   # grep -c prints 0 and exits 1 on no match; the zero is then rejected below
  if [[ "${SF_COUNT}" -eq 0 ]]; then
    echo "coverage_gate: zero SF (source file) records in ${REPORT_PATH} -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  LF_TOTAL=$(grep '^LF:' "${REPORT_PATH}" | awk -F: '{s+=$2} END {print s+0}')
  LH_TOTAL=$(grep '^LH:' "${REPORT_PATH}" | awk -F: '{s+=$2} END {print s+0}')
  if [[ "${LF_TOTAL}" -eq 0 ]]; then
    echo "coverage_gate: zero lines found (LF) across ${SF_COUNT} files in ${REPORT_PATH} -- treating as FAILURE, not a pass" >&2
    exit 1
  fi
  PERCENT=$(python3 -c "print(f'{${LH_TOTAL} / ${LF_TOTAL} * 100:.2f}')")
  echo "coverage_gate: ${SF_COUNT} files examined, ${LH_TOTAL}/${LF_TOTAL} lines covered"
fi

echo "coverage_gate: ${PERCENT}% (threshold ${THRESHOLD}%)"
awk -v p="${PERCENT}" -v t="${THRESHOLD}" 'BEGIN { exit !(p+0 >= t+0) }'
```

```bash
chmod +x mobile/gazer/scripts/coverage_gate.sh
```

- [ ] **Step 7: Prove the gate actually gates — synthetic pass/fail fixtures**

```bash
set -euo pipefail

# Fixture A: zero SF records -> must FAIL (this is the "zero items examined
# is a failure" case from critical-rules.md Verification Integrity).
printf 'TN:\nend_of_record\n' > /tmp/lcov-empty.info
if bash mobile/gazer/scripts/coverage_gate.sh 90 /tmp/lcov-empty.info lcov; then
  echo "FAIL: gate passed on a zero-SF report, it must not" >&2
  exit 1
fi
echo "OK: zero-SF report correctly rejected"

# Fixture B: below threshold -> must FAIL.
printf 'SF:a.dart\nLF:10\nLH:5\nend_of_record\n' > /tmp/lcov-low.info
if bash mobile/gazer/scripts/coverage_gate.sh 90 /tmp/lcov-low.info lcov; then
  echo "FAIL: gate passed at 50%% coverage against a 90%% threshold" >&2
  exit 1
fi
echo "OK: below-threshold report correctly rejected"

# Fixture C: above threshold -> must PASS.
printf 'SF:a.dart\nLF:10\nLH:10\nend_of_record\n' > /tmp/lcov-high.info
bash mobile/gazer/scripts/coverage_gate.sh 90 /tmp/lcov-high.info lcov
echo "OK: above-threshold report correctly accepted"

rm -f /tmp/lcov-empty.info /tmp/lcov-low.info /tmp/lcov-high.info
```
Expected: three `OK:` lines, no non-zero exit reaching the shell (the two intentional failures are caught by the `if` guards above, not allowed to abort the script).

- [ ] **Step 8: Add the `mobile-*` targets to the repo-root Makefile**

Append to `Makefile` (repo root), after the existing `pre-commit:` target — do not reorder or edit anything above it:

```makefile

# --- Gazer Mobile 2.0 (mobile/gazer) -----------------------------------
# Every target below runs inside the gazer-toolchain image -- never on the
# host. Host Flutter (snap) is never invoked directly; see docs/superpowers/
# specs/2026-09-07-gazer-mobile-v2-design.md Toolchain, CI, Versioning.
.PHONY: mobile-toolchain mobile-run mobile-lint mobile-test mobile-test-android mobile-build mobile-security mobile-codegen mobile-clean mobile-test-integration mobile-screenshots seed-mock-data-mobile
# added later: mobile-test-integration by Task 21; mobile-screenshots and seed-mock-data-mobile
# by Task 26 -- pre-declared phony here (harmless before those targets exist)
# so the whole mobile-* target set is uniformly a .PHONY gate from the very first commit.

MOBILE_IMAGE := gazer-toolchain:3.47.2
MOBILE_RUN := docker run --rm --user $(shell id -u):$(shell id -g) \
	-v $(CURDIR)/mobile/gazer:/work \
	-v gazer-pub-cache:/home/appuser/.pub-cache \
	-v gazer-gradle:/home/appuser/.gradle \
	-w /work $(MOBILE_IMAGE)

mobile-toolchain:
	docker build -t $(MOBILE_IMAGE) mobile/gazer

mobile-run:
	@test -n "$(CMD)" || { echo "usage: make mobile-run CMD=\"<command>\"" >&2; exit 1; }
	$(MOBILE_RUN) bash -lc "$(CMD)"

mobile-lint:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter analyze; dart format --set-exit-if-changed .; if [ -d android ]; then cd android && ./gradlew ktlintCheck lint; fi"

mobile-test:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter test --coverage; bash scripts/coverage_gate.sh 90 coverage/lcov.info lcov"

mobile-test-android:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; cd android && ./gradlew testDebugUnitTest jacocoTestReport && cd .. && bash scripts/coverage_gate.sh 90 android/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml jacoco"

mobile-build:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter build apk --split-per-abi --obfuscate --split-debug-info=build/symbols; flutter build appbundle --obfuscate --split-debug-info=build/symbols"

mobile-security:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; osv-scanner --lockfile=pubspec.lock; (cd android && osv-scanner -r .); semgrep --config auto --error .; gitleaks detect --source . --no-git -v"

mobile-codegen:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; dart run pigeon --input pigeons/pipeline.dart; dart run build_runner build --delete-conflicting-outputs; flutter gen-l10n"

mobile-clean:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter clean; if [ -d android ]; then cd android && ./gradlew clean; fi"
```

Run: `grep -c '^mobile-toolchain:' Makefile`
Expected: `1`

- [ ] **Step 9: Build the toolchain image**

Run: `make mobile-toolchain`
Expected: Docker build succeeds (`docker build` exits 0); note the digest/GPG/Flutter/cmdline-tools checks inside the Dockerfile are themselves fail-closed — a `sha256sum -c` or fingerprint mismatch aborts the build with a non-zero exit and a printed mismatch message. If it fails on `sdkmanager --licenses` prompts, re-check the `yes |` pipe is present (it is, above).

- [ ] **Step 10: Verify the image reports the pinned Flutter version**

Run: `make mobile-run CMD="flutter --version"`
Expected: output includes `Flutter 3.47.2` and `Dart 3.13.2` (Dart version bundled with this exact Flutter release — if the container reports a different Dart version, stop: it means `flutter_linux_3.47.2-stable.tar.xz` did not resolve to the Dart 3.13.2 pin the spec assumes, and Task 2's `pubspec.yaml` SDK constraint must be reconciled before proceeding).

- [ ] **Step 11: Commit**

```bash
git add mobile/gazer/Dockerfile mobile/gazer/.dockerignore mobile/gazer/scripts/coverage_gate.sh Makefile
git commit -m "$(cat <<'COMMIT_EOF'
ci(gazer): add toolchain image and mobile-* make targets

Digest-pinned Ubuntu 24.04 base, sha256-verified Flutter 3.47.2 and
Android cmdline-tools, fingerprint-pinned Temurin 17 apt key. All
mobile/gazer builds/lints/tests/scans now run through make mobile-*
targets inside gazer-toolchain:3.47.2 -- never on the host.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
COMMIT_EOF
)"
```

### Task 2: Flutter project scaffold and pins

**Files:**
- Create (via `flutter create`, then edited/overwritten as noted below): `mobile/gazer/.flutter-version`, `mobile/gazer/pubspec.yaml`, `mobile/gazer/pubspec.lock`, `mobile/gazer/analysis_options.yaml`, `mobile/gazer/l10n.yaml`, `mobile/gazer/lib/l10n/app_en.arb`, `mobile/gazer/test/widget_test.dart`, `mobile/gazer/android/gradle/libs.versions.toml`, `mobile/gazer/android/settings.gradle.kts`, `mobile/gazer/android/build.gradle.kts`, `mobile/gazer/android/app/build.gradle.kts`, `mobile/gazer/android/gradle.properties`, `mobile/gazer/android/gradle/wrapper/gradle-wrapper.properties`
- Create: `mobile/gazer/lib/config/flag_keys.dart` (the ONLY task that creates this file — B's Task 9 imports it, never recreates it), `mobile/gazer/test/config/flag_keys_test.dart`, `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/BuildInfo.kt`, `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/BuildInfoTest.kt` — exist solely so the `test` and `android-unit` CI coverage gates (Task 3) have a non-zero denominator to measure the first time CI runs, instead of a documented "expected red" (see Task 3)
- Left as generated by `flutter create` (untouched by this task — later tasks own them): `mobile/gazer/lib/main.dart` (stock counter demo; replaced wholesale by Task 13), `mobile/gazer/README.md` (replaced by Task 26), `mobile/gazer/android/app/src/main/AndroidManifest.xml` and `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/MainActivity.kt` (extended by Tasks 17/20), `mobile/gazer/android/app/src/main/res/**` (launcher icons/themes)
- Confirmed absent: `mobile/gazer/ios/` (never generated — `flutter create` was passed `--platforms android`)
- Modify: `.gitignore` (repo root)
- Test: `mobile/gazer/test/widget_test.dart` (the smoke test itself is both the deliverable and its own test)

**Interfaces:**
- Consumes: `gazer-toolchain:3.47.2` image and `mobile-*` make targets from Task 1.
- Produces: a `flutter pub get`-clean Dart package with every dependency pin from the spec; an Android Gradle project whose `gradle/libs.versions.toml` is the single source of version truth for JUnit5/MockK/JaCoCo/ktlint/RootEncoder/androidx-test/kotlinx-coroutines/junit4 that Tasks 17-20 (Kotlin) and Task 6 (Pigeon codegen) depend on (every alias any later task references is defined here — later tasks only ever verify or consume, never redeclare); `test/widget_test.dart` proves the toolchain can run a Dart test end-to-end before any real business logic exists; `class FlagKeys` (Dart, `lib/config/flag_keys.dart`) and `object BuildInfo` (Kotlin, `BuildInfo.kt`), each with a passing test, so `make mobile-test`'s lcov gate and `make mobile-test-android`'s JaCoCo gate both see a non-zero denominator the first time Task 3's CI runs.

- [ ] **Step 1: Confirm no Flutter project exists yet (failing check)**

Run: `test -f mobile/gazer/pubspec.yaml && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Run `flutter create` inside the toolchain container**

Run:
```bash
make mobile-run CMD="flutter create --org io.waddlebot --project-name gazer --platforms android --android-language kotlin ."
```
Expected: output ending in `Wrote N files.` (exit 0). `mobile/gazer/Dockerfile`, `.dockerignore`, and `scripts/` from Task 1 are untouched — `flutter create` only adds Flutter/Android scaffolding alongside them.

Verify:
```bash
test -d mobile/gazer/android && echo "OK: android/ created"
test ! -d mobile/gazer/ios && echo "OK: no ios/ (--platforms android)"
```
Expected: both `OK:` lines.

- [ ] **Step 3: Resolve the flutter_libs commit SHA and the epoch build number, then write `pubspec.yaml`**

```bash
set -euo pipefail
FLUTTER_LIBS_SHA=$(git ls-remote https://github.com/penguintechinc/penguin-libs.git HEAD | awk '{print $1}')
if [ -z "${FLUTTER_LIBS_SHA}" ]; then
  echo "git ls-remote returned nothing -- STOP, cannot pin flutter_libs" >&2
  exit 1
fi
echo "flutter_libs HEAD: ${FLUTTER_LIBS_SHA}"
EPOCH_BUILD=$(date +%s)
echo "build number: ${EPOCH_BUILD}"

cat > mobile/gazer/pubspec.yaml <<'PUBSPEC_EOF'
name: gazer
description: "Gazer -- live-streaming client for phones and tablets: phone camera or USB UVC capture card to any RTMP/RTMPS endpoint."
publish_to: 'none'
# X.Y.Z stays pre-1.0 through M1-M3; M4 cuts the first gazer-v1.0.0 tag
# (see spec Milestones M4). B is the epoch build number per the house
# versioning skill -- resolved by this step, not hand-edited later.
version: 0.1.0+__EPOCH_BUILD__

environment:
  sdk: '>=3.13.2 <3.14.0'
  flutter: '3.47.2'

dependencies:
  flutter:
    sdk: flutter
  flutter_localizations:
    sdk: flutter

  flutter_riverpod: 3.4.3
  riverpod_annotation: 4.0.7
  go_router: 18.0.1
  freezed_annotation: 3.1.0
  json_annotation: 4.12.0
  flutter_secure_storage: 11.0.0
  shared_preferences: 2.5.5
  connectivity_plus: 7.3.1
  intl: 0.20.3
  package_info_plus: 10.2.1
  dio: 5.11.1
  url_launcher: 6.3.2
  permission_handler: 13.0.2
  device_info_plus: 13.2.0
  crypto: 3.0.7
  flutter_libs:
    git:
      url: https://github.com/penguintechinc/penguin-libs.git
      path: packages/flutter_libs
      ref: __FLUTTER_LIBS_GIT_SHA__

dev_dependencies:
  flutter_test:
    sdk: flutter
  integration_test:
    sdk: flutter

  pigeon: 28.0.0
  riverpod_generator: 4.0.9
  freezed: 4.0.1
  json_serializable: 6.14.1
  build_runner: 2.16.1
  mocktail: 1.0.5
  flutter_lints: 6.0.0

flutter:
  uses-material-design: true
  generate: true
PUBSPEC_EOF

sed -i "s/__EPOCH_BUILD__/${EPOCH_BUILD}/" mobile/gazer/pubspec.yaml
sed -i "s/__FLUTTER_LIBS_GIT_SHA__/${FLUTTER_LIBS_SHA}/" mobile/gazer/pubspec.yaml
if grep -qE '__EPOCH_BUILD__|__FLUTTER_LIBS_GIT_SHA__' mobile/gazer/pubspec.yaml; then echo "sentinel left unresolved" >&2; exit 1; fi
grep -E '^version:|ref:' mobile/gazer/pubspec.yaml

echo "3.47.2" > mobile/gazer/.flutter-version
```
Expected: the final `grep` prints `version: 0.1.0+<10-digit epoch>` and `      ref: <40-hex-char sha>`, with no `__..__` sentinels anywhere in the file.

If a later `flutter pub get` (Step 12) reports `freezed_annotation: 3.1.0` is incompatible with `freezed: 4.0.1`, or that `intl: 0.20.3` doesn't match the `flutter_localizations` SDK constraint for Flutter 3.47.2: do not fight the solver. Pin whichever version `flutter pub get` actually resolves to instead, add a one-line comment above that pin recording the resolved version and the date, and re-run Step 12. Never loosen a pin to `^`/`~` to make the conflict go away.

- [ ] **Step 4: Write `analysis_options.yaml`**

```bash
cat > mobile/gazer/analysis_options.yaml <<'ANALYSIS_EOF'
include: package:flutter_lints/flutter.yaml

analyzer:
  language:
    strict-casts: true
    strict-inference: true
    strict-raw-types: true
  exclude:
    - "**/*.g.dart"
    - "**/*.freezed.dart"
    - "lib/pigeon/pipeline.g.dart"
    - "test/pigeon/pipeline_test.g.dart"

linter:
  rules:
    prefer_const_constructors: true
    avoid_print: true
    prefer_single_quotes: true
    use_build_context_synchronously: true
ANALYSIS_EOF
```
Run: `test -f mobile/gazer/analysis_options.yaml && echo OK`
Expected: `OK`

- [ ] **Step 5: Write `l10n.yaml` and the seed `app_en.arb`**

```bash
mkdir -p mobile/gazer/lib/l10n

cat > mobile/gazer/l10n.yaml <<'L10N_EOF'
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
output-class: AppLocalizations
nullable-getter: false
synthetic-package: false
L10N_EOF

cat > mobile/gazer/lib/l10n/app_en.arb <<'ARB_EOF'
{
  "@@locale": "en",
  "appTitle": "Gazer",
  "@appTitle": {
    "description": "The application title shown in the OS task switcher and app drawer."
  }
}
ARB_EOF
```
Run: `test -f mobile/gazer/l10n.yaml && test -f mobile/gazer/lib/l10n/app_en.arb && echo OK`
Expected: `OK`

- [ ] **Step 6: Replace the generated widget test with the M1 smoke test**

The app itself (`GazerApp`, `lib/main.dart`, `lib/app.dart`) doesn't exist until Task 13 — this smoke test intentionally never imports `package:gazer/main.dart` so Task 2's own verification doesn't depend on unwritten app code.

`mobile/gazer/test/widget_test.dart`:
```dart
// Task 2 toolchain smoke test: proves flutter test runs end-to-end inside
// the gazer-toolchain container before any app code exists. Task 13
// replaces lib/main.dart with GazerApp; this test deliberately never
// imports it, so it keeps passing unmodified through that rewrite.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('smoke: MaterialApp renders content', (WidgetTester tester) async {
    await tester.pumpWidget(const MaterialApp(home: Text('gazer')));

    expect(find.text('gazer'), findsOneWidget);
  });
}
```

- [ ] **Step 7: Write the Gradle version catalog `android/gradle/libs.versions.toml`**

```toml
# Gradle version catalog for mobile/gazer/android.
# Every [versions] entry not fixed by the spec (AGP/Kotlin/RootEncoder) was
# looked up via WebFetch/curl against Maven Central, the Gradle Plugin
# Portal, or Google's Maven, and is dated. Re-check dated entries before
# bumping them -- see docs/superpowers/specs/2026-09-07-gazer-mobile-v2-design.md
# Dependencies & Pins.
[versions]
agp = "9.1.0"                     # spec pin: Dependencies & Pins > Android/Gradle
kotlin = "2.4.0"                  # spec pin
ktlintGradle = "14.2.0"           # checked 2026-09-07: https://plugins.gradle.org/plugin/org.jlleitschuh.gradle.ktlint (latest published)
jacoco = "0.8.13"                 # checked 2026-09-07: https://search.maven.org/solrsearch/select?q=g:%22org.jacoco%22+AND+a:%22org.jacoco.core%22&rows=1&wt=json (latestVersion)
junitJupiter = "5.12.2"           # checked 2026-09-07: Maven Central core=gav listing for org.junit.jupiter:junit-jupiter -- latest true GA; 5.13.0-M1/M2/M3 are pre-release milestones and are never pinned here
junitPlatformLauncher = "1.12.2"  # JUnit Platform version paired to Jupiter 5.12.2 (Platform 1.x tracks Jupiter 5.x on matching minor.patch)
mockk = "1.14.3"                  # checked 2026-09-07: https://search.maven.org/solrsearch/select?q=g:%22io.mockk%22+AND+a:%22mockk%22&rows=1&wt=json (latestVersion)
androidxTestRunner = "1.7.0"      # checked 2026-09-07: https://dl.google.com/dl/android/maven2/androidx/test/runner/maven-metadata.xml (release)
androidxTestExtJunit = "1.3.0"    # checked 2026-09-07: https://dl.google.com/dl/android/maven2/androidx/test/ext/junit/maven-metadata.xml (release)
androidxTestRules = "1.7.0"       # checked 2026-09-07: https://dl.google.com/dl/android/maven2/androidx/test/rules/maven-metadata.xml (release)
junit4 = "4.13.2"                 # checked 2026-09-07: search.maven.org g:junit a:junit (latestVersion) -- JUnit4 is required alongside JUnit5 because
                                   # androidx.test's AndroidJUnitRunner (androidTest, Task 20) is JUnit4-based; JUnit5/Jupiter above is for JVM unit tests only
rootEncoder = "2.8.1"             # spec pin (JitPack, `library` module ONLY -- never `extra-sources`, see Global Constraints)
kotlinxCoroutines = "1.10.2"      # checked 2026-09-07: search.maven.org g:org.jetbrains.kotlinx a:kotlinx-coroutines-core (latestVersion) -- required
                                   # because Pigeon 28.0.0 generates `suspend fun` (not callback-style) for @FlutterApi methods and @async @HostApi
                                   # methods by default (see Task 6/Task 20); both the Pigeon-generated Pipeline.g.kt and PigeonHostApiImpl need it

[libraries]
rootencoder-library = { group = "com.github.pedroSG94.RootEncoder", name = "library", version.ref = "rootEncoder" }
junit-jupiter = { group = "org.junit.jupiter", name = "junit-jupiter", version.ref = "junitJupiter" }
junit-platform-launcher = { group = "org.junit.platform", name = "junit-platform-launcher", version.ref = "junitPlatformLauncher" }
mockk = { group = "io.mockk", name = "mockk", version.ref = "mockk" }
androidx-test-runner = { group = "androidx.test", name = "runner", version.ref = "androidxTestRunner" }
androidx-test-ext-junit = { group = "androidx.test.ext", name = "junit", version.ref = "androidxTestExtJunit" }
androidx-test-rules = { group = "androidx.test", name = "rules", version.ref = "androidxTestRules" }
junit4 = { group = "junit", name = "junit", version.ref = "junit4" }
kotlinx-coroutines-core = { group = "org.jetbrains.kotlinx", name = "kotlinx-coroutines-core", version.ref = "kotlinxCoroutines" }
kotlinx-coroutines-android = { group = "org.jetbrains.kotlinx", name = "kotlinx-coroutines-android", version.ref = "kotlinxCoroutines" }

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
ktlint = { id = "org.jlleitschuh.gradle.ktlint", version.ref = "ktlintGradle" }
```

- [ ] **Step 8: Overwrite `android/settings.gradle.kts`**

```kotlin
pluginManagement {
    val flutterSdkPath = run {
        val properties = java.util.Properties()
        file("local.properties").inputStream().use { properties.load(it) }
        val flutterSdkPath = properties.getProperty("flutter.sdk")
        require(flutterSdkPath != null) { "flutter.sdk not set in local.properties" }
        flutterSdkPath
    }
    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "9.1.0" apply false        // keep in sync with gradle/libs.versions.toml [versions] agp
    id("org.jetbrains.kotlin.android") version "2.4.0" apply false    // keep in sync with gradle/libs.versions.toml [versions] kotlin
    id("org.jlleitschuh.gradle.ktlint") version "14.2.0" apply false  // keep in sync with gradle/libs.versions.toml [versions] ktlintGradle
}

include(":app")
```

- [ ] **Step 9: Overwrite `android/build.gradle.kts`**

```kotlin
allprojects {
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://jitpack.io") } // RootEncoder (com.github.pedroSG94.RootEncoder) is published via JitPack only
    }
}

val newBuildDir: Directory = rootProject.layout.buildDirectory.dir("../../build").get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
    project.evaluationDependsOn(":app")
}

tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
```

- [ ] **Step 10: Overwrite `android/app/build.gradle.kts`**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
    id("org.jlleitschuh.gradle.ktlint")
    jacoco
}

// If AGP 9.1.0 / Kotlin 2.4.0 rejects the `kotlinOptions {}` block below
// (renamed/removed in that exact combination), replace it with whatever
// DSL that release's migration notes specify (e.g.
// `kotlin { compilerOptions { jvmTarget.set(...) } }`) and record the
// change in this comment -- do not downgrade AGP/Kotlin to dodge it.

android {
    namespace = "io.waddlebot.gazer"
    compileSdk = 36
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "io.waddlebot.gazer"
        minSdk = 29
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
        debug {
            enableUnitTestCoverage = true
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}

flutter {
    source = "../.."
}

jacoco {
    toolVersion = libs.versions.jacoco.get()
}

dependencies {
    implementation(libs.rootencoder.library)
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
    testImplementation(libs.mockk)

    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.junit4)
}

tasks.withType<Test> {
    useJUnitPlatform()
}

// NOTE: android/build.gradle.kts (Step 9 above) redirects the *root* buildDir to
// mobile/gazer/build, so this module's normal Gradle outputs (compiled classes, .exec/.ec
// coverage data) land under mobile/gazer/build/app, not android/app/build. The JaCoCo XML/HTML
// *report* output below is deliberately pinned to `layout.projectDirectory` (NOT
// `layout.buildDirectory`, which is the redirected one) so it lands at the fixed, predictable
// path `android/app/build/reports/jacoco/jacocoTestReport/...` that `make mobile-test-android`
// (repo-root Makefile), `scripts/coverage_gate.sh`'s jacoco-mode default, the CI `android-unit`
// job (Task 3), and Task 17 Step 7's existence check all read from -- every one of those must
// keep agreeing with this exact path if it is ever changed here.
tasks.register<JacocoReport>("jacocoTestReport") {
    dependsOn("testDebugUnitTest")
    reports {
        xml.required.set(true)
        xml.outputLocation.set(layout.projectDirectory.file("build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml"))
        html.required.set(true)
        html.outputLocation.set(layout.projectDirectory.dir("build/reports/jacoco/jacocoTestReport/html"))
    }
    val fileFilter = listOf(
        "**/R.class", "**/R\$*.class", "**/BuildConfig.*", "**/Manifest*.*",
        "**/*Test*.*", "**/pigeon/**",
    )
    val debugTree = fileTree("${layout.buildDirectory.get()}/tmp/kotlin-classes/debug") {
        exclude(fileFilter)
    }
    val mainSrc = "${project.projectDir}/src/main/kotlin"
    sourceDirectories.setFrom(files(mainSrc))
    classDirectories.setFrom(files(debugTree))
    executionData.setFrom(fileTree(layout.buildDirectory.get()) {
        include("**/*.exec", "**/*.ec")
    })
}
```

- [ ] **Step 11: Overwrite `android/gradle.properties` and pin the Gradle wrapper to 9.3.1**

`mobile/gazer/android/gradle.properties`:
```properties
org.gradle.jvmargs=-Xmx4G -XX:MaxMetaspaceSize=2G -XX:+HeapDumpOnOutOfMemoryError
android.useAndroidX=true
android.enableJetifier=false
org.gradle.parallel=true
org.gradle.caching=true
kotlin.code.style=official
```

`mobile/gazer/android/gradle/wrapper/gradle-wrapper.properties` (checksum checked 2026-09-07 via `https://downloads.gradle.org/distributions/gradle-9.3.1-bin.zip.sha256`):
```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-9.3.1-bin.zip
distributionSha256Sum=b266d5ff6b90eada6dc3b20cb090e3731302e553a27c5d3e4df1f0d76beaff06
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

- [ ] **Step 12: Update the repo-root `.gitignore`**

`build/` (line 22) and `**/.gradle/` (line 196) already cover this app's build output and Gradle cache at any depth — only `.dart_tool/` and `coverage/` are genuinely new. Append:
```gitignore

# Gazer Mobile 2.0 (mobile/gazer) -- build/ and **/.gradle/ above already
# cover this app's build output and Gradle caches at any depth.
mobile/gazer/.dart_tool/
mobile/gazer/coverage/
mobile/gazer/android/local.properties
```
Run: `grep -c 'mobile/gazer/.dart_tool/' .gitignore`
Expected: `1`

- [ ] **Step 13: `flutter pub get` inside the container**

Run: `make mobile-run CMD="flutter pub get"`
Expected: exit 0, ending in `Got dependencies!` (or a version-solve failure — if so, apply the Step 3 contingency, edit `pubspec.yaml`, and re-run this step until it succeeds). Confirm the lockfile exists: `test -f mobile/gazer/pubspec.lock && echo OK`.

- [ ] **Step 14: Verify `make mobile-lint` passes**

Run: `make mobile-lint`
Expected: `flutter analyze` reports `No issues found!`, `dart format --set-exit-if-changed .` exits 0 (no diff), and (since `android/` now exists) `./gradlew ktlintCheck lint` completes with `BUILD SUCCESSFUL`. If Gradle fails to resolve a plugin/dependency, fix the root cause in the Gradle files written above (e.g. a stale catalog version) — never mask it by removing the `if [ -d android ]` guard's condition or skipping ktlint/lint.

- [ ] **Step 15: Verify the Dart toolchain runs the smoke test**

Run: `make mobile-run CMD="flutter test"`
Expected: `00:0X +1: All tests passed!`

Note: this deliberately runs bare `flutter test`, not the fully-gated `make mobile-test`. `make mobile-test`'s `scripts/coverage_gate.sh 90` correctly treats a zero-`SF:` lcov report as a **failure, not a pass** (Task 1 Step 7 proved this), and at this point in the plan `lib/` contains only the stock `flutter create` counter demo that this task's smoke test never imports — there is no application code for coverage to measure yet. `make mobile-test`'s coverage-gated form becomes meaningful starting Task 4, once `lib/models/` exists.

- [ ] **Step 16: Write `lib/config/flag_keys.dart` and its test**

This is the **only** place `FlagKeys` is created — the shared contract lists it in the file map
without assigning it to a numbered task, and Writer B's Task 9 needs it two tasks before its own
`lib/config/constants.dart` step, so it is created here instead of duplicated later. B's Task 9
only ever imports it. This file (and `BuildInfo.kt` in Step 17 below) exist so Task 3's `test` and
`android-unit` CI coverage gates measure real, passing, non-zero-denominator coverage the first
time CI runs, instead of a documented "expected red" until Tasks 4/17 land.

`mobile/gazer/lib/config/flag_keys.dart`:
```dart
/// Canonical PostHog feature-flag keys for Gazer, in `{product}.{feature-name}` form.
/// `FeatureFlags.isEnabled` is always called with one of these — never a raw string literal —
/// so a typo fails at compile time, not at runtime.
class FlagKeys {
  const FlagKeys._();

  /// Gates whether Go Live is allowed at all (phone camera -> RTMP).
  static const String cameraStream = 'waddlebot.gazer.camera-stream';

  /// Gates UVC capture-card sources (M2+; unused by M1 but reserved here so the
  /// flag key is defined once for the whole product lifetime).
  static const String uvcCapture = 'waddlebot.gazer.uvc-capture';

  /// Gates whether the encoder is allowed to lower bitrate on congestion.
  static const String adaptiveBitrate = 'waddlebot.gazer.adaptive-bitrate';

  /// Gates whether username/password are ever sent to the RTMP endpoint.
  static const String rtmpAuth = 'waddlebot.gazer.rtmp-auth';

  /// Every known flag key, for validation and for tests that assert the full set.
  static const List<String> all = <String>[cameraStream, uvcCapture, adaptiveBitrate, rtmpAuth];
}
```

`mobile/gazer/test/config/flag_keys_test.dart`:
```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/config/flag_keys.dart';

void main() {
  test('flag keys match the PostHog {product}.{feature-name} convention', () {
    expect(FlagKeys.cameraStream, 'waddlebot.gazer.camera-stream');
    expect(FlagKeys.uvcCapture, 'waddlebot.gazer.uvc-capture');
    expect(FlagKeys.adaptiveBitrate, 'waddlebot.gazer.adaptive-bitrate');
    expect(FlagKeys.rtmpAuth, 'waddlebot.gazer.rtmp-auth');
  });

  test('all lists every flag key exactly once', () {
    expect(FlagKeys.all.length, 4);
    expect(FlagKeys.all.toSet().length, 4);
  });
}
```
Run: `make mobile-run CMD="flutter test test/config/flag_keys_test.dart"`
Expected: `00:0X +2: All tests passed!`

- [ ] **Step 17: Write `BuildInfo.kt` and its JUnit5 test**

`mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/BuildInfo.kt`:
```kotlin
package io.waddlebot.gazer

/**
 * Static build identity for this app. Exists (beyond Gradle's own `applicationId`) so a plain
 * JVM unit test can assert on the application id without parsing the manifest, giving the
 * `android-unit` JaCoCo gate a real, non-zero-denominator class to measure from Task 2 onward —
 * every later Kotlin file in Tasks 17-20 adds to this same gate, never replaces it.
 */
object BuildInfo {
    /** The application id declared in `android/app/build.gradle.kts`'s `defaultConfig`. */
    const val APPLICATION_ID = "io.waddlebot.gazer"

    /** Human-readable one-line identity string, e.g. for logs. */
    fun describe(): String = APPLICATION_ID
}
```

`mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/BuildInfoTest.kt`:
```kotlin
package io.waddlebot.gazer

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/** Trivial coverage-anchor test for [BuildInfo] — see the class doc for why it exists. */
class BuildInfoTest {

    @Test
    fun `application id matches the Gradle applicationId`() {
        assertEquals("io.waddlebot.gazer", BuildInfo.APPLICATION_ID)
    }

    @Test
    fun `describe returns the application id`() {
        assertEquals("io.waddlebot.gazer", BuildInfo.describe())
    }
}
```
Run: `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.BuildInfoTest'"`
Expected: `BUILD SUCCESSFUL`, `2 tests completed, 0 failed`.

- [ ] **Step 18: Verify both coverage gates now see a non-zero denominator**

Run: `make mobile-test`
Expected: `scripts/coverage_gate.sh` reports at least 2 files examined (the widget smoke test plus
`flag_keys.dart` via `flag_keys_test.dart`) and passes at 90%+ (both files are fully exercised by
their tests).

Run: `make mobile-test-android`
Expected: `scripts/coverage_gate.sh` reports a non-zero jacoco LINE counter total (from `BuildInfo`)
and passes at 90%+.

- [ ] **Step 19: Commit**

```bash
git add mobile/gazer/.flutter-version mobile/gazer/pubspec.yaml mobile/gazer/pubspec.lock \
  mobile/gazer/analysis_options.yaml mobile/gazer/l10n.yaml mobile/gazer/lib/l10n/app_en.arb \
  mobile/gazer/test/widget_test.dart mobile/gazer/android/gradle/libs.versions.toml \
  mobile/gazer/android/settings.gradle.kts mobile/gazer/android/build.gradle.kts \
  mobile/gazer/android/app/build.gradle.kts mobile/gazer/android/gradle.properties \
  mobile/gazer/android/gradle/wrapper/gradle-wrapper.properties \
  mobile/gazer/lib mobile/gazer/android mobile/gazer/test mobile/gazer/README.md \
  mobile/gazer/.metadata .gitignore
git commit -m "$(cat <<'COMMIT_EOF'
feat(gazer): scaffold Flutter project and pin every M1 dependency

flutter create --platforms android --android-language kotlin, then
pinned every pub.dev and Gradle dependency to the exact versions from
the design spec (no ^/~), added a Gradle version catalog recording
where each looked-up version came from, a toolchain smoke test that
passes before any application code exists, and FlagKeys/BuildInfo so
Task 3's coverage gates measure real code from their first CI run
instead of a documented zero-denominator red.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
COMMIT_EOF
)"
```

### Task 3: CI workflow

**Files:**
- Create: `.github/workflows/gazer-mobile.yml` (repo root)
- Test: none (a workflow file's "test" is `zizmor` static analysis plus an actual GitHub Actions run, both performed as steps below)

**Interfaces:**
- Consumes: `mobile/gazer/Dockerfile` (Task 1), `mobile/gazer/scripts/coverage_gate.sh` (Task 1), `mobile/gazer/pubspec.yaml`/`pubspec.lock` (Task 2), the Gradle project (Task 2). Does **not** consume anything from Tasks 4+ — those land after this task in plan order.
- Produces: `.github/workflows/gazer-mobile.yml` with jobs `toolchain`, `analyze`, `test`, `android-unit`, `build`, `security`, `release` — the exact job set and names every later task's own CI expectations (and writer E's Task 21 `integration` job addition) are written against. Does **not** add an `integration` job — writer E adds that in Task 21.

- [ ] **Step 1: Confirm the workflow doesn't exist yet (failing check)**

Run: `test -f .github/workflows/gazer-mobile.yml && echo EXISTS || echo MISSING`
Expected: `MISSING`

- [ ] **Step 2: Write `.github/workflows/gazer-mobile.yml`**

```yaml
name: Gazer Mobile CI

on:
  push:
    paths:
      - 'mobile/gazer/**'
      - 'Makefile'
      - '.github/workflows/gazer-mobile.yml'
  pull_request:
    paths:
      - 'mobile/gazer/**'
      - 'Makefile'
      - '.github/workflows/gazer-mobile.yml'

concurrency:
  group: gazer-mobile-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

permissions: {}

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: penguintechinc/waddlebot/gazer-toolchain

jobs:
  toolchain:
    name: Build toolchain image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      image: ${{ steps.resolve.outputs.image }}
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: Compute Dockerfile content tag
        id: tag
        run: |
          set -euo pipefail
          DIGEST=$(sha256sum mobile/gazer/Dockerfile | cut -c1-12)
          echo "tag=${DIGEST}" >> "$GITHUB_OUTPUT"

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@37fe631027851001ddb9b187196cc803df7f5f0e  # v4.3.0

      - name: Log in to GHCR
        uses: docker/login-action@dbcb813823bdd20940b903addbd779551569679f  # v4.6.0
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Check whether this image already exists
        id: check
        run: |
          set -euo pipefail
          IMAGE="${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.tag.outputs.tag }}"
          if docker manifest inspect "${IMAGE}" > /dev/null 2>&1; then
            echo "exists=true" >> "$GITHUB_OUTPUT"
          else
            echo "exists=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Build and push toolchain image
        if: steps.check.outputs.exists == 'false'
        uses: docker/build-push-action@53b7df96c91f9c12dcc8a07bcb9ccacbed38856a  # v7.3.0
        with:
          context: mobile/gazer
          file: mobile/gazer/Dockerfile
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.tag.outputs.tag }}

      - name: Resolve image ref for downstream jobs
        id: resolve
        run: |
          echo "image=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.tag.outputs.tag }}" >> "$GITHUB_OUTPUT"

  analyze:
    name: Dart analyze
    needs: toolchain
    runs-on: ubuntu-latest
    permissions:
      contents: read
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: flutter pub get
        working-directory: mobile/gazer
        run: flutter pub get

      - name: flutter analyze
        working-directory: mobile/gazer
        run: flutter analyze

      - name: dart format check
        working-directory: mobile/gazer
        run: dart format --set-exit-if-changed .

  test:
    name: Dart unit tests + coverage gate
    needs: toolchain
    runs-on: ubuntu-latest
    permissions:
      contents: read
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: flutter pub get
        working-directory: mobile/gazer
        run: flutter pub get

      - name: flutter test --coverage
        working-directory: mobile/gazer
        run: flutter test --coverage

      - name: Coverage gate (>=90%)
        working-directory: mobile/gazer
        run: bash scripts/coverage_gate.sh 90 coverage/lcov.info lcov

      - name: Upload coverage artifact
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-dart-coverage
          path: mobile/gazer/coverage/

  android-unit:
    name: Kotlin unit tests + JaCoCo gate
    needs: toolchain
    runs-on: ubuntu-latest
    permissions:
      contents: read
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: flutter pub get
        working-directory: mobile/gazer
        run: flutter pub get

      - name: gradlew testDebugUnitTest jacocoTestReport
        working-directory: mobile/gazer/android
        run: ./gradlew testDebugUnitTest jacocoTestReport

      - name: Coverage gate (>=90%)
        working-directory: mobile/gazer
        run: bash scripts/coverage_gate.sh 90 android/app/build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml jacoco

      - name: Upload JaCoCo artifact
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-android-coverage
          path: mobile/gazer/android/app/build/reports/jacoco/

  build:
    name: Build APK + AAB
    needs: toolchain
    runs-on: ubuntu-latest
    permissions:
      contents: read
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: flutter pub get
        working-directory: mobile/gazer
        run: flutter pub get

      - name: flutter build apk --split-per-abi
        working-directory: mobile/gazer
        run: flutter build apk --split-per-abi --obfuscate --split-debug-info=build/symbols

      - name: flutter build appbundle
        working-directory: mobile/gazer
        run: flutter build appbundle --obfuscate --split-debug-info=build/symbols

      - name: Upload APKs
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-apk
          path: mobile/gazer/build/app/outputs/apk/**/*.apk
          retention-days: 30

      - name: Upload AAB
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-aab
          path: mobile/gazer/build/app/outputs/bundle/**/*.aab
          retention-days: 30

  security:
    name: Security scans
    needs: toolchain
    runs-on: ubuntu-latest
    permissions:
      contents: read
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: flutter pub get
        working-directory: mobile/gazer
        run: flutter pub get

      - name: osv-scanner (pubspec.lock)
        working-directory: mobile/gazer
        run: osv-scanner --lockfile=pubspec.lock

      - name: osv-scanner (gradle project)
        working-directory: mobile/gazer/android
        run: osv-scanner -r .

      - name: semgrep
        working-directory: mobile/gazer
        run: semgrep --config auto --error .

      - name: gitleaks
        working-directory: mobile/gazer
        run: gitleaks detect --source . --no-git -v

  # NOTE for writer E's Task 21: once the `integration` job exists (added after `security`, per
  # Task 21 Step 15), this job's `needs:` list below MUST be extended to
  # `[build, test, android-unit, security, integration]` in that same task -- otherwise a tag
  # push creates a GitHub release without ever waiting for the emulator integration test to pass.
  # Not added here because `integration` does not exist yet at this point in the plan (Task 3
  # predates Task 21) -- a `needs:` reference to a job that doesn't exist yet would be an invalid
  # workflow.
  release:
    name: GitHub Release
    needs: [build, test, android-unit, security]
    if: startsWith(github.ref, 'refs/tags/gazer-v')
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: Download APK artifact
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8
        with:
          name: gazer-apk
          path: release-artifacts

      - name: Download AAB artifact
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8
        with:
          name: gazer-aab
          path: release-artifacts

      - name: Create GitHub Release
        uses: softprops/action-gh-release@b4309332981a82ec1c5618f44dd2e27cc8bfbfda  # v3
        with:
          files: release-artifacts/**/*
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

Note on job graph: `analyze`, `test`, `android-unit`, `build`, and `security` each depend only on `toolchain` and run in parallel (per the spec's `toolchain → analyze, test, android-unit, build, security` ordering) — `build` does **not** wait on `test`/`android-unit`, which matters for Step 6 below. `release` (tag-gated, not exercised by this task) is the one job that waits on all four verification jobs plus `build`.

- [ ] **Step 3: Run zizmor locally before committing**

```bash
uvx zizmor==1.30.0 .github/workflows/gazer-mobile.yml
```
(fallback if `uv`/`uvx` isn't on the host: `pipx run zizmor==1.30.0 .github/workflows/gazer-mobile.yml`)
Expected: no `error`-level findings. zizmor commonly flags overly-broad `permissions:` or unpinned `uses:` — this workflow already sets `permissions: {}` at the top with per-job grants and pins every `uses:` to a full commit SHA, so a clean run is expected. If zizmor reports a real finding (e.g. a job permission broader than it needs), fix the workflow and re-run this step until clean — do not suppress or ignore its output.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/gazer-mobile.yml
git commit -m "$(cat <<'COMMIT_EOF'
ci(gazer): add gazer-mobile.yml CI workflow

toolchain -> analyze, test, android-unit, build, security (parallel),
release (tag gazer-v* only). Toolchain image tagged by Dockerfile
content hash and reused across runs via docker manifest inspect.
Every uses: pinned to a full commit SHA; zizmor-clean.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
COMMIT_EOF
)"
```

- [ ] **Step 5: Push and watch the run**

```bash
git push -u origin HEAD
gh run watch "$(gh run list --workflow gazer-mobile.yml --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
```
(backup push to this short-lived branch is pre-authorized per `devops.md` Branch Backups — this is not a merge or PR action)

- [ ] **Step 6: Confirm status and act on it honestly**

Run: `gh run list --workflow gazer-mobile.yml --limit 1`

Expected at **this point in the plan** (Tasks 4-20 have not run yet): every job — `toolchain`,
`analyze`, `test`, `android-unit`, `build`, `security` — is **GREEN**. `test` and `android-unit`
are not expected to fail: Task 2 Steps 16-17 already added `lib/config/flag_keys.dart` (+
`test/config/flag_keys_test.dart`) and `BuildInfo.kt` (+ `BuildInfoTest.kt`) specifically so both
coverage gates have real, fully-covered, non-zero-denominator code to measure from this first CI
run onward — there is no "expected red" window in this plan. `test`/`android-unit`'s coverage
percentage will simply be 100% (or very close to it) until Task 4/Task 17 add more code to cover.

**If red:** treat it as a real defect and fix it, the same as any other job. A `test`/`android-unit`
failure at the "Coverage gate (>=90%)" step now means either Step 16/17's files or tests are
missing/broken, or `scripts/coverage_gate.sh` regressed — not an accepted, self-documenting state.
A failure anywhere else (`flutter pub get`, `flutter test --coverage`, `gradlew testDebugUnitTest`
itself) is likewise a workflow or scaffold defect. Never mask any of this with `|| true`, a lowered
threshold, or a skipped step — fix the root cause before considering Task 3 done.


# Part B — Tasks 4-12: Dart Core (Writer B)

> Continuation of the Gazer Mobile 2.0 M1 Implementation Plan. This part assumes Tasks 1-3
> (toolchain container, `make mobile-*` targets, Flutter scaffold with all pubspec pins,
> Android Gradle project) are complete and committed. All commands below run from the repo
> root via `make` targets, which execute inside the `gazer-toolchain:3.47.2` container.

**Two deliberate resolutions of ordering gaps left open by the shared contract (both explained
in-line at the task that first hits them):**

1. **`GazerErrorCode` forward reference (Task 4 vs Task 6).** The contract defines
   `GazerErrorCode` only inside `pigeons/pipeline.dart` (Task 6), but `GazerError`/`PipelineState`
   (Task 4) need it two tasks earlier. Task 4 hand-writes a temporary `GazerErrorCode` enum with
   the exact 13 members in `lib/models/pipeline_state.dart`; Task 6, once the Pigeon-generated
   enum exists, deletes the temporary copy and imports the canonical one. One enum exists at any
   commit; both commits compile and pass tests.
2. **`PipelineController.goLive`'s flag-gating params.** The contract's literal quoted signature
   for `goLive` doesn't list a `FeatureFlags` parameter, yet its own prose two lines later requires
   flag-gated behavior (adaptive bitrate, RTMP auth) that only a caller-supplied `FeatureFlags` can
   drive — the same way the contract's prose adds `orientation` on top of the literal quoted
   signature. Task 11 adds `required FeatureFlags flags` alongside `orientation`, following the
   contract's own pattern of amending the quoted signature in prose rather than inventing an
   unrelated name.

`lib/config/constants.dart` is not owned by any numbered task in the writer breakdown but is
required by `kLicenseBaseUrl`/`kGithubReleasesUrl` referenced in the shared contract; Task 9
creates it, being the first task that needs `kLicenseBaseUrl`. `lib/config/flag_keys.dart` (the
`FlagKeys` class) is created by Task 2 instead (moved there by the A/D reconciliation pass so
coverage has a non-zero denominator from the very first task) — Task 9 only *consumes* it.

---

### Task 4: Domain models and enums

**Files:**
- Create: `lib/models/quality.dart`, `lib/models/stream_target_settings.dart`, `lib/models/gazer_settings.dart`, `lib/models/pipeline_state.dart`, `lib/models/stream_stats.dart`, `lib/models/license_state.dart`, `lib/models/update_info.dart`, `lib/models/validation_issue.dart`
- Test: `test/models/quality_test.dart`, `test/models/stream_target_settings_test.dart`, `test/models/gazer_settings_test.dart`, `test/models/pipeline_state_test.dart`, `test/models/stream_stats_test.dart`, `test/models/license_state_test.dart`, `test/models/update_info_test.dart`, `test/models/validation_issue_test.dart`

**Interfaces:**
- Produces: `Resolution`, `FrameRate`, `QualitySettings`, `StreamTargetSettings`, `AudioSourceChoice`, `GazerSettings`, `GazerErrorCode` (temporary, see header), `GazerError`, `PipelineState` + 8 subclasses, `StreamStats`, `LicenseStatus`, `LicenseState`, `UpdateInfo`, `ValidationIssue` — all exact signatures from the shared contract.
- Consumes: `package:freezed_annotation/freezed_annotation.dart` (freezed 4.0.1 / freezed_annotation pinned by Task 2), `dart:core` only otherwise.

This task has 8 independent TDD cycles (one per model file) sharing one final lint+commit. Every
cycle's codegen step uses `dart run build_runner build` directly, **not** the composite
`make mobile-codegen` — that target chains `dart run pigeon --input pigeons/pipeline.dart`
first, and `pigeons/pipeline.dart` does not exist until Task 6; running the composite target now
would fail before build_runner ever executes.

- [ ] **Step 1: Write failing test for `Resolution`/`FrameRate`/`QualitySettings`**

  `test/models/quality_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/quality.dart';

  void main() {
    group('Resolution', () {
      test('p540 has 960x540 dimensions and label', () {
        expect(Resolution.p540.width, 960);
        expect(Resolution.p540.height, 540);
        expect(Resolution.p540.label, '540p');
      });

      test('all five tiers expose correct width/height pairs', () {
        expect(Resolution.p180.width, 320);
        expect(Resolution.p180.height, 180);
        expect(Resolution.p360.width, 640);
        expect(Resolution.p360.height, 360);
        expect(Resolution.p720.width, 1280);
        expect(Resolution.p720.height, 720);
        expect(Resolution.p1080.width, 1920);
        expect(Resolution.p1080.height, 1080);
      });
    });

    group('FrameRate', () {
      test('exposes the four supported values', () {
        expect(FrameRate.fps15.value, 15);
        expect(FrameRate.fps30.value, 30);
        expect(FrameRate.fps50.value, 50);
        expect(FrameRate.fps60.value, 60);
      });
    });

    group('QualitySettings.defaults', () {
      test('is 540p/30fps/2000kbps/adaptive-on', () {
        final defaults = QualitySettings.defaults();
        expect(defaults.resolution, Resolution.p540);
        expect(defaults.frameRate, FrameRate.fps30);
        expect(defaults.videoBitrateKbps, 2000);
        expect(defaults.adaptiveBitrate, isTrue);
      });
    });

    group('QualitySettings JSON round-trip', () {
      test('toJson/fromJson preserves every field', () {
        const original = QualitySettings(
          resolution: Resolution.p1080,
          frameRate: FrameRate.fps60,
          videoBitrateKbps: 4500,
          adaptiveBitrate: false,
        );
        final restored = QualitySettings.fromJson(original.toJson());
        expect(restored, original);
      });
    });

    group('QualitySettings equality', () {
      test('two instances with identical fields are ==', () {
        const a = QualitySettings(
          resolution: Resolution.p720,
          frameRate: FrameRate.fps30,
          videoBitrateKbps: 2000,
          adaptiveBitrate: true,
        );
        const b = QualitySettings(
          resolution: Resolution.p720,
          frameRate: FrameRate.fps30,
          videoBitrateKbps: 2000,
          adaptiveBitrate: true,
        );
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing bitrate breaks equality', () {
        const a = QualitySettings(
          resolution: Resolution.p720,
          frameRate: FrameRate.fps30,
          videoBitrateKbps: 2000,
          adaptiveBitrate: true,
        );
        const b = QualitySettings(
          resolution: Resolution.p720,
          frameRate: FrameRate.fps30,
          videoBitrateKbps: 2500,
          adaptiveBitrate: true,
        );
        expect(a == b, isFalse);
      });
    });
  }
  ```

- [ ] **Step 2: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/quality_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/quality.dart': No such file or directory` (compile-time import error — the model file does not exist yet).

- [ ] **Step 3: Implement `lib/models/quality.dart`**

  ```dart
  import 'package:freezed_annotation/freezed_annotation.dart';

  part 'quality.freezed.dart';
  part 'quality.g.dart';

  /// Short-edge output resolution for the encoded video stream, paired with
  /// its pixel width/height at 16:9 and a compact UI label (e.g. "540p").
  enum Resolution {
    p180(320, 180),
    p360(640, 360),
    p540(960, 540),
    p720(1280, 720),
    p1080(1920, 1080);

    const Resolution(this.width, this.height);

    /// Encoded frame width in pixels for this resolution tier.
    final int width;

    /// Encoded frame height in pixels for this resolution tier.
    final int height;

    /// Short label shown in the resolution picker, e.g. "540p".
    String get label => '${height}p';
  }

  /// Target encoder frame rate in frames per second.
  enum FrameRate {
    fps15(15),
    fps30(30),
    fps50(50),
    fps60(60);

    const FrameRate(this.value);

    /// Frames per second value passed to the native encoder.
    final int value;
  }

  /// Minimum allowed video bitrate, in kbps, for the quality slider.
  const int kMinBitrateKbps = 500;

  /// Maximum allowed video bitrate, in kbps, for the quality slider.
  const int kMaxBitrateKbps = 5000;

  /// Step size, in kbps, between adjacent quality slider positions.
  const int kBitrateStepKbps = 100;

  /// Fixed AAC audio bitrate, in kbps, used for every stream in M1.
  const int kAudioBitrateKbps = 128;

  /// User-configurable video quality: resolution, frame rate, target bitrate
  /// and whether the encoder is allowed to adapt bitrate down on congestion.
  @freezed
  abstract class QualitySettings with _$QualitySettings {
    const factory QualitySettings({
      required Resolution resolution,
      required FrameRate frameRate,
      required int videoBitrateKbps,
      required bool adaptiveBitrate,
    }) = _QualitySettings;

    /// Deserializes a [QualitySettings] from JSON (round-trip tests only;
    /// [SecureSettingsRepository] persists these as separate scalar keys).
    factory QualitySettings.fromJson(Map<String, dynamic> json) =>
        _$QualitySettingsFromJson(json);

    /// House default: 540p @ 30fps, 2000 kbps, adaptive bitrate on.
    factory QualitySettings.defaults() => const QualitySettings(
          resolution: Resolution.p540,
          frameRate: FrameRate.fps30,
          videoBitrateKbps: 2000,
          adaptiveBitrate: true,
        );
  }
  ```

- [ ] **Step 4: Generate freezed/json_serializable code and run**

  `make mobile-run CMD="dart run build_runner build --delete-conflicting-outputs"`
  Expected: `lib/models/quality.freezed.dart` and `lib/models/quality.g.dart` created; output ends
  `Built with build_runner ...`, `[INFO] Succeeded after ...`.

  `make mobile-run CMD="flutter test test/models/quality_test.dart"`
  Expected PASS: `00:0X +9: All tests passed!`

- [ ] **Step 5: Write failing test for `StreamTargetSettings`**

  `test/models/stream_target_settings_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/stream_target_settings.dart';

  void main() {
    group('StreamTargetSettings.empty', () {
      test('has a blank url and no key or credentials', () {
        final empty = StreamTargetSettings.empty();
        expect(empty.url, isEmpty);
        expect(empty.streamKey, isNull);
        expect(empty.username, isNull);
        expect(empty.password, isNull);
      });
    });

    group('StreamTargetSettings JSON round-trip', () {
      test('toJson/fromJson preserves every field including credentials', () {
        const original = StreamTargetSettings(
          url: 'rtmps://ingest-b.example.com/app',
          streamKey: 'demo-key-0002',
          username: 'demo',
          password: 's3cret',
        );
        final restored = StreamTargetSettings.fromJson(original.toJson());
        expect(restored, original);
      });

      test('nullable fields round-trip as null', () {
        const original = StreamTargetSettings(url: 'rtmp://ingest-a.example.com/live');
        final restored = StreamTargetSettings.fromJson(original.toJson());
        expect(restored.streamKey, isNull);
        expect(restored.username, isNull);
        expect(restored.password, isNull);
      });
    });

    group('StreamTargetSettings equality', () {
      test('two instances with identical fields are ==', () {
        const a = StreamTargetSettings(url: 'rtmp://a.example.com/live', streamKey: 'k');
        const b = StreamTargetSettings(url: 'rtmp://a.example.com/live', streamKey: 'k');
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing url breaks equality', () {
        const a = StreamTargetSettings(url: 'rtmp://a.example.com/live');
        const b = StreamTargetSettings(url: 'rtmp://b.example.com/live');
        expect(a == b, isFalse);
      });
    });
  }
  ```

- [ ] **Step 6: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/stream_target_settings_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/stream_target_settings.dart': No such file or directory`.

- [ ] **Step 7: Implement `lib/models/stream_target_settings.dart`**

  ```dart
  import 'package:freezed_annotation/freezed_annotation.dart';

  part 'stream_target_settings.freezed.dart';
  part 'stream_target_settings.g.dart';

  /// User-supplied RTMP/RTMPS destination: URL, optional stream key, and an
  /// optional both-or-neither username/password pair.
  ///
  /// Every field here is sensitive: [SecureSettingsRepository] stores it in
  /// `flutter_secure_storage`, never `shared_preferences`, and it is never
  /// logged. Validation and the key-append/dedupe logic live in
  /// `TargetValidator`, not here.
  @freezed
  abstract class StreamTargetSettings with _$StreamTargetSettings {
    const factory StreamTargetSettings({
      required String url,
      String? streamKey,
      String? username,
      String? password,
    }) = _StreamTargetSettings;

    /// Deserializes a [StreamTargetSettings] from JSON (round-trip tests only).
    factory StreamTargetSettings.fromJson(Map<String, dynamic> json) =>
        _$StreamTargetSettingsFromJson(json);

    /// Empty target: blank URL, no key, no credentials — the pre-setup state.
    factory StreamTargetSettings.empty() => const StreamTargetSettings(url: '');
  }
  ```

- [ ] **Step 8: Generate and run**

  `make mobile-run CMD="dart run build_runner build --delete-conflicting-outputs"` → succeeds.
  `make mobile-run CMD="flutter test test/models/stream_target_settings_test.dart"` → PASS.

- [ ] **Step 9: Write failing test for `GazerSettings`/`AudioSourceChoice`**

  `test/models/gazer_settings_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/quality.dart';
  import 'package:gazer/models/stream_target_settings.dart';

  void main() {
    group('GazerSettings.defaults', () {
      test('is an empty target, default quality, auto audio, libuvc off', () {
        final defaults = GazerSettings.defaults();
        expect(defaults.target, StreamTargetSettings.empty());
        expect(defaults.quality, QualitySettings.defaults());
        expect(defaults.audio, AudioSourceChoice.auto);
        expect(defaults.forceLibuvc, isFalse);
      });
    });

    group('GazerSettings JSON round-trip', () {
      test('toJson/fromJson preserves nested target and quality', () {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            streamKey: 'demo-key-0001',
          ),
          quality: const QualitySettings(
            resolution: Resolution.p720,
            frameRate: FrameRate.fps60,
            videoBitrateKbps: 3000,
            adaptiveBitrate: false,
          ),
          audio: AudioSourceChoice.usbAudio,
          forceLibuvc: true,
        );
        final restored = GazerSettings.fromJson(original.toJson());
        expect(restored, original);
      });
    });

    group('GazerSettings equality', () {
      test('two instances with identical nested fields are ==', () {
        final a = GazerSettings.defaults();
        final b = GazerSettings.defaults();
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing audio choice breaks equality', () {
        final a = GazerSettings.defaults();
        final b = a.copyWith(audio: AudioSourceChoice.mic);
        expect(a == b, isFalse);
      });
    });

    group('AudioSourceChoice', () {
      test('has exactly the four supported values', () {
        expect(AudioSourceChoice.values, [
          AudioSourceChoice.auto,
          AudioSourceChoice.mic,
          AudioSourceChoice.usbAudio,
          AudioSourceChoice.silence,
        ]);
      });
    });
  }
  ```

- [ ] **Step 10: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/gazer_settings_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/gazer_settings.dart': No such file or directory`.

- [ ] **Step 11: Implement `lib/models/gazer_settings.dart`**

  ```dart
  import 'package:freezed_annotation/freezed_annotation.dart';

  import 'quality.dart';
  import 'stream_target_settings.dart';

  part 'gazer_settings.freezed.dart';
  part 'gazer_settings.g.dart';

  /// User's chosen audio source for the stream.
  ///
  /// `auto` resolves at Go Live time (M1: always mic, since M1 has no UVC/USB
  /// audio path); `usbAudio` is reserved for M2 and falls back to mic in M1.
  enum AudioSourceChoice { auto, mic, usbAudio, silence }

  /// The complete set of user-configurable Gazer settings: target, quality,
  /// audio source and the hidden developer "force libuvc" toggle.
  ///
  /// This is the aggregate root `SettingsRepository` loads/saves; persistence
  /// itself is split across secure storage (target) and shared_preferences
  /// (everything else) — see `SecureSettingsRepository`.
  @freezed
  abstract class GazerSettings with _$GazerSettings {
    const factory GazerSettings({
      required StreamTargetSettings target,
      required QualitySettings quality,
      required AudioSourceChoice audio,
      required bool forceLibuvc,
    }) = _GazerSettings;

    /// Deserializes a [GazerSettings] from JSON (round-trip tests only —
    /// [SecureSettingsRepository] persists fields individually, not as one blob).
    factory GazerSettings.fromJson(Map<String, dynamic> json) =>
        _$GazerSettingsFromJson(json);

    /// First-launch defaults: empty target, default quality, auto audio,
    /// developer toggle off.
    factory GazerSettings.defaults() => GazerSettings(
          target: StreamTargetSettings.empty(),
          quality: QualitySettings.defaults(),
          audio: AudioSourceChoice.auto,
          forceLibuvc: false,
        );
  }
  ```

- [ ] **Step 12: Generate and run**

  `make mobile-run CMD="dart run build_runner build --delete-conflicting-outputs"` → succeeds.
  `make mobile-run CMD="flutter test test/models/gazer_settings_test.dart"` → PASS.

- [ ] **Step 13: Write failing test for `PipelineState`/`GazerError`/`GazerErrorCode`**

  `test/models/pipeline_state_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/pipeline_state.dart';

  void main() {
    group('GazerErrorCode', () {
      test('exposes all thirteen native error codes', () {
        expect(GazerErrorCode.values, hasLength(13));
        expect(GazerErrorCode.values, contains(GazerErrorCode.usbPermissionDenied));
        expect(GazerErrorCode.values, contains(GazerErrorCode.uvcNoUsableFormat));
        expect(GazerErrorCode.values, contains(GazerErrorCode.uvcOpenFailed));
        expect(GazerErrorCode.values, contains(GazerErrorCode.cameraUnavailable));
        expect(GazerErrorCode.values, contains(GazerErrorCode.cameraInUse));
        expect(GazerErrorCode.values, contains(GazerErrorCode.encoderFailed));
        expect(GazerErrorCode.values, contains(GazerErrorCode.audioSourceFailed));
        expect(GazerErrorCode.values, contains(GazerErrorCode.rtmpAuthFailed));
        expect(GazerErrorCode.values, contains(GazerErrorCode.rtmpConnectFailed));
        expect(GazerErrorCode.values, contains(GazerErrorCode.rtmpDisconnected));
        expect(GazerErrorCode.values, contains(GazerErrorCode.usbDetached));
        expect(GazerErrorCode.values, contains(GazerErrorCode.serviceStartDenied));
        expect(GazerErrorCode.values, contains(GazerErrorCode.unknown));
      });
    });

    group('GazerError equality', () {
      test('same code and detail are equal', () {
        const a = GazerError(code: GazerErrorCode.rtmpConnectFailed, detail: 'timeout');
        const b = GazerError(code: GazerErrorCode.rtmpConnectFailed, detail: 'timeout');
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing detail breaks equality', () {
        const a = GazerError(code: GazerErrorCode.rtmpConnectFailed, detail: 'timeout');
        const b = GazerError(code: GazerErrorCode.rtmpConnectFailed, detail: 'refused');
        expect(a == b, isFalse);
      });
    });

    group('PipelineState subclasses', () {
      test('each stateless subclass equals another instance of itself', () {
        expect(const IdleState(), const IdleState());
        expect(const PreparingState(), const PreparingState());
        expect(const ReadyState(), const ReadyState());
        expect(const ConnectingState(), const ConnectingState());
        expect(const StreamingState(), const StreamingState());
        expect(const StoppingState(), const StoppingState());
      });

      test('IdleState is never equal to PreparingState', () {
        expect(const IdleState() == const PreparingState(), isFalse);
      });

      test('ReconnectingState compares by attempt and nextIn', () {
        const a = ReconnectingState(2, Duration(seconds: 4));
        const b = ReconnectingState(2, Duration(seconds: 4));
        const c = ReconnectingState(3, Duration(seconds: 4));
        expect(a, b);
        expect(a.hashCode, b.hashCode);
        expect(a == c, isFalse);
      });

      test('ErrorState compares by wrapped GazerError', () {
        const a = ErrorState(GazerError(code: GazerErrorCode.rtmpAuthFailed));
        const b = ErrorState(GazerError(code: GazerErrorCode.rtmpAuthFailed));
        const c = ErrorState(GazerError(code: GazerErrorCode.unknown));
        expect(a, b);
        expect(a == c, isFalse);
      });

      test('a switch expression over PipelineState is exhaustive', () {
        String describe(PipelineState s) => switch (s) {
              IdleState() => 'idle',
              PreparingState() => 'preparing',
              ReadyState() => 'ready',
              ConnectingState() => 'connecting',
              StreamingState() => 'streaming',
              ReconnectingState() => 'reconnecting',
              StoppingState() => 'stopping',
              ErrorState() => 'error',
            };
        expect(describe(const IdleState()), 'idle');
        expect(describe(const ErrorState(GazerError(code: GazerErrorCode.unknown))), 'error');
      });
    });
  }
  ```

- [ ] **Step 14: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/pipeline_state_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/pipeline_state.dart': No such file or directory`.

- [ ] **Step 15: Implement `lib/models/pipeline_state.dart`**

  ```dart
  /// Error codes reported by the native pipeline across the Pigeon boundary.
  ///
  /// TEMPORARY (Task 4 only): hand-written here so [GazerError] and
  /// [PipelineState] compile before Task 6 generates the canonical Pigeon
  /// enum. Task 6 replaces this declaration with an import of
  /// `package:gazer/pigeon/pipeline.g.dart`'s `GazerErrorCode` (same 13
  /// members, same order) and deletes this block — see Task 6 Step 5.
  enum GazerErrorCode {
    usbPermissionDenied,
    uvcNoUsableFormat,
    uvcOpenFailed,
    cameraUnavailable,
    cameraInUse,
    encoderFailed,
    audioSourceFailed,
    rtmpAuthFailed,
    rtmpConnectFailed,
    rtmpDisconnected,
    usbDetached,
    serviceStartDenied,
    unknown,
  }

  /// An error surfaced by the native pipeline, carried inside [ErrorState].
  ///
  /// Immutable value type: two [GazerError]s with the same [code] and
  /// [detail] compare equal so tests and UI can diff error states cheaply.
  class GazerError {
    const GazerError({required this.code, this.detail});

    /// Machine-readable error classification from the native pipeline.
    final GazerErrorCode code;

    /// Optional human-readable detail forwarded from the native layer
    /// (never contains secrets; native never includes URLs/credentials).
    final String? detail;

    @override
    bool operator ==(Object other) =>
        identical(this, other) ||
        (other is GazerError && other.code == code && other.detail == detail);

    @override
    int get hashCode => Object.hash(code, detail);

    @override
    String toString() => 'GazerError(code: $code, detail: $detail)';
  }

  /// Current state of the Gazer streaming pipeline.
  ///
  /// Mirrors the native `NativePipelineState` machine but adds the
  /// Dart-owned [ReconnectingState], which the native layer never emits —
  /// `PipelineController` synthesizes it while a reconnect backoff is
  /// in flight.
  sealed class PipelineState {
    const PipelineState();
  }

  /// No source prepared, not streaming; the resting state.
  class IdleState extends PipelineState {
    const IdleState();

    @override
    bool operator ==(Object other) => other is IdleState;

    @override
    int get hashCode => (IdleState).hashCode;

    @override
    String toString() => 'IdleState()';
  }

  /// Native pipeline is negotiating the video/audio source.
  class PreparingState extends PipelineState {
    const PreparingState();

    @override
    bool operator ==(Object other) => other is PreparingState;

    @override
    int get hashCode => (PreparingState).hashCode;

    @override
    String toString() => 'PreparingState()';
  }

  /// Source prepared successfully; not yet connecting to the RTMP endpoint.
  class ReadyState extends PipelineState {
    const ReadyState();

    @override
    bool operator ==(Object other) => other is ReadyState;

    @override
    int get hashCode => (ReadyState).hashCode;

    @override
    String toString() => 'ReadyState()';
  }

  /// TCP/RTMP handshake with the endpoint is in progress.
  class ConnectingState extends PipelineState {
    const ConnectingState();

    @override
    bool operator ==(Object other) => other is ConnectingState;

    @override
    int get hashCode => (ConnectingState).hashCode;

    @override
    String toString() => 'ConnectingState()';
  }

  /// Actively encoding and publishing to the RTMP endpoint.
  class StreamingState extends PipelineState {
    const StreamingState();

    @override
    bool operator ==(Object other) => other is StreamingState;

    @override
    int get hashCode => (StreamingState).hashCode;

    @override
    String toString() => 'StreamingState()';
  }

  /// Dart-owned backoff state: the connection dropped and
  /// `PipelineController` will retry after [nextIn].
  class ReconnectingState extends PipelineState {
    const ReconnectingState(this.attempt, this.nextIn);

    /// 1-based attempt number, matching `ReconnectPolicy.delayFor`.
    final int attempt;

    /// Time remaining before the next `start()` retry is issued.
    final Duration nextIn;

    @override
    bool operator ==(Object other) =>
        other is ReconnectingState && other.attempt == attempt && other.nextIn == nextIn;

    @override
    int get hashCode => Object.hash(attempt, nextIn);

    @override
    String toString() => 'ReconnectingState(attempt: $attempt, nextIn: $nextIn)';
  }

  /// User (or the controller) requested stop; native teardown in progress.
  class StoppingState extends PipelineState {
    const StoppingState();

    @override
    bool operator ==(Object other) => other is StoppingState;

    @override
    int get hashCode => (StoppingState).hashCode;

    @override
    String toString() => 'StoppingState()';
  }

  /// Terminal (until the user retries manually) error state.
  class ErrorState extends PipelineState {
    const ErrorState(this.error);

    /// The error that caused the pipeline to stop retrying automatically.
    final GazerError error;

    @override
    bool operator ==(Object other) => other is ErrorState && other.error == error;

    @override
    int get hashCode => error.hashCode;

    @override
    String toString() => 'ErrorState(error: $error)';
  }
  ```

- [ ] **Step 16: Run and confirm pass**

  `make mobile-run CMD="flutter test test/models/pipeline_state_test.dart"` → PASS (no codegen
  needed — this file is hand-written, not freezed).

- [ ] **Step 17: Write failing test for `StreamStats`**

  `test/models/stream_stats_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/stream_stats.dart';

  void main() {
    group('StreamStats.zero', () {
      test('is the all-zero snapshot', () {
        const zero = StreamStats(
          currentBitrateKbps: 0,
          averageBitrateKbps: 0,
          fps: 0,
          droppedFrames: 0,
          sentBytes: 0,
          uptime: Duration.zero,
          reconnectCount: 0,
          congestionPercent: 0,
        );
        expect(StreamStats.zero(), zero);
      });
    });

    group('StreamStats equality', () {
      test('two instances with identical fields are ==', () {
        const a = StreamStats(
          currentBitrateKbps: 2000,
          averageBitrateKbps: 1900,
          fps: 29.5,
          droppedFrames: 3,
          sentBytes: 123456,
          uptime: Duration(seconds: 62),
          reconnectCount: 1,
          congestionPercent: 12.5,
        );
        const b = StreamStats(
          currentBitrateKbps: 2000,
          averageBitrateKbps: 1900,
          fps: 29.5,
          droppedFrames: 3,
          sentBytes: 123456,
          uptime: Duration(seconds: 62),
          reconnectCount: 1,
          congestionPercent: 12.5,
        );
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing reconnectCount breaks equality', () {
        final a = StreamStats.zero();
        final b = a.copyWith(reconnectCount: 2);
        expect(a == b, isFalse);
      });
    });
  }
  ```

- [ ] **Step 18: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/stream_stats_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/stream_stats.dart': No such file or directory`.

- [ ] **Step 19: Implement `lib/models/stream_stats.dart`**

  ```dart
  import 'package:freezed_annotation/freezed_annotation.dart';

  part 'stream_stats.freezed.dart';

  /// Dart-side aggregation of native 1Hz `StatsSample`s: rolling averages and
  /// session totals shown in the status panel.
  ///
  /// `PipelineController` owns the aggregation math (rolling average bitrate,
  /// uptime clock, cumulative reconnect count); this class is the immutable
  /// snapshot handed to the UI via `streamStatsProvider`. Not persisted, so
  /// no JSON codegen is needed.
  @freezed
  abstract class StreamStats with _$StreamStats {
    const factory StreamStats({
      required int currentBitrateKbps,
      required int averageBitrateKbps,
      required double fps,
      required int droppedFrames,
      required int sentBytes,
      required Duration uptime,
      required int reconnectCount,
      required double congestionPercent,
    }) = _StreamStats;

    /// The all-zero snapshot shown before streaming starts and after a full
    /// stop (session totals reset).
    factory StreamStats.zero() => const StreamStats(
          currentBitrateKbps: 0,
          averageBitrateKbps: 0,
          fps: 0,
          droppedFrames: 0,
          sentBytes: 0,
          uptime: Duration.zero,
          reconnectCount: 0,
          congestionPercent: 0,
        );
  }
  ```

- [ ] **Step 20: Generate and run**

  `make mobile-run CMD="dart run build_runner build --delete-conflicting-outputs"` → succeeds.
  `make mobile-run CMD="flutter test test/models/stream_stats_test.dart"` → PASS.

- [ ] **Step 21: Write failing test for `LicenseStatus`/`LicenseState`**

  `test/models/license_state_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/license_state.dart';

  void main() {
    group('LicenseState.initial', () {
      test('is unknown status, no flags, never fetched', () {
        final initial = LicenseState.initial('device-abc');
        expect(initial.status, LicenseStatus.unknown);
        expect(initial.flags, isEmpty);
        expect(initial.lastFetched, isNull);
        expect(initial.deviceId, 'device-abc');
      });
    });

    group('LicenseState JSON round-trip', () {
      test('toJson/fromJson preserves status, flags map, and lastFetched', () {
        final original = LicenseState(
          status: LicenseStatus.valid,
          flags: const {
            'waddlebot.gazer.camera-stream': true,
            'waddlebot.gazer.uvc-capture': false,
          },
          lastFetched: DateTime.utc(2026, 9, 7, 12, 30),
          deviceId: 'device-abc',
        );
        final restored = LicenseState.fromJson(original.toJson());
        expect(restored, original);
      });

      test('null lastFetched round-trips as null', () {
        final original = LicenseState.initial('device-abc');
        final restored = LicenseState.fromJson(original.toJson());
        expect(restored.lastFetched, isNull);
      });
    });

    group('LicenseState equality', () {
      test('two instances with identical fields are ==', () {
        final a = LicenseState.initial('device-abc');
        final b = LicenseState.initial('device-abc');
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing deviceId breaks equality', () {
        final a = LicenseState.initial('device-abc');
        final b = LicenseState.initial('device-xyz');
        expect(a == b, isFalse);
      });
    });

    group('LicenseStatus', () {
      test('has exactly the four supported values', () {
        expect(LicenseStatus.values, [
          LicenseStatus.unknown,
          LicenseStatus.valid,
          LicenseStatus.gracePeriod,
          LicenseStatus.invalid,
        ]);
      });
    });
  }
  ```

- [ ] **Step 22: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/license_state_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/license_state.dart': No such file or directory`.

- [ ] **Step 23: Implement `lib/models/license_state.dart`**

  ```dart
  import 'package:freezed_annotation/freezed_annotation.dart';

  part 'license_state.freezed.dart';
  part 'license_state.g.dart';

  /// Result of the most recent license/feature-flag validation.
  ///
  /// `unknown` means no successful fetch has ever completed and no usable
  /// cache exists (blocks streaming per the first-launch rule); `gracePeriod`
  /// means the server is unreachable but the cache is within its 7-day grace
  /// window.
  enum LicenseStatus { unknown, valid, gracePeriod, invalid }

  /// Cached license/feature-flag state, persisted as JSON by `LicenseCache`.
  ///
  /// [flags] holds every flag key the server has ever returned; a key absent
  /// from this map is treated as OFF by `FeatureFlags`, never as an error.
  @freezed
  abstract class LicenseState with _$LicenseState {
    const factory LicenseState({
      required LicenseStatus status,
      required Map<String, bool> flags,
      DateTime? lastFetched,
      required String deviceId,
    }) = _LicenseState;

    /// Deserializes a [LicenseState] from JSON (`LicenseCache` reads this
    /// back from `shared_preferences` key `gazer.license.state`).
    factory LicenseState.fromJson(Map<String, dynamic> json) =>
        _$LicenseStateFromJson(json);

    /// Pre-first-fetch state for a freshly resolved [deviceId]: unknown
    /// status, no flags, never fetched.
    factory LicenseState.initial(String deviceId) => LicenseState(
          status: LicenseStatus.unknown,
          flags: const {},
          lastFetched: null,
          deviceId: deviceId,
        );
  }
  ```

- [ ] **Step 24: Generate and run**

  `make mobile-run CMD="dart run build_runner build --delete-conflicting-outputs"` → succeeds.
  `make mobile-run CMD="flutter test test/models/license_state_test.dart"` → PASS.

- [ ] **Step 25: Write failing test for `UpdateInfo`**

  `test/models/update_info_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/update_info.dart';

  void main() {
    group('UpdateInfo equality', () {
      test('two instances with identical fields are ==', () {
        final a = UpdateInfo(
          latestVersion: '1.2.3',
          currentVersion: '1.2.0',
          releaseUrl: Uri.parse('https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.2.3'),
        );
        final b = UpdateInfo(
          latestVersion: '1.2.3',
          currentVersion: '1.2.0',
          releaseUrl: Uri.parse('https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.2.3'),
        );
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing latestVersion breaks equality', () {
        final a = UpdateInfo(
          latestVersion: '1.2.3',
          currentVersion: '1.2.0',
          releaseUrl: Uri.parse('https://example.com/a'),
        );
        final b = UpdateInfo(
          latestVersion: '1.3.0',
          currentVersion: '1.2.0',
          releaseUrl: Uri.parse('https://example.com/a'),
        );
        expect(a == b, isFalse);
      });
    });

    test('fields are exposed exactly as constructed', () {
      final info = UpdateInfo(
        latestVersion: '2.0.0',
        currentVersion: '1.9.9',
        releaseUrl: Uri.parse('https://example.com/release'),
      );
      expect(info.latestVersion, '2.0.0');
      expect(info.currentVersion, '1.9.9');
      expect(info.releaseUrl, Uri.parse('https://example.com/release'));
    });
  }
  ```

- [ ] **Step 26: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/update_info_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/update_info.dart': No such file or directory`.

- [ ] **Step 27: Implement `lib/models/update_info.dart`**

  ```dart
  /// Describes an available update, surfaced by `UpdateChecker` when the
  /// latest `gazer-v*` GitHub release tag is newer than the running app.
  ///
  /// Hand-written (not freezed): never persisted, and `Uri` has no built-in
  /// json_serializable converter, so JSON codegen would need a bespoke
  /// converter for no benefit — this is a display-only, in-memory value.
  class UpdateInfo {
    const UpdateInfo({
      required this.latestVersion,
      required this.currentVersion,
      required this.releaseUrl,
    });

    /// Latest `gazer-vX.Y.Z` tag found on GitHub Releases, without the prefix.
    final String latestVersion;

    /// The running app's version, from `package_info_plus`.
    final String currentVersion;

    /// GitHub Release page for [latestVersion]; opened via `url_launcher`.
    final Uri releaseUrl;

    @override
    bool operator ==(Object other) =>
        identical(this, other) ||
        (other is UpdateInfo &&
            other.latestVersion == latestVersion &&
            other.currentVersion == currentVersion &&
            other.releaseUrl == releaseUrl);

    @override
    int get hashCode => Object.hash(latestVersion, currentVersion, releaseUrl);

    @override
    String toString() =>
        'UpdateInfo(latestVersion: $latestVersion, currentVersion: $currentVersion, releaseUrl: $releaseUrl)';
  }
  ```

- [ ] **Step 28: Run and confirm pass**

  `make mobile-run CMD="flutter test test/models/update_info_test.dart"` → PASS.

- [ ] **Step 29: Write failing test for `ValidationIssue`**

  `test/models/validation_issue_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/validation_issue.dart';

  void main() {
    group('ValidationIssue equality', () {
      test('two instances with identical field/messageKey are ==', () {
        const a = ValidationIssue(field: 'url', messageKey: 'errorUrlScheme');
        const b = ValidationIssue(field: 'url', messageKey: 'errorUrlScheme');
        expect(a, b);
        expect(a.hashCode, b.hashCode);
      });

      test('differing messageKey breaks equality', () {
        const a = ValidationIssue(field: 'url', messageKey: 'errorUrlScheme');
        const b = ValidationIssue(field: 'url', messageKey: 'errorUrlHost');
        expect(a == b, isFalse);
      });
    });

    test('fields are exposed exactly as constructed', () {
      const issue = ValidationIssue(field: 'password', messageKey: 'errorAuthBothOrNeither');
      expect(issue.field, 'password');
      expect(issue.messageKey, 'errorAuthBothOrNeither');
    });
  }
  ```

- [ ] **Step 30: Run and confirm failure**

  `make mobile-run CMD="flutter test test/models/validation_issue_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/models/validation_issue.dart': No such file or directory`.

- [ ] **Step 31: Implement `lib/models/validation_issue.dart`**

  ```dart
  import 'package:freezed_annotation/freezed_annotation.dart';

  part 'validation_issue.freezed.dart';

  /// A single settings-validation failure: which [field] failed and an l10n
  /// [messageKey] to render (never a hardcoded English string).
  ///
  /// Produced by `TargetValidator.validate`; an empty issue list means the
  /// settings are valid and Go Live may proceed.
  @freezed
  abstract class ValidationIssue with _$ValidationIssue {
    const factory ValidationIssue({
      required String field,
      required String messageKey,
    }) = _ValidationIssue;
  }
  ```

- [ ] **Step 32: Generate and run all eight model suites**

  `make mobile-run CMD="dart run build_runner build --delete-conflicting-outputs"` → succeeds.
  `make mobile-run CMD="flutter test test/models/"` → PASS, e.g. `00:0X +47: All tests passed!`

- [ ] **Step 33: Lint**

  `make mobile-lint` → PASS (flutter analyze: no issues found; dart format: no changes needed).

- [ ] **Step 34: Commit**

  ```bash
  git add lib/models/ test/models/
  git commit -m "$(cat <<'EOF'
  feat(gazer): add domain models and enums

  Adds QualitySettings/Resolution/FrameRate, StreamTargetSettings,
  GazerSettings/AudioSourceChoice, the hand-written PipelineState sealed
  hierarchy (+ temporary GazerErrorCode, replaced in Task 6), StreamStats,
  LicenseState/LicenseStatus, UpdateInfo, and ValidationIssue, with unit
  tests for defaults, JSON round-trip, equality, and enum values.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 5: TargetValidator

**Files:**
- Create: `lib/services/target_validator.dart`
- Test: `test/services/target_validator_test.dart`

**Interfaces:**
- Consumes: `StreamTargetSettings` (`lib/models/stream_target_settings.dart`), `ValidationIssue` (`lib/models/validation_issue.dart`).
- Produces: `class TargetValidator { const TargetValidator(); List<ValidationIssue> validate(StreamTargetSettings t); static String effectiveUrl(StreamTargetSettings t); }`

- [ ] **Step 1: Write failing table-driven test**

  `test/services/target_validator_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/models/validation_issue.dart';
  import 'package:gazer/services/target_validator.dart';

  void main() {
    const validator = TargetValidator();

    group('TargetValidator.validate (table-driven)', () {
      final cases = <String, ({StreamTargetSettings target, List<ValidationIssue> expected})>{
        'valid rtmp': (
          target: const StreamTargetSettings(url: 'rtmp://ingest-a.example.com/live'),
          expected: const [],
        ),
        'valid rtmps': (
          target: const StreamTargetSettings(url: 'rtmps://ingest-b.example.com/app'),
          expected: const [],
        ),
        'missing scheme': (
          target: const StreamTargetSettings(url: 'ingest.example.com/live'),
          expected: const [ValidationIssue(field: 'url', messageKey: 'errorUrlScheme')],
        ),
        'http scheme rejected': (
          target: const StreamTargetSettings(url: 'http://bad.example.com/live'),
          expected: const [ValidationIssue(field: 'url', messageKey: 'errorUrlScheme')],
        ),
        'empty host': (
          target: const StreamTargetSettings(url: 'rtmp:///live'),
          expected: const [ValidationIssue(field: 'url', messageKey: 'errorUrlHost')],
        ),
        'missing app path': (
          target: const StreamTargetSettings(url: 'rtmp://host.example.com'),
          expected: const [ValidationIssue(field: 'url', messageKey: 'errorUrlPath')],
        ),
        'username without password rejected': (
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            username: 'demo',
          ),
          expected: const [ValidationIssue(field: 'auth', messageKey: 'errorAuthBothOrNeither')],
        ),
        'password without username rejected': (
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            password: 'secret',
          ),
          expected: const [ValidationIssue(field: 'auth', messageKey: 'errorAuthBothOrNeither')],
        ),
      };

      cases.forEach((description, testCase) {
        test(description, () {
          expect(validator.validate(testCase.target), testCase.expected);
        });
      });
    });

    group('TargetValidator.effectiveUrl', () {
      test('key appended when url lacks it', () {
        const t = StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live',
          streamKey: 'demo-key-0001',
        );
        expect(TargetValidator.effectiveUrl(t), 'rtmp://ingest-a.example.com/live/demo-key-0001');
      });

      test('key not double-appended when url already ends with it', () {
        const t = StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live/demo-key-0001',
          streamKey: 'demo-key-0001',
        );
        expect(TargetValidator.effectiveUrl(t), 'rtmp://ingest-a.example.com/live/demo-key-0001');
      });

      test('key with leading slash is normalised, not double-slashed', () {
        const t = StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live',
          streamKey: '/demo-key-0001',
        );
        expect(TargetValidator.effectiveUrl(t), 'rtmp://ingest-a.example.com/live/demo-key-0001');
      });

      test('trailing slash on url never produces a doubled slash before the key', () {
        const t = StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live/',
          streamKey: 'demo-key-0001',
        );
        final result = TargetValidator.effectiveUrl(t);
        expect(result, 'rtmp://ingest-a.example.com/live/demo-key-0001');
        expect(result.contains('//demo-key-0001'), isFalse);
      });

      test('no key returns the url unchanged', () {
        const t = StreamTargetSettings(url: 'rtmp://ingest-a.example.com/live');
        expect(TargetValidator.effectiveUrl(t), 'rtmp://ingest-a.example.com/live');
      });
    });
  }
  ```

- [ ] **Step 2: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/target_validator_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/target_validator.dart': No such file or directory`.

- [ ] **Step 3: Implement `lib/services/target_validator.dart`**

  ```dart
  import '../models/stream_target_settings.dart';
  import '../models/validation_issue.dart';

  /// Validates a [StreamTargetSettings] against the RTMP/RTMPS target rules
  /// from the design spec, and computes the final connect URL (with the
  /// stream key folded into the path) via [effectiveUrl].
  ///
  /// Stateless and side-effect free: never logs, never touches storage or
  /// the network. `PipelineController.goLive` calls [validate] before ever
  /// touching the native pipeline.
  class TargetValidator {
    const TargetValidator();

    /// Returns the list of validation problems with [t]; empty means valid.
    ///
    /// Checks, in order: the URL parses with an `rtmp`/`rtmps` scheme, a
    /// non-empty host, at least one non-empty path segment, and that
    /// username/password are both present or both absent.
    List<ValidationIssue> validate(StreamTargetSettings t) {
      final issues = <ValidationIssue>[];
      final uri = Uri.tryParse(t.url);

      if (uri == null || (uri.scheme != 'rtmp' && uri.scheme != 'rtmps')) {
        issues.add(const ValidationIssue(field: 'url', messageKey: 'errorUrlScheme'));
      } else {
        if (uri.host.isEmpty) {
          issues.add(const ValidationIssue(field: 'url', messageKey: 'errorUrlHost'));
        }
        final hasPath = uri.pathSegments.any((segment) => segment.isNotEmpty);
        if (!hasPath) {
          issues.add(const ValidationIssue(field: 'url', messageKey: 'errorUrlPath'));
        }
      }

      final hasUsername = (t.username ?? '').isNotEmpty;
      final hasPassword = (t.password ?? '').isNotEmpty;
      if (hasUsername != hasPassword) {
        issues.add(const ValidationIssue(field: 'auth', messageKey: 'errorAuthBothOrNeither'));
      }

      return issues;
    }

    /// The final URL passed to the native `start()` call: [t]'s url with
    /// its stream key folded into the path (appended once, leading slash on
    /// the key normalised away, no trailing-slash duplication).
    ///
    /// Never logs its input or output — the result may contain the stream
    /// key, which is a secret.
    static String effectiveUrl(StreamTargetSettings t) {
      final key = t.streamKey?.trim();
      if (key == null || key.isEmpty) {
        return t.url;
      }
      final normalizedKey = key.startsWith('/') ? key.substring(1) : key;
      final trimmedUrl = t.url.endsWith('/') ? t.url.substring(0, t.url.length - 1) : t.url;
      final lastSegment = trimmedUrl.split('/').last;
      if (lastSegment == normalizedKey) {
        return trimmedUrl;
      }
      return '$trimmedUrl/$normalizedKey';
    }
  }
  ```

- [ ] **Step 4: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/target_validator_test.dart"`
  Expected PASS: `00:0X +13: All tests passed!`

- [ ] **Step 5: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add lib/services/target_validator.dart test/services/target_validator_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): add TargetValidator

  Table-driven validation for RTMP/RTMPS target settings (scheme, host,
  path, both-or-neither auth) and effectiveUrl's key-append/dedupe/
  leading-slash-normalisation logic, with full-coverage unit tests.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 6: Pigeon contract and code generation

**Files:**
- Create: `pigeons/pipeline.dart`
- Test: `test/pigeon/pipeline_contract_test.dart`
- Generate (via `make mobile-codegen`, then commit — never hand-authored): `lib/pigeon/pipeline.g.dart`, `test/pigeon/pipeline_test.g.dart`, `android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/Pipeline.g.kt`
- Modify: `lib/models/pipeline_state.dart` (delete the Task 4 temporary `GazerErrorCode`, import the generated one — see header note 1)

**Interfaces:**
- Produces (generated from `pigeons/pipeline.dart`, single source of truth): `VideoDeviceKind`, `AudioDeviceKind`, `NativePipelineState`, `GazerErrorCode` (canonical, 13 members), `OutputOrientation`, `VideoDevice`, `AudioDevice`, `StreamConfig`, `StreamTarget`, `PrepareResult`, `StatsSample`, `StateEvent`, `GazerHostApi`, `GazerFlutterApi` — every generated data class exposes `encode()` and static `decode(Object)`.
- Consumes: `package:pigeon/pigeon.dart` (dev dependency, pinned 28.0.0 by Task 2).

- [ ] **Step 1: Write failing round-trip test (imports the not-yet-generated file)**

  `test/pigeon/pipeline_contract_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/pigeon/pipeline.g.dart';

  void main() {
    group('Pigeon-generated data classes round-trip through encode()/decode()', () {
      test('VideoDevice', () {
        final original = VideoDevice()
          ..id = 'camera:back'
          ..kind = VideoDeviceKind.backCamera
          ..name = 'Back Camera'
          ..vendorId = null
          ..productId = null;
        final restored = VideoDevice.decode(original.encode());
        expect(restored.id, original.id);
        expect(restored.kind, original.kind);
        expect(restored.name, original.name);
        expect(restored.vendorId, original.vendorId);
        expect(restored.productId, original.productId);
      });

      test('AudioDevice', () {
        final original = AudioDevice()
          ..id = 'audio:mic'
          ..kind = AudioDeviceKind.mic
          ..name = 'Phone Microphone';
        final restored = AudioDevice.decode(original.encode());
        expect(restored.id, original.id);
        expect(restored.kind, original.kind);
        expect(restored.name, original.name);
      });

      test('StreamConfig', () {
        final original = StreamConfig()
          ..videoDeviceId = 'camera:back'
          ..audioDeviceId = 'audio:mic'
          ..width = 960
          ..height = 540
          ..fps = 30
          ..videoBitrateKbps = 2000
          ..adaptiveBitrate = true
          ..audioBitrateKbps = 128
          ..orientation = OutputOrientation.landscape;
        final restored = StreamConfig.decode(original.encode());
        expect(restored.videoDeviceId, original.videoDeviceId);
        expect(restored.audioDeviceId, original.audioDeviceId);
        expect(restored.width, original.width);
        expect(restored.height, original.height);
        expect(restored.fps, original.fps);
        expect(restored.videoBitrateKbps, original.videoBitrateKbps);
        expect(restored.adaptiveBitrate, original.adaptiveBitrate);
        expect(restored.audioBitrateKbps, original.audioBitrateKbps);
        expect(restored.orientation, original.orientation);
      });

      test('StreamTarget', () {
        final original = StreamTarget()
          ..url = 'rtmp://ingest-a.example.com/live/demo-key-0001'
          ..username = 'demo'
          ..password = 'secret';
        final restored = StreamTarget.decode(original.encode());
        expect(restored.url, original.url);
        expect(restored.username, original.username);
        expect(restored.password, original.password);
      });

      test('PrepareResult', () {
        final original = PrepareResult()
          ..ok = false
          ..error = GazerErrorCode.cameraUnavailable
          ..detail = 'no back camera'
          ..negotiatedWidth = null
          ..negotiatedHeight = null
          ..negotiatedFps = null
          ..negotiatedFormat = null;
        final restored = PrepareResult.decode(original.encode());
        expect(restored.ok, original.ok);
        expect(restored.error, original.error);
        expect(restored.detail, original.detail);
      });

      test('StatsSample', () {
        final original = StatsSample()
          ..bitrateKbps = 2000
          ..fps = 29.7
          ..droppedVideoFrames = 3
          ..sentBytes = 123456
          ..congestionPercent = 12.5;
        final restored = StatsSample.decode(original.encode());
        expect(restored.bitrateKbps, original.bitrateKbps);
        expect(restored.fps, original.fps);
        expect(restored.droppedVideoFrames, original.droppedVideoFrames);
        expect(restored.sentBytes, original.sentBytes);
        expect(restored.congestionPercent, original.congestionPercent);
      });

      test('StateEvent', () {
        final original = StateEvent()
          ..state = NativePipelineState.error
          ..error = GazerErrorCode.rtmpAuthFailed
          ..detail = '401 unauthorized';
        final restored = StateEvent.decode(original.encode());
        expect(restored.state, original.state);
        expect(restored.error, original.error);
        expect(restored.detail, original.detail);
      });
    });
  }
  ```

- [ ] **Step 2: Run and confirm failure**

  `make mobile-run CMD="flutter test test/pigeon/pipeline_contract_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/pigeon/pipeline.g.dart': No such file or directory`.

- [ ] **Step 3: Write `pigeons/pipeline.dart` exactly as the shared contract**

  ```dart
  import 'package:pigeon/pigeon.dart';

  @ConfigurePigeon(PigeonOptions(
    dartOut: 'lib/pigeon/pipeline.g.dart',
    dartTestOut: 'test/pigeon/pipeline_test.g.dart',
    kotlinOut: 'android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/Pipeline.g.kt',
    kotlinOptions: KotlinOptions(package: 'io.waddlebot.gazer.pigeon'),
  ))
  library;

  /// Kind of video source a device entry represents.
  enum VideoDeviceKind { backCamera, frontCamera, uvcCamera2, uvcLibuvc }

  /// Kind of audio source a device entry represents.
  enum AudioDeviceKind { mic, usbAudio, silence }

  /// Native pipeline state machine, as reported by the Kotlin side. Dart adds
  /// the `reconnecting` state on top of this (see the Dart `PipelineState`).
  enum NativePipelineState { idle, preparing, ready, connecting, streaming, stopping, error }

  /// Error classification for every failure the native pipeline can report.
  enum GazerErrorCode {
    usbPermissionDenied,
    uvcNoUsableFormat,
    uvcOpenFailed,
    cameraUnavailable,
    cameraInUse,
    encoderFailed,
    audioSourceFailed,
    rtmpAuthFailed,
    rtmpConnectFailed,
    rtmpDisconnected,
    usbDetached,
    serviceStartDenied,
    unknown,
  }

  /// Requested output orientation for the encoded video (camera path only;
  /// UVC is always landscape).
  enum OutputOrientation { landscape, portrait }

  /// One enumerable video source (a camera or an attached UVC device).
  class VideoDevice {
    late String id;
    late VideoDeviceKind kind;
    late String name;
    int? vendorId;
    int? productId;
  }

  /// One enumerable audio source.
  class AudioDevice {
    late String id;
    late AudioDeviceKind kind;
    late String name;
  }

  /// Parameters for `GazerHostApi.prepare` describing the encoder/source setup.
  class StreamConfig {
    late String videoDeviceId;
    late String audioDeviceId;
    late int width;
    late int height;
    late int fps;
    late int videoBitrateKbps;
    late bool adaptiveBitrate;
    late int audioBitrateKbps;
    late OutputOrientation orientation;
  }

  /// RTMP/RTMPS destination passed to `GazerHostApi.start`. `url` already has
  /// the stream key folded in by `TargetValidator.effectiveUrl` on the Dart
  /// side — Kotlin never appends a key itself.
  class StreamTarget {
    late String url;
    String? username;
    String? password;
  }

  /// Result of `GazerHostApi.prepare`: whether the source/encoder negotiated
  /// successfully and, if so, what was actually negotiated.
  class PrepareResult {
    late bool ok;
    GazerErrorCode? error;
    String? detail;
    int? negotiatedWidth;
    int? negotiatedHeight;
    int? negotiatedFps;
    String? negotiatedFormat;
  }

  /// One 1Hz statistics sample emitted by the native encoder/publisher.
  class StatsSample {
    late int bitrateKbps;
    late double fps;
    late int droppedVideoFrames;
    late int sentBytes;
    late double congestionPercent;
  }

  /// A native pipeline state transition, optionally carrying an error.
  class StateEvent {
    late NativePipelineState state;
    GazerErrorCode? error;
    String? detail;
  }

  /// Commands Dart issues to the native pipeline (Dart -> Kotlin).
  @HostApi()
  abstract class GazerHostApi {
    /// Enumerates available video sources (back/front camera; UVC devices
    /// attached at call time).
    List<VideoDevice> listVideoDevices();

    /// Enumerates available audio sources.
    List<AudioDevice> listAudioDevices();

    /// Requests OS-level USB permission for [deviceId]. M1 always returns
    /// false: no UVC devices are ever listed, so this is never actually
    /// invoked with a real device in this milestone.
    @async
    bool requestUsbPermission(String deviceId);

    /// Negotiates the source/encoder for [config]; must succeed before `start`.
    @async
    PrepareResult prepare(StreamConfig config);

    /// Begins publishing to [target]; only valid after a successful `prepare`.
    @async
    void start(StreamTarget target);

    /// Stops publishing and tears down the source/encoder.
    @async
    void stop();

    /// Adjusts the live video bitrate without a full restart (used by the
    /// native `BitrateAdapter` and by Dart-driven manual overrides).
    void setVideoBitrate(int kbps);

    /// Returns the native pipeline's current state synchronously.
    NativePipelineState getState();
  }

  /// Events the native pipeline pushes to Dart (Kotlin -> Dart).
  @FlutterApi()
  abstract class GazerFlutterApi {
    /// Fired on every native state transition.
    void onStateChanged(StateEvent event);

    /// Fired at 1Hz while prepared/streaming.
    void onStats(StatsSample sample);

    /// Fired when a UVC device is physically attached (M1: never fired).
    void onUsbAttached(VideoDevice device);

    /// Fired when a UVC device is physically detached (M1: never fired).
    void onUsbDetached(String deviceId);

    /// Fired after an RTMP auth attempt resolves.
    void onAuthResult(bool ok);
  }
  ```

- [ ] **Step 4: Generate**

  `make mobile-codegen` (now safe: `pigeons/pipeline.dart` exists, so the `dart run pigeon`
  stage of the composite target succeeds, then `build_runner` regenerates the Task 4/7/8/9/10
  freezed/json_serializable part files unchanged, then `flutter gen-l10n` regenerates
  `AppLocalizations` from the Task 2 seed `app_en.arb`).

  Expected output includes:
  ```
  Generating lib/pigeon/pipeline.g.dart / test/pigeon/pipeline_test.g.dart / android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/Pipeline.g.kt
  [INFO] Succeeded after ...ms with 0 outputs (build_runner)
  ```

- [ ] **Step 5: Modify `lib/models/pipeline_state.dart` to consume the canonical enum**

  Delete the temporary `enum GazerErrorCode { ... }` block (Task 4 Step 15) and its doc comment;
  add at the top of the file:
  ```dart
  import 'package:gazer/pigeon/pipeline.g.dart' show GazerErrorCode;
  ```
  Every other declaration in the file (`GazerError`, `PipelineState` and its 8 subclasses) is
  unchanged — they only reference `GazerErrorCode` by name, never redefine it.

- [ ] **Step 6: Run Task 4's model test to confirm no regression**

  `make mobile-run CMD="flutter test test/models/pipeline_state_test.dart"`
  Expected PASS: same 8 tests as Task 4 Step 16, now exercising the Pigeon-generated enum.

- [ ] **Step 7: Run the round-trip test and confirm pass**

  `make mobile-run CMD="flutter test test/pigeon/pipeline_contract_test.dart"`
  Expected PASS: `00:0X +7: All tests passed!`

- [ ] **Step 8: Static analysis**

  `make mobile-run CMD="flutter analyze"` → `No issues found!`

- [ ] **Step 9: Confirm the generated Kotlin file compiles**

  `make mobile-test-android`
  Expected PASS: gradle `testDebugUnitTest` and `jacocoTestReport` succeed; `Pipeline.g.kt`
  compiles as part of the module (no Kotlin unit tests target it directly yet — it is pure
  generated glue, excluded from the JaCoCo coverage denominator by the exclusion pattern Task 2
  Step 10 configured (`exclude("**/pigeon/**")` in the JaCoCo report task)).

- [ ] **Step 10: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 11: Commit**

  ```bash
  git add pigeons/pipeline.dart lib/pigeon/pipeline.g.dart test/pigeon/pipeline_test.g.dart \
    android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/Pipeline.g.kt \
    lib/models/pipeline_state.dart test/pigeon/pipeline_contract_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): add Pigeon pipeline contract and generated bindings

  Adds pigeons/pipeline.dart as the single source of truth for the
  Dart<->Kotlin channel and commits its generated Dart/Kotlin output.
  Retires the Task 4 temporary GazerErrorCode in favor of the canonical
  Pigeon-generated enum.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 7: SettingsRepository

**Files:**
- Create: `lib/services/settings_repository.dart`
- Modify: `pubspec.yaml` (add `shared_preferences_platform_interface` as an explicit pinned `dev_dependency` — needed for `InMemorySharedPreferencesAsync` in tests; see verification below)
- Test: `test/services/settings_repository_test.dart`

**Interfaces:**
- Produces: `abstract class SettingsRepository { Future<GazerSettings> load(); Future<void> save(GazerSettings s); }`; `class SecureSettingsRepository implements SettingsRepository { SecureSettingsRepository({required FlutterSecureStorage secure, required SharedPreferencesAsync prefs}); }`
- Consumes: `GazerSettings`/`QualitySettings`/`StreamTargetSettings`/`AudioSourceChoice`/`Resolution`/`FrameRate` (Task 4), `package:flutter_secure_storage/flutter_secure_storage.dart`, `package:shared_preferences/shared_preferences.dart`.
- Storage keys — secure: `gazer.target.url`, `gazer.target.streamKey`, `gazer.target.username`, `gazer.target.password`; prefs: `gazer.quality.resolution`, `gazer.quality.fps`, `gazer.quality.bitrate`, `gazer.quality.adaptive`, `gazer.audio.source`, `gazer.developer.forceLibuvc`.

**Package verification (WebFetch, recorded here per the contract's instruction):** the pinned
`shared_preferences` 2.5.5 depends on `shared_preferences_platform_interface`, whose in-memory
test double is `InMemorySharedPreferencesAsync` (a `base class` extending
`SharedPreferencesAsyncPlatform`), defined in
`packages/shared_preferences/shared_preferences_platform_interface/lib/in_memory_shared_preferences_async.dart`
in the `flutter/packages` monorepo — confirmed via WebFetch against
`pub.dev/documentation/shared_preferences_platform_interface/latest/` and the raw GitHub source.
Import path: `package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart`.
Constructors: `InMemorySharedPreferencesAsync.empty()` and `.withData(Map<String, Object> data)`.
Usage: assign to `SharedPreferencesAsyncPlatform.instance` before constructing
`SharedPreferencesAsync()` in a test's `setUp`. The latest published version found at lookup time
was `2.4.2`; because `flutter pub get` — not this document — is the authority on which exact
version the dependency graph actually resolves for `shared_preferences` 2.5.5, Step 1 below
records **whatever version `flutter pub add` resolves to** rather than hardcoding `2.4.2`
(same convention the shared contract already uses for `freezed_annotation`).

- [ ] **Step 1: Add the pinned dev dependency and fetch**

  `make mobile-run CMD="flutter pub add --dev shared_preferences_platform_interface"`
  Expected: `pubspec.yaml` gains a `dev_dependencies:` entry
  `shared_preferences_platform_interface: <resolved-version>` (no `^`/`~` — `flutter pub add`
  writes an exact caret-free version only when `--no-example` conventions are followed; if the
  tool writes a caret range, immediately hand-edit `pubspec.yaml` to the exact resolved version
  with no `^` prefix, per the house dependency-pinning rule) and `pubspec.lock` is updated.
  Record the resolved version in a one-line comment above the entry:
  `# resolved by shared_preferences 2.5.5's dependency graph, verified via WebFetch 2026-09-07`.

- [ ] **Step 2: Write failing test**

  `test/services/settings_repository_test.dart`:
  ```dart
  import 'package:flutter_secure_storage/flutter_secure_storage.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/quality.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/services/settings_repository.dart';
  import 'package:mocktail/mocktail.dart';
  import 'package:shared_preferences/shared_preferences.dart';
  import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
  import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

  /// Mocktail fake for [FlutterSecureStorage], backed by an in-memory map so
  /// write/read/delete behave like the real secure storage across a test.
  class _FakeSecureStorage extends Mock implements FlutterSecureStorage {}

  void main() {
    late Map<String, String> secureStore;
    late _FakeSecureStorage secure;
    late SharedPreferencesAsync prefs;
    late SecureSettingsRepository repository;

    setUp(() {
      secureStore = <String, String>{};
      secure = _FakeSecureStorage();
      when(() => secure.write(key: any(named: 'key'), value: any(named: 'value')))
          .thenAnswer((invocation) async {
        final key = invocation.namedArguments[#key] as String;
        final value = invocation.namedArguments[#value] as String?;
        if (value == null) {
          secureStore.remove(key);
        } else {
          secureStore[key] = value;
        }
      });
      when(() => secure.read(key: any(named: 'key'))).thenAnswer(
        (invocation) async => secureStore[invocation.namedArguments[#key] as String],
      );
      when(() => secure.delete(key: any(named: 'key'))).thenAnswer((invocation) async {
        secureStore.remove(invocation.namedArguments[#key] as String);
      });

      SharedPreferencesAsyncPlatform.instance = InMemorySharedPreferencesAsync.empty();
      prefs = SharedPreferencesAsync();

      repository = SecureSettingsRepository(secure: secure, prefs: prefs);
    });

    group('SecureSettingsRepository.load with nothing stored', () {
      test('returns GazerSettings.defaults()', () async {
        final loaded = await repository.load();
        expect(loaded, GazerSettings.defaults());
      });
    });

    group('SecureSettingsRepository save/load round trip', () {
      test('preserves target, quality, audio and developer settings', () async {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmps://ingest-b.example.com/app',
            streamKey: 'demo-key-0002',
            username: 'demo',
            password: 's3cret',
          ),
          quality: const QualitySettings(
            resolution: Resolution.p1080,
            frameRate: FrameRate.fps60,
            videoBitrateKbps: 4500,
            adaptiveBitrate: false,
          ),
          audio: AudioSourceChoice.usbAudio,
          forceLibuvc: true,
        );

        await repository.save(original);
        final loaded = await repository.load();

        expect(loaded, original);
      });
    });

    group('secrets never written to prefs', () {
      test('no shared_preferences key contains "target"', () async {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            streamKey: 'demo-key-0001',
            username: 'demo',
            password: 's3cret',
          ),
          quality: QualitySettings.defaults(),
          audio: AudioSourceChoice.auto,
          forceLibuvc: false,
        );

        await repository.save(original);

        final prefsKeys = await prefs.getKeys();
        expect(prefsKeys.any((key) => key.contains('target')), isFalse);
      });
    });
  }
  ```

- [ ] **Step 3: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/settings_repository_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/settings_repository.dart': No such file or directory`.

- [ ] **Step 4: Implement `lib/services/settings_repository.dart`**

  ```dart
  import 'package:flutter_secure_storage/flutter_secure_storage.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../models/gazer_settings.dart';
  import '../models/quality.dart';
  import '../models/stream_target_settings.dart';

  /// Loads and persists the user's [GazerSettings].
  ///
  /// Implementations decide where each field lives; [SecureSettingsRepository]
  /// is the only implementation in M1, splitting secrets into secure storage
  /// and everything else into shared_preferences per the design's storage
  /// split table.
  abstract class SettingsRepository {
    /// Returns the persisted settings, or [GazerSettings.defaults] if nothing
    /// has ever been saved.
    Future<GazerSettings> load();

    /// Persists every field of [s].
    Future<void> save(GazerSettings s);
  }

  /// [SettingsRepository] backed by `flutter_secure_storage` (target: URL,
  /// stream key, username, password) and `shared_preferences` (quality,
  /// audio, developer toggle) — never mixes the two.
  class SecureSettingsRepository implements SettingsRepository {
    SecureSettingsRepository({required FlutterSecureStorage secure, required SharedPreferencesAsync prefs})
        : _secure = secure,
          _prefs = prefs;

    final FlutterSecureStorage _secure;
    final SharedPreferencesAsync _prefs;

    static const String _kTargetUrl = 'gazer.target.url';
    static const String _kTargetStreamKey = 'gazer.target.streamKey';
    static const String _kTargetUsername = 'gazer.target.username';
    static const String _kTargetPassword = 'gazer.target.password';
    static const String _kQualityResolution = 'gazer.quality.resolution';
    static const String _kQualityFps = 'gazer.quality.fps';
    static const String _kQualityBitrate = 'gazer.quality.bitrate';
    static const String _kQualityAdaptive = 'gazer.quality.adaptive';
    static const String _kAudioSource = 'gazer.audio.source';
    static const String _kDeveloperForceLibuvc = 'gazer.developer.forceLibuvc';

    @override
    Future<GazerSettings> load() async {
      final defaults = GazerSettings.defaults();

      final url = await _secure.read(key: _kTargetUrl) ?? defaults.target.url;
      final streamKey = await _secure.read(key: _kTargetStreamKey);
      final username = await _secure.read(key: _kTargetUsername);
      final password = await _secure.read(key: _kTargetPassword);

      final resolutionName = await _prefs.getString(_kQualityResolution);
      final resolution = Resolution.values.firstWhere(
        (r) => r.name == resolutionName,
        orElse: () => defaults.quality.resolution,
      );
      final fpsValue = await _prefs.getInt(_kQualityFps);
      final frameRate = FrameRate.values.firstWhere(
        (f) => f.value == fpsValue,
        orElse: () => defaults.quality.frameRate,
      );
      final bitrate = await _prefs.getInt(_kQualityBitrate) ?? defaults.quality.videoBitrateKbps;
      final adaptive = await _prefs.getBool(_kQualityAdaptive) ?? defaults.quality.adaptiveBitrate;

      final audioName = await _prefs.getString(_kAudioSource);
      final audio = AudioSourceChoice.values.firstWhere(
        (a) => a.name == audioName,
        orElse: () => defaults.audio,
      );
      final forceLibuvc = await _prefs.getBool(_kDeveloperForceLibuvc) ?? defaults.forceLibuvc;

      return GazerSettings(
        target: StreamTargetSettings(url: url, streamKey: streamKey, username: username, password: password),
        quality: QualitySettings(
          resolution: resolution,
          frameRate: frameRate,
          videoBitrateKbps: bitrate,
          adaptiveBitrate: adaptive,
        ),
        audio: audio,
        forceLibuvc: forceLibuvc,
      );
    }

    @override
    Future<void> save(GazerSettings s) async {
      await _secure.write(key: _kTargetUrl, value: s.target.url);
      await _writeOrDeleteSecure(_kTargetStreamKey, s.target.streamKey);
      await _writeOrDeleteSecure(_kTargetUsername, s.target.username);
      await _writeOrDeleteSecure(_kTargetPassword, s.target.password);

      await _prefs.setString(_kQualityResolution, s.quality.resolution.name);
      await _prefs.setInt(_kQualityFps, s.quality.frameRate.value);
      await _prefs.setInt(_kQualityBitrate, s.quality.videoBitrateKbps);
      await _prefs.setBool(_kQualityAdaptive, s.quality.adaptiveBitrate);
      await _prefs.setString(_kAudioSource, s.audio.name);
      await _prefs.setBool(_kDeveloperForceLibuvc, s.forceLibuvc);
    }

    Future<void> _writeOrDeleteSecure(String key, String? value) {
      if (value == null) {
        return _secure.delete(key: key);
      }
      return _secure.write(key: key, value: value);
    }
  }
  ```

- [ ] **Step 5: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/settings_repository_test.dart"`
  Expected PASS: `00:0X +3: All tests passed!`

- [ ] **Step 6: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 7: Commit**

  ```bash
  git add pubspec.yaml pubspec.lock lib/services/settings_repository.dart test/services/settings_repository_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): add SettingsRepository

  SecureSettingsRepository splits GazerSettings across
  flutter_secure_storage (target: url/key/username/password) and
  shared_preferences (quality/audio/developer toggle), never mixing the
  two. Tests use a mocktail fake FlutterSecureStorage and
  InMemorySharedPreferencesAsync.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 8: ReconnectPolicy

**Files:**
- Create: `lib/services/reconnect_policy.dart`
- Test: `test/services/reconnect_policy_test.dart`

**Interfaces:**
- Consumes: `GazerErrorCode` (`package:gazer/pigeon/pipeline.g.dart`, generated in Task 6).
- Produces: `class ReconnectPolicy { ReconnectPolicy({int maxAttempts = 10, Duration base = const Duration(seconds: 1), Duration cap = const Duration(seconds: 30), double jitter = 0.2, Random? random}); bool shouldRetry(GazerErrorCode code); Duration? delayFor(int attempt); }`

- [ ] **Step 1: Write failing test**

  `test/services/reconnect_policy_test.dart`:
  ```dart
  import 'dart:math';

  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/pigeon/pipeline.g.dart';
  import 'package:gazer/services/reconnect_policy.dart';

  /// Deterministic stand-in for [Random] whose `nextDouble()` always returns
  /// [fixedValue], so jitter in [ReconnectPolicy.delayFor] is reproducible.
  class _FixedRandom implements Random {
    _FixedRandom(this.fixedValue);

    final double fixedValue;

    @override
    double nextDouble() => fixedValue;

    @override
    bool nextBool() => false;

    @override
    int nextInt(int max) => 0;
  }

  void main() {
    group('ReconnectPolicy.shouldRetry (table-driven, all 13 codes)', () {
      final policy = ReconnectPolicy();
      final expected = <GazerErrorCode, bool>{
        GazerErrorCode.usbPermissionDenied: false,
        GazerErrorCode.uvcNoUsableFormat: false,
        GazerErrorCode.uvcOpenFailed: false,
        GazerErrorCode.cameraUnavailable: false,
        GazerErrorCode.cameraInUse: false,
        GazerErrorCode.encoderFailed: false,
        GazerErrorCode.audioSourceFailed: false,
        GazerErrorCode.rtmpAuthFailed: false,
        GazerErrorCode.rtmpConnectFailed: true,
        GazerErrorCode.rtmpDisconnected: true,
        GazerErrorCode.usbDetached: false,
        GazerErrorCode.serviceStartDenied: false,
        GazerErrorCode.unknown: false,
      };

      expected.forEach((code, shouldRetry) {
        test('$code -> shouldRetry == $shouldRetry', () {
          expect(policy.shouldRetry(code), shouldRetry);
        });
      });
    });

    group('ReconnectPolicy.delayFor with zero jitter (fixed Random at midpoint)', () {
      final policy = ReconnectPolicy(random: _FixedRandom(0.5));

      test('attempts 1 through 10 follow base*2^(attempt-1) capped at 30s', () {
        final expectedSeconds = [1, 2, 4, 8, 16, 30, 30, 30, 30, 30];
        for (var attempt = 1; attempt <= 10; attempt++) {
          final delay = policy.delayFor(attempt);
          expect(delay, isNotNull, reason: 'attempt $attempt');
          expect(
            delay!.inMilliseconds,
            expectedSeconds[attempt - 1] * 1000,
            reason: 'attempt $attempt',
          );
        }
      });

      test('delayFor(11) is null (exceeds maxAttempts)', () {
        expect(policy.delayFor(11), isNull);
      });

      test('delayFor(0) is null (attempts are 1-based)', () {
        expect(policy.delayFor(0), isNull);
      });
    });

    group('ReconnectPolicy.delayFor jitter bounds', () {
      test('random at 1.0 applies the full +20% jitter', () {
        final policy = ReconnectPolicy(random: _FixedRandom(1.0));
        final delay = policy.delayFor(1);
        expect(delay!.inMilliseconds, 1200);
      });

      test('random at 0.0 applies the full -20% jitter', () {
        final policy = ReconnectPolicy(random: _FixedRandom(0.0));
        final delay = policy.delayFor(1);
        expect(delay!.inMilliseconds, 800);
      });

      test('cap is applied before jitter, so attempt 10 never exceeds 36s (30s + 20%)', () {
        final policy = ReconnectPolicy(random: _FixedRandom(1.0));
        final delay = policy.delayFor(10);
        expect(delay!.inMilliseconds, 36000);
      });
    });
  }
  ```

- [ ] **Step 2: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/reconnect_policy_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/reconnect_policy.dart': No such file or directory`.

- [ ] **Step 3: Implement `lib/services/reconnect_policy.dart`**

  ```dart
  import 'dart:math';

  import '../pigeon/pipeline.g.dart';

  /// Dart-owned exponential-backoff policy for RTMP reconnects.
  ///
  /// Native (`RootEncoder`) never retries on its own (`setReTries(0)`
  /// always); `PipelineController` asks this class whether a given
  /// [GazerErrorCode] is retryable and, if so, how long to wait before
  /// calling `start()` again.
  class ReconnectPolicy {
    ReconnectPolicy({
      this.maxAttempts = 10,
      this.base = const Duration(seconds: 1),
      this.cap = const Duration(seconds: 30),
      this.jitter = 0.2,
      Random? random,
    }) : _random = random ?? Random();

    /// Maximum number of retry attempts before giving up permanently.
    final int maxAttempts;

    /// Delay before the first retry; doubled on every subsequent attempt.
    final Duration base;

    /// Upper bound on the (pre-jitter) computed delay.
    final Duration cap;

    /// Fractional jitter applied to the capped delay, e.g. `0.2` = ±20%.
    final double jitter;

    final Random _random;

    static const Set<GazerErrorCode> _retryableCodes = {
      GazerErrorCode.rtmpConnectFailed,
      GazerErrorCode.rtmpDisconnected,
    };

    /// True only for the two transient RTMP failure codes; every other
    /// [GazerErrorCode] (auth, USB, camera, encoder, service-start errors)
    /// requires manual user action per the design's retry-policy table.
    bool shouldRetry(GazerErrorCode code) => _retryableCodes.contains(code);

    /// Delay before the [attempt]-th retry (1-based), or `null` once
    /// [attempt] exceeds [maxAttempts]. Computed as `base * 2^(attempt-1)`,
    /// capped at [cap], then jittered by ±[jitter] using the injected
    /// [Random] so tests can make the sequence deterministic.
    Duration? delayFor(int attempt) {
      if (attempt < 1 || attempt > maxAttempts) return null;
      final rawMs = base.inMilliseconds * pow(2, attempt - 1);
      final cappedMs = min(rawMs.toDouble(), cap.inMilliseconds.toDouble());
      final jitterFactor = 1 + jitter * (2 * _random.nextDouble() - 1);
      final jitteredMs = (cappedMs * jitterFactor).round();
      return Duration(milliseconds: jitteredMs);
    }
  }
  ```

- [ ] **Step 4: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/reconnect_policy_test.dart"`
  Expected PASS: `00:0X +18: All tests passed!`

- [ ] **Step 5: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add lib/services/reconnect_policy.dart test/services/reconnect_policy_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): add ReconnectPolicy

  Dart-owned exponential backoff (1/2/4/8/16/30s cap, ±20% jitter,
  max 10 attempts) for the two retryable RTMP error codes; every other
  GazerErrorCode requires manual user action. Jitter is deterministic
  in tests via an injected Random.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 9: Device id, license client, feature flags

**Files:**
- Create: `lib/config/constants.dart` (not owned by any other numbered task — first needed here, see header note), `lib/services/device_id.dart`, `lib/services/license_client.dart`, `lib/services/feature_flags.dart`
- Test: `test/services/device_id_test.dart`, `test/services/license_client_test.dart`, `test/services/feature_flags_test.dart`

**Interfaces:**
- Produces: `const String kLicenseBaseUrl`, `const String kGithubReleasesUrl`, `const Duration kLicenseKeepaliveInterval`, `const Duration kLicenseGracePeriod`; `abstract class DeviceIdProvider { Future<String> deviceId(); }`; `class AndroidDeviceIdProvider implements DeviceIdProvider { AndroidDeviceIdProvider({required DeviceInfoPlugin deviceInfo, required PackageInfo packageInfo}); }`; `class LicenseClient { LicenseClient({required Dio dio, required LicenseCache cache, required DeviceIdProvider deviceIdProvider, required DateTime Function() now, String baseUrl = kLicenseBaseUrl}); Future<LicenseState> validateAndFetchFlags(); Future<void> keepalive(); }`; `class LicenseCache { LicenseCache(SharedPreferencesAsync prefs); Future<LicenseState?> read(); Future<void> write(LicenseState s); }`; `class FeatureFlags { const FeatureFlags(LicenseState state); bool isEnabled(String key); bool get hasFetchedOnce; }`
- Consumes: `LicenseState`/`LicenseStatus` (Task 4), `class FlagKeys` (`cameraStream`, `uvcCapture`, `adaptiveBitrate`, `rtmpAuth` — `lib/config/flag_keys.dart`, Task 2), `package:dio/dio.dart`, `package:device_info_plus/device_info_plus.dart`, `package:package_info_plus/package_info_plus.dart`, `package:crypto/crypto.dart`, `package:shared_preferences/shared_preferences.dart`.

**Note on `AndroidDeviceIdProvider`:** `device_info_plus` does not expose the platform
`Settings.Secure.ANDROID_ID` value — `AndroidDeviceInfo` has no such field. The contract's
constructor signature is fixed to exactly `{required DeviceInfoPlugin deviceInfo, required
PackageInfo packageInfo}`, so [AndroidDeviceInfo.id] (the build fingerprint ID — the field
literally named `id`) is the identifier actually hashed, matching the contract's own literal
digest input `'$androidId:$packageName'`.

- [ ] **Step 1: Create config constants**

  `lib/config/flag_keys.dart` already exists (Task 2 — moved there in the A/D reconciliation pass
  so coverage has a non-zero denominator from the first task) with its `FlagKeys` class exactly
  per the shared contract shape (`FlagKeys.cameraStream`, `.uvcCapture`, `.adaptiveBitrate`,
  `.rtmpAuth`). Verify it before continuing — do not redefine it here:
  ```
  test -f mobile/gazer/lib/config/flag_keys.dart && grep -c 'static const String' mobile/gazer/lib/config/flag_keys.dart
  ```
  Expected: file exists, `4` (one per flag key). If missing, stop — Task 2 is incomplete; do not
  hand-roll a second `FlagKeys` definition here.

  `lib/config/constants.dart`:
  ```dart
  /// App-wide constants: license server base URL, GitHub releases endpoint
  /// for the update checker, and shared licensing timing knobs.
  ///
  /// Single source of truth — every service needing one of these values
  /// imports it from here rather than hardcoding it inline.
  library;

  /// Base URL for the PenguinTech license server's Gazer-facing API.
  const String kLicenseBaseUrl = 'https://license.penguintech.io/api/v2';

  /// GitHub Releases API endpoint polled by `UpdateChecker`.
  const String kGithubReleasesUrl =
      'https://api.github.com/repos/penguintechinc/waddlebot/releases';

  /// Interval between license keepalive pings while the app is foregrounded.
  const Duration kLicenseKeepaliveInterval = Duration(minutes: 5);

  /// Offline grace period: a cached license result stays usable this long
  /// after the last successful fetch, even if the server is unreachable.
  const Duration kLicenseGracePeriod = Duration(days: 7);
  ```

  No test file for this: it is constant declarations with no branching logic (nothing to
  assert beyond "the constant equals its literal", which the compiler already guarantees);
  every consumer below exercises them transitively.

- [ ] **Step 2: Write failing test for `AndroidDeviceIdProvider`**

  `test/services/device_id_test.dart`:
  ```dart
  import 'dart:convert';

  import 'package:crypto/crypto.dart';
  import 'package:device_info_plus/device_info_plus.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/services/device_id.dart';
  import 'package:mocktail/mocktail.dart';
  import 'package:package_info_plus/package_info_plus.dart';

  class _MockDeviceInfoPlugin extends Mock implements DeviceInfoPlugin {}

  class _MockAndroidDeviceInfo extends Mock implements AndroidDeviceInfo {}

  void main() {
    group('AndroidDeviceIdProvider.deviceId', () {
      test('is sha256("<androidId>:<packageName>") hex-encoded', () async {
        final deviceInfoPlugin = _MockDeviceInfoPlugin();
        final androidInfo = _MockAndroidDeviceInfo();
        when(() => androidInfo.id).thenReturn('abc123');
        when(() => deviceInfoPlugin.androidInfo).thenAnswer((_) async => androidInfo);

        const packageInfo = PackageInfo(
          appName: 'Gazer',
          packageName: 'io.waddlebot.gazer',
          version: '1.0.0',
          buildNumber: '1',
        );

        final provider = AndroidDeviceIdProvider(
          deviceInfo: deviceInfoPlugin,
          packageInfo: packageInfo,
        );

        final id = await provider.deviceId();
        final expected = sha256.convert(utf8.encode('abc123:io.waddlebot.gazer')).toString();
        expect(id, expected);
      });

      test('is deterministic across repeated calls', () async {
        final deviceInfoPlugin = _MockDeviceInfoPlugin();
        final androidInfo = _MockAndroidDeviceInfo();
        when(() => androidInfo.id).thenReturn('xyz789');
        when(() => deviceInfoPlugin.androidInfo).thenAnswer((_) async => androidInfo);
        const packageInfo = PackageInfo(
          appName: 'Gazer',
          packageName: 'io.waddlebot.gazer',
          version: '1.0.0',
          buildNumber: '1',
        );
        final provider = AndroidDeviceIdProvider(deviceInfo: deviceInfoPlugin, packageInfo: packageInfo);

        final first = await provider.deviceId();
        final second = await provider.deviceId();
        expect(first, second);
      });
    });
  }
  ```

- [ ] **Step 3: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/device_id_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/device_id.dart': No such file or directory`.

- [ ] **Step 4: Implement `lib/services/device_id.dart`**

  ```dart
  import 'dart:convert';

  import 'package:crypto/crypto.dart';
  import 'package:device_info_plus/device_info_plus.dart';
  import 'package:package_info_plus/package_info_plus.dart';

  /// Resolves the stable per-install device identifier used by `LicenseClient`.
  abstract class DeviceIdProvider {
    /// Returns a stable, hex-encoded identifier for this install.
    Future<String> deviceId();
  }

  /// Resolves the device identifier as SHA-256 of `'<androidId>:<packageName>'`,
  /// hex-encoded.
  ///
  /// `device_info_plus` does not expose the raw platform
  /// `Settings.Secure.ANDROID_ID` value; [AndroidDeviceInfo.id] (the build
  /// fingerprint ID) is the closest stable identifier reachable through the
  /// two dependencies this class is constructed with, per the design
  /// contract's exact constructor signature.
  class AndroidDeviceIdProvider implements DeviceIdProvider {
    AndroidDeviceIdProvider({
      required DeviceInfoPlugin deviceInfo,
      required PackageInfo packageInfo,
    })  : _deviceInfo = deviceInfo,
          _packageInfo = packageInfo;

    final DeviceInfoPlugin _deviceInfo;
    final PackageInfo _packageInfo;

    @override
    Future<String> deviceId() async {
      final androidInfo = await _deviceInfo.androidInfo;
      final raw = '${androidInfo.id}:${_packageInfo.packageName}';
      return sha256.convert(utf8.encode(raw)).toString();
    }
  }
  ```

- [ ] **Step 5: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/device_id_test.dart"`
  Expected PASS: `00:0X +2: All tests passed!`

- [ ] **Step 6: Write failing test for `LicenseCache` + `LicenseClient`**

  `test/services/license_client_test.dart`:
  ```dart
  import 'package:dio/dio.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/services/device_id.dart';
  import 'package:gazer/services/license_client.dart';
  import 'package:mocktail/mocktail.dart';
  import 'package:shared_preferences/shared_preferences.dart';
  import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
  import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

  class _MockDio extends Mock implements Dio {}

  class _FakeDeviceIdProvider implements DeviceIdProvider {
    @override
    Future<String> deviceId() async => 'device-abc';
  }

  void main() {
    setUpAll(() {
      registerFallbackValue(<String, String>{});
    });

    late _MockDio dio;
    late LicenseCache cache;
    late DateTime fakeNow;

    setUp(() {
      dio = _MockDio();
      SharedPreferencesAsyncPlatform.instance = InMemorySharedPreferencesAsync.empty();
      cache = LicenseCache(SharedPreferencesAsync());
      fakeNow = DateTime.utc(2026, 9, 7, 12);
    });

    LicenseClient buildClient() => LicenseClient(
          dio: dio,
          cache: cache,
          deviceIdProvider: _FakeDeviceIdProvider(),
          now: () => fakeNow,
        );

    group('LicenseCache round trip', () {
      test('read() returns null when nothing was ever written', () async {
        expect(await cache.read(), isNull);
      });

      test('write() then read() returns the same LicenseState', () async {
        final state = LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: fakeNow,
          deviceId: 'device-abc',
        );
        await cache.write(state);
        expect(await cache.read(), state);
      });
    });

    group('validateAndFetchFlags success', () {
      test('returns valid status, server flags, and lastFetched = now()', () async {
        when(() => dio.post(any(), data: any(named: 'data'))).thenAnswer((invocation) async {
          final path = invocation.positionalArguments.first as String;
          if (path.endsWith('/validate')) {
            return Response(requestOptions: RequestOptions(path: path), statusCode: 200, data: {});
          }
          return Response(
            requestOptions: RequestOptions(path: path),
            statusCode: 200,
            data: {
              'features': {'waddlebot.gazer.camera-stream': true},
            },
          );
        });

        final state = await buildClient().validateAndFetchFlags();

        expect(state.status, LicenseStatus.valid);
        expect(state.flags['waddlebot.gazer.camera-stream'], isTrue);
        expect(state.lastFetched, fakeNow);
      });
    });

    group('validateAndFetchFlags network error with fresh cache', () {
      test('within 7 days -> gracePeriod with cached flags', () async {
        await cache.write(LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: fakeNow.subtract(const Duration(days: 3)),
          deviceId: 'device-abc',
        ));
        when(() => dio.post(any(), data: any(named: 'data'))).thenThrow(
          DioException(requestOptions: RequestOptions(path: '/validate'), type: DioExceptionType.connectionTimeout),
        );

        final state = await buildClient().validateAndFetchFlags();

        expect(state.status, LicenseStatus.gracePeriod);
        expect(state.flags['waddlebot.gazer.camera-stream'], isTrue);
      });
    });

    group('validateAndFetchFlags network error with stale cache', () {
      test('older than 7 days -> unknown', () async {
        await cache.write(LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: fakeNow.subtract(const Duration(days: 10)),
          deviceId: 'device-abc',
        ));
        when(() => dio.post(any(), data: any(named: 'data'))).thenThrow(
          DioException(requestOptions: RequestOptions(path: '/validate'), type: DioExceptionType.connectionTimeout),
        );

        final state = await buildClient().validateAndFetchFlags();

        expect(state.status, LicenseStatus.unknown);
      });

      test('no cache at all -> unknown with empty flags', () async {
        when(() => dio.post(any(), data: any(named: 'data'))).thenThrow(
          DioException(requestOptions: RequestOptions(path: '/validate'), type: DioExceptionType.connectionTimeout),
        );

        final state = await buildClient().validateAndFetchFlags();

        expect(state.status, LicenseStatus.unknown);
        expect(state.flags, isEmpty);
      });
    });

    group('validateAndFetchFlags 4xx response', () {
      test('-> invalid', () async {
        when(() => dio.post(any(), data: any(named: 'data'))).thenThrow(
          DioException(
            requestOptions: RequestOptions(path: '/validate'),
            type: DioExceptionType.badResponse,
            response: Response(requestOptions: RequestOptions(path: '/validate'), statusCode: 401),
          ),
        );

        final state = await buildClient().validateAndFetchFlags();

        expect(state.status, LicenseStatus.invalid);
      });
    });

    group('validateAndFetchFlags never throws', () {
      test('an unexpected exception (malformed response shape) is swallowed, not rethrown', () async {
        when(() => dio.post(any(), data: any(named: 'data'))).thenAnswer((invocation) async {
          final path = invocation.positionalArguments.first as String;
          return Response(requestOptions: RequestOptions(path: path), statusCode: 200, data: {});
        });

        expect(buildClient().validateAndFetchFlags(), completes);
      });
    });

    group('keepalive', () {
      test('is fire-and-forget: completes even when the POST throws', () async {
        when(() => dio.post(any(), data: any(named: 'data'))).thenThrow(
          DioException(requestOptions: RequestOptions(path: '/keepalive'), type: DioExceptionType.connectionTimeout),
        );

        await expectLater(buildClient().keepalive(), completes);
      });
    });
  }
  ```

- [ ] **Step 7: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/license_client_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/license_client.dart': No such file or directory`.

- [ ] **Step 8: Implement `lib/services/license_client.dart`**

  ```dart
  import 'dart:async';
  import 'dart:convert';

  import 'package:dio/dio.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../config/constants.dart';
  import '../models/license_state.dart';
  import 'device_id.dart';

  /// Persists the most recent [LicenseState] as JSON in shared_preferences.
  class LicenseCache {
    LicenseCache(SharedPreferencesAsync prefs) : _prefs = prefs;

    final SharedPreferencesAsync _prefs;

    static const String _kKey = 'gazer.license.state';

    /// Returns the cached state, or `null` if nothing has ever been written.
    Future<LicenseState?> read() async {
      final json = await _prefs.getString(_kKey);
      if (json == null) return null;
      return LicenseState.fromJson(jsonDecode(json) as Map<String, dynamic>);
    }

    /// Overwrites the cached state with [s].
    Future<void> write(LicenseState s) async {
      await _prefs.setString(_kKey, jsonEncode(s.toJson()));
    }
  }

  /// App-local client for the PenguinTech license server's Gazer-facing API
  /// (temporary bridge pending promotion into `flutter_libs` — see the
  /// design spec's "TEMPORARY BRIDGE" decision).
  ///
  /// Never throws: every failure path degrades to a cached or `unknown`
  /// [LicenseState] instead of propagating an exception to the caller.
  class LicenseClient {
    LicenseClient({
      required Dio dio,
      required LicenseCache cache,
      required DeviceIdProvider deviceIdProvider,
      required DateTime Function() now,
      this.baseUrl = kLicenseBaseUrl,
    })  : _dio = dio,
          _cache = cache,
          _deviceIdProvider = deviceIdProvider,
          _now = now;

    final Dio _dio;
    final LicenseCache _cache;
    final DeviceIdProvider _deviceIdProvider;
    final DateTime Function() _now;

    /// Base URL for `/validate`, `/features`, `/keepalive`.
    final String baseUrl;

    /// Validates this install and fetches its feature flags.
    ///
    /// Success -> `valid` with fresh flags and `lastFetched = now()`.
    /// Network error with a cache fetched within [kLicenseGracePeriod] ->
    /// `gracePeriod` with the cached flags. Network error with a stale or
    /// absent cache -> `unknown`. A 4xx response -> `invalid`. Any other
    /// failure (including a malformed response body) is swallowed and
    /// treated the same as a network error — this method never throws.
    Future<LicenseState> validateAndFetchFlags() async {
      final deviceId = await _deviceIdProvider.deviceId();
      final cached = await _cache.read();
      try {
        await _dio.post('$baseUrl/validate', data: _payload(deviceId));
        final response = await _dio.post('$baseUrl/features', data: _payload(deviceId));
        final rawFlags = Map<String, dynamic>.from(
          (response.data as Map<String, dynamic>)['features'] as Map,
        );
        final flags = rawFlags.map((key, value) => MapEntry(key, value as bool));
        final state = LicenseState(
          status: LicenseStatus.valid,
          flags: flags,
          lastFetched: _now(),
          deviceId: deviceId,
        );
        await _cache.write(state);
        return state;
      } on DioException catch (e) {
        final statusCode = e.response?.statusCode;
        if (statusCode != null && statusCode >= 400 && statusCode < 500) {
          final invalid = LicenseState(
            status: LicenseStatus.invalid,
            flags: cached?.flags ?? const {},
            lastFetched: cached?.lastFetched,
            deviceId: deviceId,
          );
          await _cache.write(invalid);
          return invalid;
        }
        return _offlineFallback(cached, deviceId);
      } catch (_) {
        return _offlineFallback(cached, deviceId);
      }
    }

    /// Fire-and-forget keepalive ping; failures are swallowed silently.
    Future<void> keepalive() async {
      final deviceId = await _deviceIdProvider.deviceId();
      unawaited(_dio.post('$baseUrl/keepalive', data: _payload(deviceId)).catchError((_) => null));
    }

    LicenseState _offlineFallback(LicenseState? cached, String deviceId) {
      if (cached?.lastFetched != null && _now().difference(cached!.lastFetched!) <= kLicenseGracePeriod) {
        return cached.copyWith(status: LicenseStatus.gracePeriod);
      }
      return LicenseState(
        status: LicenseStatus.unknown,
        flags: cached?.flags ?? const {},
        lastFetched: cached?.lastFetched,
        deviceId: deviceId,
      );
    }

    Map<String, String> _payload(String deviceId) => {
          'device_id': deviceId,
          'product': 'waddlebot',
          'component': 'gazer',
        };
  }
  ```

- [ ] **Step 9: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/license_client_test.dart"`
  Expected PASS: `00:0X +8: All tests passed!`

- [ ] **Step 10: Write failing test for `FeatureFlags`**

  `test/services/feature_flags_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/services/feature_flags.dart';

  void main() {
    group('FeatureFlags.isEnabled', () {
      test('a never-seen flag key is false', () {
        final flags = FeatureFlags(LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ));
        expect(flags.isEnabled('waddlebot.gazer.rtmp-auth'), isFalse);
      });

      test('a known-true flag key is true', () {
        final flags = FeatureFlags(LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ));
        expect(flags.isEnabled('waddlebot.gazer.camera-stream'), isTrue);
      });
    });

    group('FeatureFlags.hasFetchedOnce', () {
      test('is false before any successful fetch', () {
        final flags = FeatureFlags(LicenseState.initial('device-abc'));
        expect(flags.hasFetchedOnce, isFalse);
      });

      test('is true once lastFetched is set', () {
        final flags = FeatureFlags(LicenseState(
          status: LicenseStatus.valid,
          flags: const {},
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ));
        expect(flags.hasFetchedOnce, isTrue);
      });
    });
  }
  ```

- [ ] **Step 11: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/feature_flags_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/feature_flags.dart': No such file or directory`.

- [ ] **Step 12: Implement `lib/services/feature_flags.dart`**

  ```dart
  import '../models/license_state.dart';

  /// Read-only view over a [LicenseState] for flag checks.
  ///
  /// A key absent from `state.flags` is treated as OFF, never as an error —
  /// this is what makes "never-seen flags default OFF" true regardless of
  /// whether the license server has ever heard of a given flag key.
  class FeatureFlags {
    const FeatureFlags(this._state);

    final LicenseState _state;

    /// Whether [key] is enabled; defaults to `false` if [key] was never
    /// returned by the server.
    bool isEnabled(String key) => _state.flags[key] ?? false;

    /// Whether at least one successful validate+features fetch has ever
    /// completed. The first-launch rule blocks Go Live until this is true.
    bool get hasFetchedOnce => _state.lastFetched != null;
  }
  ```

- [ ] **Step 13: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/feature_flags_test.dart"`
  Expected PASS: `00:0X +4: All tests passed!`

- [ ] **Step 14: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 15: Commit**

  ```bash
  git add lib/config/constants.dart lib/services/device_id.dart \
    lib/services/license_client.dart lib/services/feature_flags.dart \
    test/services/device_id_test.dart test/services/license_client_test.dart test/services/feature_flags_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): add device id, LicenseClient, LicenseCache, and FeatureFlags

  AndroidDeviceIdProvider hashes androidId:packageName; LicenseClient
  validates + fetches flags against license.penguintech.io with a
  7-day offline grace period and never throws; FeatureFlags treats an
  absent flag key as OFF. Adds lib/config/constants.dart, first needed
  here (flag_keys.dart already exists from Task 2).

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 10: UpdateChecker

**Files:**
- Create: `lib/services/update_checker.dart`
- Test: `test/services/update_checker_test.dart`

**Interfaces:**
- Produces: `class UpdateChecker { UpdateChecker({required Dio dio, required String currentVersion, String releasesUrl = kGithubReleasesUrl}); Future<UpdateInfo?> check(); }`
- Consumes: `UpdateInfo` (Task 4), `kGithubReleasesUrl` (Task 9), `package:dio/dio.dart`.

- [ ] **Step 1: Write failing test**

  `test/services/update_checker_test.dart`:
  ```dart
  import 'package:dio/dio.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/services/update_checker.dart';
  import 'package:mocktail/mocktail.dart';

  class _MockDio extends Mock implements Dio {}

  void main() {
    late _MockDio dio;

    setUp(() {
      dio = _MockDio();
    });

    Response<dynamic> releasesResponse(List<Map<String, dynamic>> releases) => Response(
          requestOptions: RequestOptions(path: 'releases'),
          statusCode: 200,
          data: releases,
        );

    group('UpdateChecker.check', () {
      test('a newer gazer-v tag returns UpdateInfo', () async {
        when(() => dio.get(any())).thenAnswer((_) async => releasesResponse([
              {
                'tag_name': 'gazer-v1.3.0',
                'html_url': 'https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.3.0',
              },
            ]));
        final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

        final info = await checker.check();

        expect(info, isNotNull);
        expect(info!.latestVersion, '1.3.0');
        expect(info.currentVersion, '1.2.0');
        expect(
          info.releaseUrl,
          Uri.parse('https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.3.0'),
        );
      });

      test('an equal tag returns null', () async {
        when(() => dio.get(any())).thenAnswer((_) async => releasesResponse([
              {'tag_name': 'gazer-v1.2.0', 'html_url': 'https://example.com/gazer-v1.2.0'},
            ]));
        final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

        expect(await checker.check(), isNull);
      });

      test('non-gazer tags are ignored', () async {
        when(() => dio.get(any())).thenAnswer((_) async => releasesResponse([
              {'tag_name': 'v1.9.0', 'html_url': 'https://example.com/v1.9.0'},
              {'tag_name': 'backend-v2.0.0', 'html_url': 'https://example.com/backend-v2.0.0'},
            ]));
        final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

        expect(await checker.check(), isNull);
      });

      test('a malformed release list returns null', () async {
        when(() => dio.get(any())).thenAnswer(
          (_) async =>
              Response(requestOptions: RequestOptions(path: 'releases'), statusCode: 200, data: 'not-a-list'),
        );
        final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

        expect(await checker.check(), isNull);
      });

      test('a network error returns null', () async {
        when(() => dio.get(any())).thenThrow(
          DioException(requestOptions: RequestOptions(path: 'releases'), type: DioExceptionType.connectionTimeout),
        );
        final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

        expect(await checker.check(), isNull);
      });

      test('semver compare treats 1.10.0 as newer than 1.9.9', () async {
        when(() => dio.get(any())).thenAnswer((_) async => releasesResponse([
              {'tag_name': 'gazer-v1.10.0', 'html_url': 'https://example.com/gazer-v1.10.0'},
            ]));
        final checker = UpdateChecker(dio: dio, currentVersion: '1.9.9');

        final info = await checker.check();

        expect(info, isNotNull);
        expect(info!.latestVersion, '1.10.0');
      });
    });
  }
  ```

- [ ] **Step 2: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/update_checker_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/update_checker.dart': No such file or directory`.

- [ ] **Step 3: Implement `lib/services/update_checker.dart`**

  ```dart
  import 'package:dio/dio.dart';

  import '../config/constants.dart';
  import '../models/update_info.dart';

  /// Polls GitHub Releases for `penguintechinc/waddlebot` and reports the
  /// newest `gazer-vX.Y.Z` tag, if it is newer than [currentVersion].
  ///
  /// Non-blocking, startup-only in the app shell; any failure (network,
  /// malformed body, unparseable tags) resolves to `null` rather than
  /// throwing — an update notice is never worth crashing over.
  class UpdateChecker {
    UpdateChecker({
      required Dio dio,
      required this.currentVersion,
      this.releasesUrl = kGithubReleasesUrl,
    }) : _dio = dio;

    final Dio _dio;

    /// The running app's version, from `package_info_plus`.
    final String currentVersion;

    /// GitHub Releases API endpoint to poll.
    final String releasesUrl;

    static final RegExp _tagPattern = RegExp(r'^gazer-v(\d+)\.(\d+)\.(\d+)$');
    static final RegExp _semverPrefix = RegExp(r'^(\d+)\.(\d+)\.(\d+)');

    /// Returns [UpdateInfo] for the newest `gazer-v*` release strictly newer
    /// than [currentVersion], or `null` when up to date or on any error.
    Future<UpdateInfo?> check() async {
      try {
        final response = await _dio.get(releasesUrl);
        final releases = response.data as List<dynamic>;

        String? bestTag;
        List<int>? bestVersion;
        String? bestUrl;
        for (final release in releases) {
          final map = release as Map<String, dynamic>;
          final tagName = map['tag_name'] as String?;
          if (tagName == null) continue;
          final match = _tagPattern.firstMatch(tagName);
          if (match == null) continue;
          final version = [
            int.parse(match.group(1)!),
            int.parse(match.group(2)!),
            int.parse(match.group(3)!),
          ];
          if (bestVersion == null || _compare(version, bestVersion) > 0) {
            bestVersion = version;
            bestTag = tagName;
            bestUrl = map['html_url'] as String?;
          }
        }
        if (bestVersion == null || bestTag == null || bestUrl == null) return null;

        final current = _parseSemver(currentVersion);
        if (current != null && _compare(bestVersion, current) <= 0) return null;

        return UpdateInfo(
          latestVersion: bestTag.substring('gazer-v'.length),
          currentVersion: currentVersion,
          releaseUrl: Uri.parse(bestUrl),
        );
      } catch (_) {
        return null;
      }
    }

    List<int>? _parseSemver(String v) {
      final match = _semverPrefix.firstMatch(v);
      if (match == null) return null;
      return [int.parse(match.group(1)!), int.parse(match.group(2)!), int.parse(match.group(3)!)];
    }

    int _compare(List<int> a, List<int> b) {
      for (var i = 0; i < 3; i++) {
        if (a[i] != b[i]) return a[i].compareTo(b[i]);
      }
      return 0;
    }
  }
  ```

- [ ] **Step 4: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/update_checker_test.dart"`
  Expected PASS: `00:0X +6: All tests passed!`

- [ ] **Step 5: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add lib/services/update_checker.dart test/services/update_checker_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): add UpdateChecker

  Polls GitHub Releases for penguintechinc/waddlebot, filters gazer-v*
  tags, semver-compares against the running version, and never throws
  (network/malformed responses resolve to null).

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 11: NativeEventBridge and PipelineController

**Files:**
- Create: `lib/services/native_event_bridge.dart`, `lib/services/pipeline_controller.dart`
- Create (helper, not a `_test.dart` — never auto-run by `flutter test`): `test/helpers/fake_host_api.dart`
- Test: `test/services/native_event_bridge_test.dart`, `test/services/pipeline_controller_test.dart`

**Interfaces:**
- Produces: `class NativeEventBridge implements GazerFlutterApi { Stream<StateEvent> get stateEvents; Stream<StatsSample> get stats; Stream<VideoDevice> get usbAttached; Stream<String> get usbDetached; Stream<bool> get authResults; void dispose(); }`; `class PipelineController { PipelineController({required GazerHostApi host, required NativeEventBridge events, required ReconnectPolicy policy, Future<void> Function(Duration) sleeper = Future.delayed}); Stream<PipelineState> get state; PipelineState get current; Stream<StreamStats> get stats; Future<void> goLive(GazerSettings settings, {required List<VideoDevice> devices, required String videoDeviceId, required FeatureFlags flags, OutputOrientation orientation = OutputOrientation.landscape}); Future<void> stop(); void dispose(); }`
- Consumes: `GazerHostApi`/`GazerFlutterApi`/`StreamConfig`/`StreamTarget`/`StateEvent`/`StatsSample`/`VideoDevice`/`OutputOrientation`/`NativePipelineState`/`GazerErrorCode` (Task 6), `PipelineState` hierarchy + `GazerError` (Task 4), `TargetValidator` (Task 5), `ReconnectPolicy` (Task 8), `FeatureFlags`/`FlagKeys` (Task 9), `StreamStats` (Task 4), `GazerSettings`/`AudioSourceChoice` (Task 4).

`goLive`'s `required FeatureFlags flags` and `OutputOrientation orientation = OutputOrientation.landscape`
parameters are additions beyond the contract's literal quoted `goLive` signature — see header
note 2. `stop()` has no real `Timer` to cancel: the injectable `sleeper` future is what stands in
for a timer, and cancellation is a `_cancelled` flag checked after the sleeper resolves.

`test/helpers/fake_host_api.dart`'s `FakeGazerHostApi` (Step 1 below) is Part C and Part E's
entire test surface onto this task's classes — its full shape: `implements GazerHostApi`;
`List<String> calls`; `List<StreamConfig> prepareCalls`; `List<StreamTarget> startCalls`; `int
stopCallCount`; `PrepareResult prepareResult` (settable, defaults `PrepareResult()..ok = true`);
`List<VideoDevice> videoDevices` (settable, defaults `[]`); `List<AudioDevice> audioDevices`
(settable, defaults `[]`); `final NativeEventBridge bridge`; `Future<void>
emitState(NativePipelineState state, {GazerErrorCode? error, String? detail})`; `Future<void>
emitStats(StatsSample sample)`. A widget/provider test that needs `emitState`/`emitStats` to
reach the `PipelineController` under test must override `pipelineControllerProvider` with
`PipelineController(host: fake, events: fake.bridge, policy: ReconnectPolicy())` — overriding
only `gazerHostApiProvider` leaves `fake.bridge` unconnected, since production
`pipelineControllerProvider` (Task 12) constructs its own `NativeEventBridge()`.

- [ ] **Step 1: Write the shared test helper `FakeGazerHostApi`**

  `test/helpers/fake_host_api.dart`:
  ```dart
  import 'package:gazer/pigeon/pipeline.g.dart';
  import 'package:gazer/services/native_event_bridge.dart';

  /// Test double for [GazerHostApi] that records every call it receives.
  ///
  /// Also owns a paired [bridge] (a [NativeEventBridge]) and `emitState`/
  /// `emitStats` helpers, so widget/provider tests can drive native-side
  /// push events without touching a real Pigeon channel. To wire this up,
  /// construct the [PipelineController] under test with `events:
  /// fake.bridge` (see Task 12's `pipelineControllerProvider` test) and
  /// override `pipelineControllerProvider.overrideWithValue(controller)` —
  /// `gazerHostApiProvider.overrideWithValue(fake)` alone does not connect
  /// the two, since production `pipelineControllerProvider` constructs its
  /// own internal `NativeEventBridge()`.
  class FakeGazerHostApi implements GazerHostApi {
    /// Every method name invoked, in call order (e.g. `'prepare'`, `'start'`).
    final List<String> calls = [];

    /// Every [StreamConfig] passed to [prepare], in call order.
    final List<StreamConfig> prepareCalls = [];

    /// Every [StreamTarget] passed to [start], in call order.
    final List<StreamTarget> startCalls = [];

    /// Number of times [stop] has been called.
    int stopCallCount = 0;

    /// Value [prepare] resolves to; tests can override to simulate failure.
    PrepareResult prepareResult = PrepareResult()..ok = true;

    /// Value [listVideoDevices] returns; empty by default, tests populate it
    /// to exercise device-dependent UI (e.g. `SourcePicker`, "Go Live"
    /// enablement).
    List<VideoDevice> videoDevices = <VideoDevice>[];

    /// Value [listAudioDevices] returns; empty by default.
    List<AudioDevice> audioDevices = <AudioDevice>[];

    /// Paired event bridge — see the class doc for how tests wire this to
    /// the `PipelineController` under test.
    final NativeEventBridge bridge = NativeEventBridge();

    /// Pushes a [StateEvent] into [bridge] as if the native side reported
    /// [state] (optionally with [error]/[detail]), then yields one
    /// microtask so listeners observe it before the caller continues.
    Future<void> emitState(NativePipelineState state, {GazerErrorCode? error, String? detail}) async {
      bridge.onStateChanged(StateEvent()
        ..state = state
        ..error = error
        ..detail = detail);
      await Future<void>.delayed(Duration.zero);
    }

    /// Pushes a [StatsSample] into [bridge], then yields one microtask so
    /// listeners observe it before the caller continues.
    Future<void> emitStats(StatsSample sample) async {
      bridge.onStats(sample);
      await Future<void>.delayed(Duration.zero);
    }

    @override
    List<VideoDevice> listVideoDevices() {
      calls.add('listVideoDevices');
      return videoDevices;
    }

    @override
    List<AudioDevice> listAudioDevices() {
      calls.add('listAudioDevices');
      return audioDevices;
    }

    @override
    Future<bool> requestUsbPermission(String deviceId) async {
      calls.add('requestUsbPermission($deviceId)');
      return false;
    }

    @override
    Future<PrepareResult> prepare(StreamConfig config) async {
      calls.add('prepare');
      prepareCalls.add(config);
      return prepareResult;
    }

    @override
    Future<void> start(StreamTarget target) async {
      calls.add('start');
      startCalls.add(target);
    }

    @override
    Future<void> stop() async {
      calls.add('stop');
      stopCallCount += 1;
    }

    @override
    void setVideoBitrate(int kbps) {
      calls.add('setVideoBitrate($kbps)');
    }

    @override
    NativePipelineState getState() {
      calls.add('getState');
      return NativePipelineState.idle;
    }
  }
  ```

- [ ] **Step 2: Write failing test for `NativeEventBridge`**

  `test/services/native_event_bridge_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/pigeon/pipeline.g.dart';
  import 'package:gazer/services/native_event_bridge.dart';

  void main() {
    late NativeEventBridge bridge;

    setUp(() {
      bridge = NativeEventBridge();
    });

    tearDown(() {
      bridge.dispose();
    });

    test('onStateChanged forwards to stateEvents', () async {
      final events = <StateEvent>[];
      final sub = bridge.stateEvents.listen(events.add);

      bridge.onStateChanged(StateEvent()..state = NativePipelineState.streaming);
      await Future<void>.delayed(Duration.zero);

      expect(events, hasLength(1));
      expect(events.single.state, NativePipelineState.streaming);
      await sub.cancel();
    });

    test('onStats forwards to stats', () async {
      final samples = <StatsSample>[];
      final sub = bridge.stats.listen(samples.add);

      bridge.onStats(StatsSample()
        ..bitrateKbps = 2000
        ..fps = 30
        ..droppedVideoFrames = 0
        ..sentBytes = 100
        ..congestionPercent = 0);
      await Future<void>.delayed(Duration.zero);

      expect(samples, hasLength(1));
      expect(samples.single.bitrateKbps, 2000);
      await sub.cancel();
    });

    test('onUsbAttached forwards to usbAttached', () async {
      final devices = <VideoDevice>[];
      final sub = bridge.usbAttached.listen(devices.add);

      bridge.onUsbAttached(VideoDevice()
        ..id = 'uvc:1'
        ..kind = VideoDeviceKind.uvcCamera2
        ..name = 'UGREEN Capture');
      await Future<void>.delayed(Duration.zero);

      expect(devices.single.id, 'uvc:1');
      await sub.cancel();
    });

    test('onUsbDetached forwards to usbDetached', () async {
      final ids = <String>[];
      final sub = bridge.usbDetached.listen(ids.add);

      bridge.onUsbDetached('uvc:1');
      await Future<void>.delayed(Duration.zero);

      expect(ids.single, 'uvc:1');
      await sub.cancel();
    });

    test('onAuthResult forwards to authResults', () async {
      final results = <bool>[];
      final sub = bridge.authResults.listen(results.add);

      bridge.onAuthResult(true);
      await Future<void>.delayed(Duration.zero);

      expect(results.single, isTrue);
      await sub.cancel();
    });
  }
  ```

- [ ] **Step 3: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/native_event_bridge_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/native_event_bridge.dart': No such file or directory`.

- [ ] **Step 4: Implement `lib/services/native_event_bridge.dart`**

  ```dart
  import 'dart:async';

  import '../pigeon/pipeline.g.dart';

  /// Concrete [GazerFlutterApi] implementation: turns Pigeon-delivered
  /// Kotlin -> Dart calls into broadcast streams the rest of the app
  /// listens to.
  ///
  /// Pigeon's codegen calls these override methods directly when a message
  /// arrives on the platform channel; nothing else in the app calls them
  /// except tests, which push events straight through to simulate native
  /// callbacks.
  class NativeEventBridge implements GazerFlutterApi {
    final StreamController<StateEvent> _stateController = StreamController<StateEvent>.broadcast();
    final StreamController<StatsSample> _statsController = StreamController<StatsSample>.broadcast();
    final StreamController<VideoDevice> _usbAttachedController =
        StreamController<VideoDevice>.broadcast();
    final StreamController<String> _usbDetachedController = StreamController<String>.broadcast();
    final StreamController<bool> _authResultController = StreamController<bool>.broadcast();

    /// Every native pipeline state transition.
    Stream<StateEvent> get stateEvents => _stateController.stream;

    /// Every 1Hz native statistics sample.
    Stream<StatsSample> get stats => _statsController.stream;

    /// Every UVC device attach event (M1: never fired).
    Stream<VideoDevice> get usbAttached => _usbAttachedController.stream;

    /// Every UVC device detach event (M1: never fired), by device id.
    Stream<String> get usbDetached => _usbDetachedController.stream;

    /// Every RTMP auth attempt result.
    Stream<bool> get authResults => _authResultController.stream;

    @override
    void onStateChanged(StateEvent event) => _stateController.add(event);

    @override
    void onStats(StatsSample sample) => _statsController.add(sample);

    @override
    void onUsbAttached(VideoDevice device) => _usbAttachedController.add(device);

    @override
    void onUsbDetached(String deviceId) => _usbDetachedController.add(deviceId);

    @override
    void onAuthResult(bool ok) => _authResultController.add(ok);

    /// Closes every underlying stream; call once, when the owner (typically
    /// `pipelineControllerProvider`) is disposed.
    void dispose() {
      _stateController.close();
      _statsController.close();
      _usbAttachedController.close();
      _usbDetachedController.close();
      _authResultController.close();
    }
  }
  ```

- [ ] **Step 5: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/native_event_bridge_test.dart"`
  Expected PASS: `00:0X +5: All tests passed!`

- [ ] **Step 6: Write failing test for `PipelineController`**

  `test/services/pipeline_controller_test.dart`:
  ```dart
  import 'dart:async';

  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/config/flag_keys.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/models/pipeline_state.dart';
  import 'package:gazer/models/quality.dart';
  import 'package:gazer/models/stream_stats.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/pigeon/pipeline.g.dart';
  import 'package:gazer/services/feature_flags.dart';
  import 'package:gazer/services/native_event_bridge.dart';
  import 'package:gazer/services/pipeline_controller.dart';
  import 'package:gazer/services/reconnect_policy.dart';

  import '../helpers/fake_host_api.dart';

  class _ManualSleeper {
    final List<Completer<void>> _pending = [];

    Future<void> call(Duration duration) {
      final completer = Completer<void>();
      _pending.add(completer);
      return completer.future;
    }

    void resolveNext() => _pending.removeAt(0).complete();

    int get pendingCount => _pending.length;
  }

  void main() {
    late FakeGazerHostApi host;
    late NativeEventBridge bridge;
    late _ManualSleeper sleeper;
    late PipelineController controller;

    final backCamera = VideoDevice()
      ..id = 'camera:back'
      ..kind = VideoDeviceKind.backCamera
      ..name = 'Back Camera';

    GazerSettings settingsWith({String? username, String? password}) => GazerSettings(
          target: StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            streamKey: 'demo-key-0001',
            username: username,
            password: password,
          ),
          quality: QualitySettings.defaults(),
          audio: AudioSourceChoice.auto,
          forceLibuvc: false,
        );

    FeatureFlags flagsWith({bool adaptiveBitrate = true, bool rtmpAuth = true}) =>
        FeatureFlags(LicenseState(
          status: LicenseStatus.valid,
          flags: {
            FlagKeys.cameraStream: true,
            FlagKeys.adaptiveBitrate: adaptiveBitrate,
            FlagKeys.rtmpAuth: rtmpAuth,
            FlagKeys.uvcCapture: false,
          },
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ));

    setUp(() {
      host = FakeGazerHostApi();
      bridge = NativeEventBridge();
      sleeper = _ManualSleeper();
      controller = PipelineController(
        host: host,
        events: bridge,
        policy: ReconnectPolicy(),
        sleeper: sleeper.call,
      );
    });

    tearDown(() {
      controller.dispose();
      bridge.dispose();
    });

    group('goLive validation', () {
      test('throws ArgumentError when the target url is invalid', () async {
        final settings = settingsWith().copyWith(
          target: const StreamTargetSettings(url: 'http://bad.example.com'),
        );
        expect(
          () => controller.goLive(
            settings,
            devices: [backCamera],
            videoDeviceId: 'camera:back',
            flags: flagsWith(),
          ),
          throwsArgumentError,
        );
      });

      test('rtmpAuth flag off with credentials throws ArgumentError', () async {
        final settings = settingsWith(username: 'demo', password: 'secret');
        expect(
          () => controller.goLive(
            settings,
            devices: [backCamera],
            videoDeviceId: 'camera:back',
            flags: flagsWith(rtmpAuth: false),
          ),
          throwsArgumentError,
        );
      });
    });

    group('goLive happy path', () {
      test('transitions Idle -> Preparing -> Ready -> Connecting -> Streaming', () async {
        final seen = <PipelineState>[];
        final sub = controller.state.listen(seen.add);

        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );
        bridge.onStateChanged(StateEvent()..state = NativePipelineState.streaming);
        await Future<void>.delayed(Duration.zero);

        expect(seen, [
          const PreparingState(),
          const ReadyState(),
          const ConnectingState(),
          const StreamingState(),
        ]);
        expect(controller.current, const StreamingState());
        await sub.cancel();
      });

      test('adaptive flag off forces StreamConfig.adaptiveBitrate to false', () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(adaptiveBitrate: false),
        );
        expect(host.prepareCalls.single.adaptiveBitrate, isFalse);
      });

      test('orientation param is passed through to StreamConfig', () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
          orientation: OutputOrientation.portrait,
        );
        expect(host.prepareCalls.single.orientation, OutputOrientation.portrait);
      });
    });

    group('reconnect on rtmpConnectFailed', () {
      test('emits ReconnectingState(1, delay) then retries start after the sleeper resolves', () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );
        final startCallsBefore = host.startCalls.length;

        bridge.onStateChanged(StateEvent()
          ..state = NativePipelineState.error
          ..error = GazerErrorCode.rtmpConnectFailed);
        await Future<void>.delayed(Duration.zero);

        expect(controller.current, isA<ReconnectingState>());
        expect((controller.current as ReconnectingState).attempt, 1);
        expect(sleeper.pendingCount, 1);
        expect(host.startCalls.length, startCallsBefore);

        sleeper.resolveNext();
        await Future<void>.delayed(Duration.zero);

        expect(host.startCalls.length, startCallsBefore + 1);
      });
    });

    group('rtmpAuthFailed', () {
      test('goes to ErrorState with no retry scheduled', () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );

        bridge.onStateChanged(StateEvent()
          ..state = NativePipelineState.error
          ..error = GazerErrorCode.rtmpAuthFailed);
        await Future<void>.delayed(Duration.zero);

        expect(controller.current, isA<ErrorState>());
        expect((controller.current as ErrorState).error.code, GazerErrorCode.rtmpAuthFailed);
        expect(sleeper.pendingCount, 0);
      });
    });

    group('reconnect exhaustion', () {
      test('after 10 retried attempts, the 11th failure is a terminal ErrorState', () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );

        for (var attempt = 1; attempt <= 10; attempt++) {
          bridge.onStateChanged(StateEvent()
            ..state = NativePipelineState.error
            ..error = GazerErrorCode.rtmpConnectFailed);
          await Future<void>.delayed(Duration.zero);
          expect(controller.current, isA<ReconnectingState>(), reason: 'attempt $attempt');
          sleeper.resolveNext();
          await Future<void>.delayed(Duration.zero);
        }

        bridge.onStateChanged(StateEvent()
          ..state = NativePipelineState.error
          ..error = GazerErrorCode.rtmpConnectFailed);
        await Future<void>.delayed(Duration.zero);

        expect(controller.current, isA<ErrorState>());
      });
    });

    group('stop during reconnect', () {
      test('cancels the pending retry: start is not called again', () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );
        final startCallsBefore = host.startCalls.length;

        bridge.onStateChanged(StateEvent()
          ..state = NativePipelineState.error
          ..error = GazerErrorCode.rtmpConnectFailed);
        await Future<void>.delayed(Duration.zero);

        await controller.stop();
        sleeper.resolveNext();
        await Future<void>.delayed(Duration.zero);

        expect(host.startCalls.length, startCallsBefore);
        expect(controller.current, const IdleState());
      });
    });

    group('stats aggregation', () {
      test('averages bitrate, tracks reconnectCount, and reports uptime while streaming', () async {
        final seen = <StreamStats>[];
        final sub = controller.stats.listen(seen.add);

        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );
        bridge.onStateChanged(StateEvent()..state = NativePipelineState.streaming);
        await Future<void>.delayed(Duration.zero);

        bridge.onStats(StatsSample()
          ..bitrateKbps = 2000
          ..fps = 30
          ..droppedVideoFrames = 0
          ..sentBytes = 1000
          ..congestionPercent = 0);
        await Future<void>.delayed(Duration.zero);
        bridge.onStats(StatsSample()
          ..bitrateKbps = 1000
          ..fps = 29
          ..droppedVideoFrames = 1
          ..sentBytes = 2000
          ..congestionPercent = 10);
        await Future<void>.delayed(Duration.zero);

        final latest = seen.last;
        expect(latest.currentBitrateKbps, 1000);
        expect(latest.averageBitrateKbps, 1500);
        expect(latest.droppedFrames, 1);
        expect(latest.sentBytes, 2000);
        expect(latest.uptime, greaterThanOrEqualTo(Duration.zero));

        bridge.onStateChanged(StateEvent()
          ..state = NativePipelineState.error
          ..error = GazerErrorCode.rtmpConnectFailed);
        await Future<void>.delayed(Duration.zero);

        expect(seen.last.reconnectCount, 1);
        await sub.cancel();
      });
    });
  }
  ```

- [ ] **Step 7: Run and confirm failure**

  `make mobile-run CMD="flutter test test/services/pipeline_controller_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/pipeline_controller.dart': No such file or directory`.

- [ ] **Step 8: Implement `lib/services/pipeline_controller.dart`**

  ```dart
  import 'dart:async';

  import '../config/flag_keys.dart';
  import '../models/gazer_settings.dart';
  import '../models/pipeline_state.dart';
  import '../models/stream_stats.dart';
  import '../models/validation_issue.dart';
  import '../pigeon/pipeline.g.dart';
  import 'feature_flags.dart';
  import 'native_event_bridge.dart';
  import 'reconnect_policy.dart';
  import 'target_validator.dart';

  /// Owns the Dart-side state machine on top of the native pipeline:
  /// validates settings, drives `prepare`/`start`/`stop`, maps native state
  /// events to [PipelineState], and runs the Dart-owned reconnect loop.
  ///
  /// Every decision (validation, source/audio selection, flag gating,
  /// reconnect timing, stats aggregation) lives here per the design's
  /// boundary rule — the native side only reports facts and takes commands.
  class PipelineController {
    PipelineController({
      required GazerHostApi host,
      required NativeEventBridge events,
      required ReconnectPolicy policy,
      Future<void> Function(Duration) sleeper = Future.delayed,
    })  : _host = host,
          _events = events,
          _policy = policy,
          _sleeper = sleeper {
      _stateSub = _events.stateEvents.listen(_onNativeStateEvent);
      _statsSub = _events.stats.listen(_onNativeStats);
    }

    final GazerHostApi _host;
    final NativeEventBridge _events;
    final ReconnectPolicy _policy;
    final Future<void> Function(Duration) _sleeper;

    final StreamController<PipelineState> _stateController =
        StreamController<PipelineState>.broadcast();
    final StreamController<StreamStats> _statsController =
        StreamController<StreamStats>.broadcast();

    late final StreamSubscription<StateEvent> _stateSub;
    late final StreamSubscription<StatsSample> _statsSub;

    PipelineState _current = const IdleState();
    StreamStats _statsSnapshot = StreamStats.zero();

    StreamTarget? _pendingTarget;
    int _reconnectAttempt = 0;
    bool _cancelled = false;
    DateTime? _streamStartedAt;
    final List<int> _bitrateSamples = [];

    /// Every [PipelineState] transition after subscription; late subscribers
    /// do not receive states emitted before they listened — combine with
    /// [current] at the call site (see `pipelineStateProvider`, Task 12).
    Stream<PipelineState> get state => _stateController.stream;

    /// The current state, synchronously.
    PipelineState get current => _current;

    /// Every [StreamStats] update after subscription.
    Stream<StreamStats> get stats => _statsController.stream;

    /// Validates [settings], builds a [StreamConfig], and starts streaming
    /// to `TargetValidator.effectiveUrl(settings.target)`.
    ///
    /// Throws [ArgumentError] if [TargetValidator.validate] reports any
    /// issue, if [videoDeviceId] is not one of [devices], or if credentials
    /// are set while `FlagKeys.rtmpAuth` is off in [flags]. Adaptive bitrate
    /// is only honoured when `FlagKeys.adaptiveBitrate` is on in [flags];
    /// credentials are only forwarded to the native `start()` call when
    /// `FlagKeys.rtmpAuth` is on.
    Future<void> goLive(
      GazerSettings settings, {
      required List<VideoDevice> devices,
      required String videoDeviceId,
      required FeatureFlags flags,
      OutputOrientation orientation = OutputOrientation.landscape,
    }) async {
      final issues = const TargetValidator().validate(settings.target);
      final hasCredentials =
          (settings.target.username ?? '').isNotEmpty || (settings.target.password ?? '').isNotEmpty;
      if (hasCredentials && !flags.isEnabled(FlagKeys.rtmpAuth)) {
        issues.add(const ValidationIssue(field: 'auth', messageKey: 'rtmpAuthDisabled'));
      }
      if (!devices.any((d) => d.id == videoDeviceId)) {
        issues.add(const ValidationIssue(field: 'videoDeviceId', messageKey: 'errorDeviceNotFound'));
      }
      if (issues.isNotEmpty) {
        throw ArgumentError(issues.map((i) => '${i.field}:${i.messageKey}').join(', '));
      }

      _cancelled = false;
      _reconnectAttempt = 0;
      _streamStartedAt = null;
      _bitrateSamples.clear();
      _statsSnapshot = StreamStats.zero();
      _statsController.add(_statsSnapshot);

      final adaptive = settings.quality.adaptiveBitrate && flags.isEnabled(FlagKeys.adaptiveBitrate);
      final config = StreamConfig()
        ..videoDeviceId = videoDeviceId
        ..audioDeviceId = _audioDeviceIdFor(settings.audio)
        ..width = settings.quality.resolution.width
        ..height = settings.quality.resolution.height
        ..fps = settings.quality.frameRate.value
        ..videoBitrateKbps = settings.quality.videoBitrateKbps
        ..adaptiveBitrate = adaptive
        ..audioBitrateKbps = kAudioBitrateKbps
        ..orientation = orientation;

      final sendCredentials = flags.isEnabled(FlagKeys.rtmpAuth);
      _pendingTarget = StreamTarget()
        ..url = TargetValidator.effectiveUrl(settings.target)
        ..username = sendCredentials ? settings.target.username : null
        ..password = sendCredentials ? settings.target.password : null;

      _emit(const PreparingState());
      await _host.prepare(config);
      _emit(const ReadyState());
      _emit(const ConnectingState());
      await _host.start(_pendingTarget!);
    }

    /// Requests a clean stop and cancels any pending reconnect retry.
    Future<void> stop() async {
      _cancelled = true;
      _emit(const StoppingState());
      await _host.stop();
      _emit(const IdleState());
    }

    /// M1 has no UVC/USB audio path: `usbAudio` and `auto` both resolve to
    /// the phone mic; `silence` resolves to the muted source.
    String _audioDeviceIdFor(AudioSourceChoice choice) {
      switch (choice) {
        case AudioSourceChoice.auto:
        case AudioSourceChoice.mic:
        case AudioSourceChoice.usbAudio:
          return 'audio:mic';
        case AudioSourceChoice.silence:
          return 'audio:silence';
      }
    }

    void _onNativeStateEvent(StateEvent event) {
      switch (event.state) {
        case NativePipelineState.idle:
          if (!_cancelled) _emit(const IdleState());
        case NativePipelineState.preparing:
          _emit(const PreparingState());
        case NativePipelineState.ready:
          _emit(const ReadyState());
        case NativePipelineState.connecting:
          _emit(const ConnectingState());
        case NativePipelineState.streaming:
          _streamStartedAt ??= DateTime.now();
          _emit(const StreamingState());
        case NativePipelineState.stopping:
          _emit(const StoppingState());
        case NativePipelineState.error:
          _handleError(event.error ?? GazerErrorCode.unknown, event.detail);
      }
    }

    void _handleError(GazerErrorCode code, String? detail) {
      if (_cancelled) {
        _emit(const IdleState());
        return;
      }
      if (_policy.shouldRetry(code)) {
        _reconnectAttempt += 1;
        final delay = _policy.delayFor(_reconnectAttempt);
        if (delay == null) {
          _emit(ErrorState(GazerError(code: code, detail: detail)));
          return;
        }
        _statsSnapshot = _statsSnapshot.copyWith(reconnectCount: _statsSnapshot.reconnectCount + 1);
        _statsController.add(_statsSnapshot);
        _emit(ReconnectingState(_reconnectAttempt, delay));
        unawaited(_retryAfter(delay));
      } else {
        _emit(ErrorState(GazerError(code: code, detail: detail)));
      }
    }

    Future<void> _retryAfter(Duration delay) async {
      await _sleeper(delay);
      if (_cancelled || _pendingTarget == null) return;
      _emit(const ConnectingState());
      await _host.start(_pendingTarget!);
    }

    void _onNativeStats(StatsSample sample) {
      _bitrateSamples.add(sample.bitrateKbps);
      final average = _bitrateSamples.reduce((a, b) => a + b) / _bitrateSamples.length;
      final uptime = _streamStartedAt == null ? Duration.zero : DateTime.now().difference(_streamStartedAt!);
      _statsSnapshot = _statsSnapshot.copyWith(
        currentBitrateKbps: sample.bitrateKbps,
        averageBitrateKbps: average.round(),
        fps: sample.fps,
        droppedFrames: sample.droppedVideoFrames,
        sentBytes: sample.sentBytes,
        uptime: uptime,
        congestionPercent: sample.congestionPercent,
      );
      _statsController.add(_statsSnapshot);
    }

    void _emit(PipelineState next) {
      _current = next;
      _stateController.add(next);
    }

    /// Cancels native-event subscriptions and closes both broadcast streams.
    void dispose() {
      _stateSub.cancel();
      _statsSub.cancel();
      _stateController.close();
      _statsController.close();
    }
  }
  ```

- [ ] **Step 9: Run and confirm pass**

  `make mobile-run CMD="flutter test test/services/pipeline_controller_test.dart"`
  Expected PASS: `00:0X +10: All tests passed!`

- [ ] **Step 10: Regression-check the whole services suite**

  `make mobile-run CMD="flutter test test/services/"` → PASS, all suites from Tasks 5, 7, 8, 9, 10, 11 green together.

- [ ] **Step 11: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 12: Commit**

  ```bash
  git add lib/services/native_event_bridge.dart lib/services/pipeline_controller.dart \
    test/helpers/fake_host_api.dart test/services/native_event_bridge_test.dart \
    test/services/pipeline_controller_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): add NativeEventBridge and PipelineController

  NativeEventBridge turns Pigeon GazerFlutterApi callbacks into broadcast
  streams; PipelineController drives goLive/stop, maps native state to
  the Dart PipelineState machine, runs the Dart-owned reconnect loop via
  an injectable sleeper, and aggregates StreamStats. goLive gates
  adaptive bitrate and RTMP auth on FeatureFlags per the design's Go
  Live enablement rule.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 12: Riverpod providers

**Files:**
- Create: `lib/providers/settings_provider.dart`, `lib/providers/license_provider.dart`, `lib/providers/connectivity_provider.dart`, `lib/providers/devices_provider.dart`, `lib/providers/pipeline_provider.dart`, `lib/providers/update_provider.dart`
- Test: `test/providers/settings_provider_test.dart`, `test/providers/license_provider_test.dart`, `test/providers/connectivity_provider_test.dart`, `test/providers/devices_provider_test.dart`, `test/providers/pipeline_provider_test.dart`, `test/providers/update_provider_test.dart`

**Interfaces:**
- Produces exactly the providers named in the shared contract: `SettingsNotifier` (class-based, `build()`/`update()`), `license(Ref)`, `featureFlags(Ref)`, `isOnline(Ref)`, `videoDevices(Ref)`, `audioDevices(Ref)`, `pipelineController(Ref)`, `pipelineState(Ref)`, `streamStats(Ref)`, `updateInfo(Ref)`, plus the overridable leaf providers `gazerHostApiProvider`, `settingsRepositoryProvider`, `licenseClientProvider`, `updateCheckerProvider`, `connectivityProvider`.
- Consumes: every service/model from Tasks 4-11, `package:riverpod_annotation/riverpod_annotation.dart`, `package:flutter_riverpod/flutter_riverpod.dart` (tests), `package:connectivity_plus/connectivity_plus.dart`, `package:device_info_plus/device_info_plus.dart`, `package:package_info_plus/package_info_plus.dart`.

This task's codegen step uses the full `make mobile-codegen` composite (unlike Task 4): by now
`pigeons/pipeline.dart` exists (Task 6), so the `dart run pigeon` stage succeeds, and
`build_runner` generates every `.g.dart` part file — freezed/json_serializable (Tasks 4/7/9) and
riverpod_generator (this task) — in one pass. `pipelineState`/`streamStats` seed each new
subscriber with the controller's current value (`PipelineController.current`) or
`StreamStats.zero()` before following the controller's stream, since `PipelineController` itself
only exposes a bare `Stream` + a synchronous `current`/(no stats getter) pair, not a replay-aware
stream — see the two providers' bodies below.

- [ ] **Step 1: Write failing test for `SettingsNotifier`**

  `test/providers/settings_provider_test.dart`:
  ```dart
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/providers/settings_provider.dart';
  import 'package:gazer/services/settings_repository.dart';

  class _FakeSettingsRepository implements SettingsRepository {
    GazerSettings stored = GazerSettings.defaults();
    int saveCallCount = 0;

    @override
    Future<GazerSettings> load() async => stored;

    @override
    Future<void> save(GazerSettings s) async {
      saveCallCount += 1;
      stored = s;
    }
  }

  void main() {
    test('SettingsNotifier.build loads from the repository', () async {
      final repo = _FakeSettingsRepository();
      final container = ProviderContainer(
        overrides: [settingsRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      final loaded = await container.read(settingsNotifierProvider.future);

      expect(loaded, GazerSettings.defaults());
    });

    test('SettingsNotifier.update persists via the repository and updates state', () async {
      final repo = _FakeSettingsRepository();
      final container = ProviderContainer(
        overrides: [settingsRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(settingsNotifierProvider.future);
      final defaults = GazerSettings.defaults();
      final updated = defaults.copyWith(
        quality: defaults.quality.copyWith(videoBitrateKbps: 3000),
      );

      await container.read(settingsNotifierProvider.notifier).update(updated);

      expect(repo.saveCallCount, 1);
      expect(repo.stored, updated);
      expect(container.read(settingsNotifierProvider).value, updated);
    });
  }
  ```

- [ ] **Step 2: Run and confirm failure**

  `make mobile-run CMD="flutter test test/providers/settings_provider_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/providers/settings_provider.dart': No such file or directory`.

- [ ] **Step 3: Implement `lib/providers/settings_provider.dart`**

  ```dart
  import 'package:flutter_secure_storage/flutter_secure_storage.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../models/gazer_settings.dart';
  import '../services/settings_repository.dart';

  part 'settings_provider.g.dart';

  /// The [SettingsRepository] implementation the app uses; overridden in
  /// tests with a fake so [SettingsNotifier] never touches real storage.
  @Riverpod(keepAlive: true)
  SettingsRepository settingsRepository(Ref ref) => SecureSettingsRepository(
        secure: const FlutterSecureStorage(),
        prefs: SharedPreferencesAsync(),
      );

  /// Loads, holds, and persists the user's [GazerSettings].
  ///
  /// `keepAlive: true` because settings must survive navigation between
  /// HomeScreen and SettingsScreen without re-reading storage on every visit.
  @Riverpod(keepAlive: true)
  class SettingsNotifier extends _$SettingsNotifier {
    @override
    Future<GazerSettings> build() => ref.watch(settingsRepositoryProvider).load();

    /// Persists [s] via the repository and updates provider state so every
    /// listener (HomeScreen enablement, StatusPanel) sees the new settings.
    Future<void> update(GazerSettings s) async {
      await ref.read(settingsRepositoryProvider).save(s);
      state = AsyncData(s);
    }
  }
  ```

- [ ] **Step 4: Generate and run**

  `make mobile-codegen` → succeeds (generates `settings_provider.g.dart`).
  `make mobile-run CMD="flutter test test/providers/settings_provider_test.dart"` → PASS.

- [ ] **Step 5: Write failing test for `devicesProvider`/`gazerHostApiProvider`**

  `test/providers/devices_provider_test.dart`:
  ```dart
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/providers/devices_provider.dart';

  import '../helpers/fake_host_api.dart';

  void main() {
    test('videoDevicesProvider forwards GazerHostApi.listVideoDevices()', () async {
      final host = FakeGazerHostApi();
      final container = ProviderContainer(
        overrides: [gazerHostApiProvider.overrideWithValue(host)],
      );
      addTearDown(container.dispose);

      final devices = await container.read(videoDevicesProvider.future);

      expect(devices, isEmpty);
      expect(host.calls, contains('listVideoDevices'));
    });

    test('audioDevicesProvider forwards GazerHostApi.listAudioDevices()', () async {
      final host = FakeGazerHostApi();
      final container = ProviderContainer(
        overrides: [gazerHostApiProvider.overrideWithValue(host)],
      );
      addTearDown(container.dispose);

      final devices = await container.read(audioDevicesProvider.future);

      expect(devices, isEmpty);
      expect(host.calls, contains('listAudioDevices'));
    });
  }
  ```

- [ ] **Step 6: Run and confirm failure**

  `make mobile-run CMD="flutter test test/providers/devices_provider_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/providers/devices_provider.dart': No such file or directory`.

- [ ] **Step 7: Implement `lib/providers/devices_provider.dart`**

  ```dart
  import 'package:riverpod_annotation/riverpod_annotation.dart';

  import '../pigeon/pipeline.g.dart';

  part 'devices_provider.g.dart';

  /// The [GazerHostApi] the app talks to; overridden in tests with
  /// `FakeGazerHostApi` so no real Pigeon channel is ever touched.
  @Riverpod(keepAlive: true)
  GazerHostApi gazerHostApi(Ref ref) => GazerHostApi();

  /// Enumerable video sources (M1: back/front camera only).
  @riverpod
  Future<List<VideoDevice>> videoDevices(Ref ref) async {
    final host = ref.watch(gazerHostApiProvider);
    return host.listVideoDevices();
  }

  /// Enumerable audio sources (M1: mic + silence only).
  @riverpod
  Future<List<AudioDevice>> audioDevices(Ref ref) async {
    final host = ref.watch(gazerHostApiProvider);
    return host.listAudioDevices();
  }
  ```

- [ ] **Step 8: Generate and run**

  `make mobile-codegen` → succeeds. `make mobile-run CMD="flutter test test/providers/devices_provider_test.dart"` → PASS.

- [ ] **Step 9: Write failing test for `connectivityProvider`/`isOnlineProvider`**

  `test/providers/connectivity_provider_test.dart`:
  ```dart
  import 'package:connectivity_plus/connectivity_plus.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/providers/connectivity_provider.dart';
  import 'package:mocktail/mocktail.dart';

  class _MockConnectivity extends Mock implements Connectivity {}

  void main() {
    test('isOnlineProvider is true when any result is not none', () async {
      final connectivity = _MockConnectivity();
      when(() => connectivity.onConnectivityChanged).thenAnswer(
        (_) => Stream.value([ConnectivityResult.wifi]),
      );
      final container = ProviderContainer(
        overrides: [connectivityProvider.overrideWithValue(connectivity)],
      );
      addTearDown(container.dispose);

      final result = await container.read(isOnlineProvider.future);

      expect(result, isTrue);
    });

    test('isOnlineProvider is false when the only result is none', () async {
      final connectivity = _MockConnectivity();
      when(() => connectivity.onConnectivityChanged).thenAnswer(
        (_) => Stream.value([ConnectivityResult.none]),
      );
      final container = ProviderContainer(
        overrides: [connectivityProvider.overrideWithValue(connectivity)],
      );
      addTearDown(container.dispose);

      final result = await container.read(isOnlineProvider.future);

      expect(result, isFalse);
    });
  }
  ```

- [ ] **Step 10: Run and confirm failure**

  `make mobile-run CMD="flutter test test/providers/connectivity_provider_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/providers/connectivity_provider.dart': No such file or directory`.

- [ ] **Step 11: Implement `lib/providers/connectivity_provider.dart`**

  ```dart
  import 'package:connectivity_plus/connectivity_plus.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';

  part 'connectivity_provider.g.dart';

  /// The [Connectivity] instance the app queries; overridden in tests with a
  /// mock that emits a scripted sequence of results.
  @Riverpod(keepAlive: true)
  Connectivity connectivity(Ref ref) => Connectivity();

  /// Online/offline indicator shown in the status panel: true whenever the
  /// device reports any connectivity result other than [ConnectivityResult.none].
  @riverpod
  Stream<bool> isOnline(Ref ref) {
    final connectivityInstance = ref.watch(connectivityProvider);
    return connectivityInstance.onConnectivityChanged.map(
      (results) => results.any((r) => r != ConnectivityResult.none),
    );
  }
  ```

- [ ] **Step 12: Generate and run**

  `make mobile-codegen` → succeeds. `make mobile-run CMD="flutter test test/providers/connectivity_provider_test.dart"` → PASS.

- [ ] **Step 13: Write failing test for `licenseClientProvider`/`licenseProvider`/`featureFlagsProvider`**

  `test/providers/license_provider_test.dart`:
  ```dart
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/services/license_client.dart';

  class _FakeLicenseClient implements LicenseClient {
    _FakeLicenseClient(this.result);

    final LicenseState result;

    @override
    Future<LicenseState> validateAndFetchFlags() async => result;

    @override
    Future<void> keepalive() async {}
  }

  void main() {
    test('featureFlagsProvider derives isEnabled from licenseProvider', () async {
      final state = LicenseState(
        status: LicenseStatus.valid,
        flags: const {'waddlebot.gazer.camera-stream': true},
        lastFetched: DateTime.utc(2026, 9, 7),
        deviceId: 'device-abc',
      );
      final container = ProviderContainer(
        overrides: [
          licenseClientProvider.overrideWith((ref) async => _FakeLicenseClient(state)),
        ],
      );
      addTearDown(container.dispose);

      await container.read(licenseProvider.future);
      final flags = container.read(featureFlagsProvider);

      expect(flags.isEnabled('waddlebot.gazer.camera-stream'), isTrue);
      expect(flags.isEnabled('waddlebot.gazer.uvc-capture'), isFalse);
      expect(flags.hasFetchedOnce, isTrue);
    });

    test('featureFlagsProvider defaults every flag OFF before the fetch resolves', () async {
      final container = ProviderContainer(
        overrides: [
          licenseClientProvider.overrideWith(
            (ref) async => _FakeLicenseClient(LicenseState.initial('device-abc')),
          ),
        ],
      );
      addTearDown(container.dispose);

      final flags = container.read(featureFlagsProvider);

      expect(flags.isEnabled('waddlebot.gazer.camera-stream'), isFalse);
      expect(flags.hasFetchedOnce, isFalse);
    });
  }
  ```

- [ ] **Step 14: Run and confirm failure**

  `make mobile-run CMD="flutter test test/providers/license_provider_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/providers/license_provider.dart': No such file or directory`.

- [ ] **Step 15: Implement `lib/providers/license_provider.dart`**

  ```dart
  import 'package:device_info_plus/device_info_plus.dart';
  import 'package:dio/dio.dart';
  import 'package:package_info_plus/package_info_plus.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../models/license_state.dart';
  import '../services/device_id.dart';
  import '../services/feature_flags.dart';
  import '../services/license_client.dart';

  part 'license_provider.g.dart';

  /// Constructs the [LicenseClient] the app talks to; overridden with a fake
  /// in tests so no real HTTP call or platform channel is ever hit.
  @Riverpod(keepAlive: true)
  Future<LicenseClient> licenseClient(Ref ref) async {
    final packageInfo = await PackageInfo.fromPlatform();
    final deviceIdProvider = AndroidDeviceIdProvider(
      deviceInfo: DeviceInfoPlugin(),
      packageInfo: packageInfo,
    );
    return LicenseClient(
      dio: Dio(),
      cache: LicenseCache(SharedPreferencesAsync()),
      deviceIdProvider: deviceIdProvider,
      now: DateTime.now,
    );
  }

  /// Validates the license and fetches feature flags once at startup.
  ///
  /// `keepAlive: true`: a single validation per app session, not re-fetched
  /// on every screen visit — the app shell's separate keepalive timer is
  /// what refreshes staleness while foregrounded.
  @Riverpod(keepAlive: true)
  Future<LicenseState> license(Ref ref) async {
    final client = await ref.watch(licenseClientProvider.future);
    return client.validateAndFetchFlags();
  }

  /// Read-only view over [license] for flag checks; never throws — while
  /// [license] is loading or has errored, flags default to all-OFF via
  /// [LicenseState.initial]'s empty flag map, since [FeatureFlags.isEnabled]
  /// treats an absent key as OFF.
  @riverpod
  FeatureFlags featureFlags(Ref ref) {
    final asyncState = ref.watch(licenseProvider);
    final state = asyncState.valueOrNull ?? LicenseState.initial('');
    return FeatureFlags(state);
  }
  ```

- [ ] **Step 16: Generate and run**

  `make mobile-codegen` → succeeds. `make mobile-run CMD="flutter test test/providers/license_provider_test.dart"` → PASS.

- [ ] **Step 17: Write failing test for `updateCheckerProvider`/`updateInfoProvider`**

  `test/providers/update_provider_test.dart`:
  ```dart
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/update_info.dart';
  import 'package:gazer/providers/update_provider.dart';
  import 'package:gazer/services/update_checker.dart';

  class _FakeUpdateChecker implements UpdateChecker {
    _FakeUpdateChecker(this.result);

    final UpdateInfo? result;

    @override
    Future<UpdateInfo?> check() async => result;

    @override
    String get currentVersion => '1.0.0';

    @override
    String get releasesUrl => 'https://example.com';
  }

  void main() {
    test('updateInfoProvider forwards UpdateChecker.check()', () async {
      final info = UpdateInfo(
        latestVersion: '1.1.0',
        currentVersion: '1.0.0',
        releaseUrl: Uri.parse('https://example.com/release'),
      );
      final container = ProviderContainer(
        overrides: [updateCheckerProvider.overrideWith((ref) async => _FakeUpdateChecker(info))],
      );
      addTearDown(container.dispose);

      final result = await container.read(updateInfoProvider.future);

      expect(result, info);
    });

    test('updateInfoProvider is null when no update is available', () async {
      final container = ProviderContainer(
        overrides: [updateCheckerProvider.overrideWith((ref) async => _FakeUpdateChecker(null))],
      );
      addTearDown(container.dispose);

      final result = await container.read(updateInfoProvider.future);

      expect(result, isNull);
    });
  }
  ```

- [ ] **Step 18: Run and confirm failure**

  `make mobile-run CMD="flutter test test/providers/update_provider_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/providers/update_provider.dart': No such file or directory`.

- [ ] **Step 19: Implement `lib/providers/update_provider.dart`**

  ```dart
  import 'package:dio/dio.dart';
  import 'package:package_info_plus/package_info_plus.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';

  import '../models/update_info.dart';
  import '../services/update_checker.dart';

  part 'update_provider.g.dart';

  /// The [UpdateChecker] the app uses; overridden in tests with one wired to
  /// a mocked Dio.
  @Riverpod(keepAlive: true)
  Future<UpdateChecker> updateChecker(Ref ref) async {
    final packageInfo = await PackageInfo.fromPlatform();
    return UpdateChecker(dio: Dio(), currentVersion: packageInfo.version);
  }

  /// Startup, non-blocking update check surfaced in the status panel.
  @riverpod
  Future<UpdateInfo?> updateInfo(Ref ref) async {
    final checker = await ref.watch(updateCheckerProvider.future);
    return checker.check();
  }
  ```

- [ ] **Step 20: Generate and run**

  `make mobile-codegen` → succeeds. `make mobile-run CMD="flutter test test/providers/update_provider_test.dart"` → PASS.

- [ ] **Step 21: Write failing test for `pipelineControllerProvider`/`pipelineStateProvider`**

  `test/providers/pipeline_provider_test.dart`:
  ```dart
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/pipeline_state.dart';
  import 'package:gazer/pigeon/pipeline.g.dart';
  import 'package:gazer/providers/devices_provider.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/services/native_event_bridge.dart';
  import 'package:gazer/services/pipeline_controller.dart';
  import 'package:gazer/services/reconnect_policy.dart';

  import '../helpers/fake_host_api.dart';

  void main() {
    test('pipelineStateProvider emits the controller current state, then follows its stream', () async {
      final host = FakeGazerHostApi();
      final bridge = NativeEventBridge();
      final controller = PipelineController(host: host, events: bridge, policy: ReconnectPolicy());
      final container = ProviderContainer(
        overrides: [
          gazerHostApiProvider.overrideWithValue(host),
          pipelineControllerProvider.overrideWithValue(controller),
        ],
      );
      addTearDown(container.dispose);
      addTearDown(bridge.dispose);

      final seen = <PipelineState>[];
      final sub = container.listen(
        pipelineStateProvider,
        (previous, next) => next.whenData(seen.add),
        fireImmediately: true,
      );
      await Future<void>.delayed(Duration.zero);

      bridge.onStateChanged(StateEvent()..state = NativePipelineState.preparing);
      await Future<void>.delayed(Duration.zero);

      expect(seen.first, const IdleState());
      expect(seen.last, const PreparingState());
      sub.close();
    });
  }
  ```

- [ ] **Step 22: Run and confirm failure**

  `make mobile-run CMD="flutter test test/providers/pipeline_provider_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/providers/pipeline_provider.dart': No such file or directory`.

- [ ] **Step 23: Implement `lib/providers/pipeline_provider.dart`**

  ```dart
  import 'package:riverpod_annotation/riverpod_annotation.dart';

  import '../models/pipeline_state.dart';
  import '../models/stream_stats.dart';
  import '../services/native_event_bridge.dart';
  import '../services/pipeline_controller.dart';
  import '../services/reconnect_policy.dart';
  import 'devices_provider.dart';

  part 'pipeline_provider.g.dart';

  /// Owns the [PipelineController] for the app's lifetime; overridden in
  /// provider/widget tests with a controller wired to `FakeGazerHostApi`.
  @Riverpod(keepAlive: true)
  PipelineController pipelineController(Ref ref) {
    final controller = PipelineController(
      host: ref.watch(gazerHostApiProvider),
      events: NativeEventBridge(),
      policy: ReconnectPolicy(),
    );
    ref.onDispose(controller.dispose);
    return controller;
  }

  /// Live [PipelineState] stream, seeded with the controller's current
  /// value so a new subscriber never waits for the next native event to
  /// render — `PipelineController.state` alone does not replay past events.
  @riverpod
  Stream<PipelineState> pipelineState(Ref ref) async* {
    final controller = ref.watch(pipelineControllerProvider);
    yield controller.current;
    yield* controller.state;
  }

  /// Live [StreamStats] stream, seeded with the zero snapshot the same way
  /// [pipelineState] is seeded with the controller's current state.
  @riverpod
  Stream<StreamStats> streamStats(Ref ref) async* {
    final controller = ref.watch(pipelineControllerProvider);
    yield StreamStats.zero();
    yield* controller.stats;
  }
  ```

- [ ] **Step 24: Generate and run**

  `make mobile-codegen` → succeeds. `make mobile-run CMD="flutter test test/providers/pipeline_provider_test.dart"` → PASS.

- [ ] **Step 25: Regression-check the whole providers suite**

  `make mobile-run CMD="flutter test test/providers/"` → PASS, all six suites green together.

- [ ] **Step 26: Full Dart suite regression check**

  `make mobile-test` → PASS: every suite from Tasks 4-12 green, coverage gate ≥90% (the
  `scripts/coverage_gate.sh` from Task 1 asserts a non-zero denominator of files examined).

- [ ] **Step 27: Lint**

  `make mobile-lint` → PASS.

- [ ] **Step 28: Commit**

  ```bash
  git add lib/providers/ test/providers/
  git commit -m "$(cat <<'EOF'
  feat(gazer): add Riverpod providers

  Adds settingsRepositoryProvider/SettingsNotifier, gazerHostApiProvider/
  videoDevicesProvider/audioDevicesProvider, connectivityProvider/
  isOnlineProvider, licenseClientProvider/licenseProvider/
  featureFlagsProvider, updateCheckerProvider/updateInfoProvider, and
  pipelineControllerProvider/pipelineStateProvider/streamStatsProvider,
  wiring every Task 4-11 service into the app via overridable leaf
  providers for tests.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---


# Part C — Tasks 13–16: Flutter UI (Gazer Mobile 2.0 M1)

> Continues the plan started by writer A. Tasks 1–12 are assumed complete: toolchain + make
> targets, scaffold with all pins, every model/service/provider named in the SHARED CONTRACT,
> and `test/helpers/fake_host_api.dart` (`FakeGazerHostApi`, Task 11).

## Contract assumptions Part C relies on (Tasks 1–12 own the actual definitions)

Task 12's exact file contents are not visible to this writer. Where the SHARED CONTRACT names a
provider or test double but Task 12/11 owns its file placement or internal shape, Part C makes
the following explicit, minimal assumptions so every import path and test call below is a real
name, never an invented one:

1. **l10n output**: l10n.yaml has no output-dir override, so `flutter gen-l10n` writes
   `lib/l10n/app_localizations.dart` (Flutter 3.47 default: output goes into the arb dir)
   (run by `make mobile-codegen`) — imported here as `l10n/app_localizations.dart` (relative)
   or `package:gazer/l10n/app_localizations.dart`.
2. **Leaf-provider file placement** (Task 9/12): each overridable leaf provider lives beside its
   primary consumer, per the file map — `gazerHostApiProvider` in `lib/providers/devices_provider.dart`
   (Task 9; `pipelineControllerProvider` in `lib/providers/pipeline_provider.dart` imports it from
   there — every file that overrides `gazerHostApiProvider` must import `devices_provider.dart`
   directly, not just `pipeline_provider.dart`), `settingsRepositoryProvider`
   in `lib/providers/settings_provider.dart`, `licenseClientProvider`
   in `lib/providers/license_provider.dart`, `updateCheckerProvider` in `lib/providers/update_provider.dart`,
   `connectivityProvider` (raw `Connectivity` plugin instance) and `isOnlineProvider` (the
   `Stream<bool>` UI/tests actually consume) both in `lib/providers/connectivity_provider.dart`.
3. **`FakeGazerHostApi` test surface** (Task 11): beyond the `GazerHostApi` methods it fakes, it
   exposes `List<StreamConfig> prepareCalls`, `List<StreamTarget> startCalls`, settable
   `List<VideoDevice> videoDevices` / `List<AudioDevice> audioDevices` (both default `[]` —
   `listVideoDevices()`/`listAudioDevices()` return them), a `final NativeEventBridge bridge`,
   `Future<void> emitState(NativePipelineState state, {GazerErrorCode? error, String? detail})`,
   and `Future<void> emitStats(StatsSample sample)` — the hooks Task 11 built specifically so UI
   widget tests (this part) can drive `PipelineController`'s state/stats streams without a real
   native side. `prepare()` defaults to `PrepareResult()..ok = true` (negotiated fields left
   null — nothing in Part C reads them). **Wiring requirement**: `emitState`/`emitStats` only
   reach the `PipelineController` under test if that test's `overrides()` also overrides
   `pipelineControllerProvider.overrideWithValue(PipelineController(host: hostApi, events:
   hostApi.bridge, policy: ReconnectPolicy()))` — overriding `gazerHostApiProvider` alone leaves
   `hostApi.bridge` unconnected, since production `pipelineControllerProvider` (Task 12)
   constructs its own `NativeEventBridge()`. Devices default to empty; any test whose UI
   needs a populated device list (e.g. `SourcePicker`, "Go Live" enablement) sets
   `hostApi.videoDevices = [...]` in its own `setUp`/test body before pumping.
4. **`TargetValidator.validate()` messageKey values** (Task 5): `'errorUrlScheme'`,
   `'errorUrlHost'`, `'errorUrlPath'`, `'errorAuthBothOrNeither'` — `ValidationIssue` is declared
   in `lib/models/validation_issue.dart` (Task 4) and merely imported by `target_validator.dart`;
   screens import it directly. `validateGazerSettings` (Task 14, `lib/services/settings_validation.dart`)
   additionally emits `messageKey: 'rtmpAuthDisabled'` (no `error` prefix) for the license-gated auth check.
5. **Riverpod codegen naming**: `@riverpod`/`@Riverpod` functions/classes generate a provider
   named `<name>Provider` (e.g. `license(Ref ref)` → `licenseProvider`), per riverpod_generator
   4.0.9 convention — matches every provider name the SHARED CONTRACT already uses verbatim.

Every task below still lists its own `Consumes` precisely so a reviewer can check these
assumptions against the real Task 11/12 output when it lands.

---

### Task 13: App shell, router, theme, localization

**Files:**
- Create: `mobile/gazer/lib/main.dart`
- Create: `mobile/gazer/lib/app.dart`
- Modify: `mobile/gazer/lib/l10n/app_en.arb` (Task 2 seeded a placeholder template; this task
  replaces it with every string Tasks 13–16 use)
- Create: `mobile/gazer/lib/screens/home_screen.dart` (nav-shell only; Task 14 replaces the body)
- Create: `mobile/gazer/lib/screens/settings_screen.dart` (nav-shell only; Task 15 replaces the body)
- Test: `mobile/gazer/test/helpers/pump_app.dart`
- Test: `mobile/gazer/test/helpers/fakes.dart`
- Test: `mobile/gazer/test/app_test.dart`

**Interfaces:**
- Consumes: `settingsRepositoryProvider` (`Provider<SettingsRepository>`), `gazerHostApiProvider`
  (`Provider<GazerHostApi>`, Task 9, `lib/providers/devices_provider.dart`), `licenseClientProvider`
  (`FutureProvider<LicenseClient>` — override with `.overrideWith((Ref ref) async => fake)`, never
  `.overrideWithValue`), `updateCheckerProvider` (`FutureProvider<UpdateChecker>` — same), `connectivityProvider`
  (`Provider<Connectivity>`, the raw plugin instance) and `isOnlineProvider`
  (`StreamProvider<bool>`, the online/offline indicator UI actually watches and tests actually
  override) — all from Task 12; `GazerSettings.defaults()`, `LicenseState`,
  `LicenseStatus`, `SettingsRepository`, `LicenseClient`, `UpdateChecker`, `UpdateInfo` (Task 4/7/9/10);
  `FakeGazerHostApi` (Task 11); `ElderThemeData.dark` (flutter_libs
  `packages/flutter_libs/lib/src/theme/elder_theme_data.dart` — `ElderThemeData extends
  ThemeExtension<ElderThemeData>` with a `static const ElderThemeData dark = ElderThemeData(...)`
  instance; it is a `ThemeExtension`, not a `ThemeData`, so it is installed via
  `ThemeData(...).copyWith(extensions: [ElderThemeData.dark])`, never passed directly to
  `MaterialApp.theme`).
- Produces: `GazerApp` (`MaterialApp.router`), `gazerRouter` (`GoRouter`), every l10n key listed
  below, `Future<void> pumpGazerApp(WidgetTester t, {List<Override> overrides = const [], Size?
  size})`, `FakeSettingsRepository`, `FakeLicenseClient`, `FakeUpdateChecker`.

**l10n keys defined in this task's `app_en.arb`** (full file written in Step 5; every key used by
Tasks 13–16 is defined here — later tasks only *reference* keys, they never add new ones):
`appTitle`, `homeScreenTitle`, `settingsScreenTitle`, `settingsButtonLabel`, `versionLabel`,
`sourcePickerTitle`, `sourceBackCameraLabel`, `sourceFrontCameraLabel`, `sourceTileSemanticsLabel`,
`goLiveButtonLabel`, `goLiveButtonSemanticsLabel`, `stopButtonLabel`, `stopButtonSemanticsLabel`,
`statusChipIdleLabel`, `statusChipPreparingLabel`, `statusChipReadyLabel`,
`statusChipConnectingLabel`, `statusChipStreamingLabel`, `statusChipReconnectingLabel`,
`statusChipStoppingLabel`, `statusChipErrorLabel`, `statusChipSemanticsLabel`, `statusPanelTitle`,
`errorUsbPermissionDeniedMessage`, `errorUsbPermissionDeniedAction`, `errorUvcNoUsableFormatMessage`,
`errorUvcNoUsableFormatAction`, `errorUvcOpenFailedMessage`, `errorUvcOpenFailedAction`,
`errorCameraUnavailableMessage`, `errorCameraUnavailableAction`, `errorCameraInUseMessage`,
`errorCameraInUseAction`, `errorEncoderFailedMessage`, `errorEncoderFailedAction`,
`errorAudioSourceFailedMessage`, `errorAudioSourceFailedAction`, `errorRtmpAuthFailedMessage`,
`errorRtmpAuthFailedAction`, `errorRtmpConnectFailedMessage`, `errorRtmpConnectFailedAction`,
`errorRtmpDisconnectedMessage`, `errorRtmpDisconnectedAction`, `errorUsbDetachedMessage`,
`errorUsbDetachedAction`, `errorServiceStartDeniedMessage`, `errorServiceStartDeniedAction`,
`errorUnknownMessage`, `errorUnknownAction`, `targetSectionTitle`, `urlFieldLabel`, `urlFieldHint`,
`streamKeyFieldLabel`, `revealStreamKeyLabel`, `usernameFieldLabel`, `passwordFieldLabel`,
`revealPasswordLabel`, `qualitySectionTitle`, `resolutionFieldLabel`, `frameRateFieldLabel`,
`frameRateOptionLabel`, `bitrateFieldLabel`, `bitrateValueLabel`, `adaptiveBitrateLabel`,
`audioSectionTitle`, `audioSourceAutoLabel`, `audioSourceMicLabel`, `audioSourceUsbLabel`,
`audioSourceSilenceLabel`, `developerSectionTitle`, `forceLibuvcLabel`, `saveButtonLabel`,
`saveButtonSemanticsLabel`, `settingsSavedMessage`, `validationUrlSchemeError`,
`validationUrlHostError`, `validationUrlPathError`, `validationAuthBothOrNeitherError`,
`validationRtmpAuthDisabledError`, `validationUnknownError`, `statusPanelCameraLabel`,
`statusPanelCameraOffLabel`, `statusPanelCameraOnLabel`, `statusPanelUvcLabel`,
`statusPanelUvcNotConnectedLabel`, `statusPanelStreamLabel`, `statusPanelConnectionLabel`,
`statusPanelConnectionProtocolLabel`, `statusPanelConnectionHostLabel`,
`statusPanelConnectionPathLabel`, `statusPanelConnectionKeyLabel`, `statusPanelConnectionAuthLabel`,
`statusPanelConnectionAuthYes`, `statusPanelConnectionAuthNo`, `statusPanelStatsLabel`,
`statusPanelBitrateLabel`, `statusPanelFpsLabel`, `statusPanelDroppedFramesLabel`,
`statusPanelUptimeLabel`, `statusPanelReconnectCountLabel`, `statusPanelCongestionLabel`,
`statusPanelConnectivityLabel`, `statusPanelOnlineLabel`, `statusPanelOfflineLabel`,
`statusPanelLicenseLabel`, `statusPanelLicenseStatusUnknown`, `statusPanelLicenseStatusValid`,
`statusPanelLicenseStatusGracePeriod`, `statusPanelLicenseStatusInvalid`,
`statusPanelLicenseFetchingLabel`, `statusPanelLicenseLastFetchedLabel`,
`statusPanelUpdateAvailableLabel`, `statusPanelUpdateNoneLabel`, `statusPanelForegroundServiceLabel`,
`statusPanelForegroundServiceActiveLabel`, `statusPanelForegroundServiceInactiveLabel`,
`statusPanelCloseButtonLabel`.

- [ ] **Step 1: Create `test/helpers/pump_app.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/app.dart';

/// Pumps a fully-wired [GazerApp] under a [ProviderScope] carrying
/// [overrides].
///
/// When [size] is given, sets the test binding's `view.physicalSize` (and
/// pins `devicePixelRatio` to 1.0) before pumping, so responsive-layout
/// tests can drive the widget tree at a specific viewport (phone vs.
/// tablet breakpoints). The view is reset via [addTearDown] so later tests
/// in the same file are unaffected.
Future<void> pumpGazerApp(
  WidgetTester t, {
  List<Override> overrides = const <Override>[],
  Size? size,
}) async {
  if (size != null) {
    t.view.physicalSize = size;
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.reset);
  }
  await t.pumpWidget(
    ProviderScope(
      overrides: overrides,
      child: const GazerApp(),
    ),
  );
  await t.pumpAndSettle();
}
```

- [ ] **Step 2: Create `test/helpers/fakes.dart`**

```dart
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/update_info.dart';
import 'package:gazer/services/license_client.dart';
import 'package:gazer/services/settings_repository.dart';
import 'package:gazer/services/update_checker.dart';

/// In-memory [SettingsRepository] for widget tests.
///
/// Starts from an injected seed (or [GazerSettings.defaults]) and never
/// touches `flutter_secure_storage`/`shared_preferences` plugin channels,
/// so it runs under plain `flutter test` with no platform mocking.
class FakeSettingsRepository implements SettingsRepository {
  FakeSettingsRepository([GazerSettings? seed]) : _current = seed ?? GazerSettings.defaults();

  GazerSettings _current;

  /// Every value passed to [save], in call order — tests assert against
  /// this instead of re-reading through [load].
  final List<GazerSettings> saved = <GazerSettings>[];

  @override
  Future<GazerSettings> load() async => _current;

  @override
  Future<void> save(GazerSettings s) async {
    _current = s;
    saved.add(s);
  }
}

/// Test double for [LicenseClient] — returns a canned [LicenseState]
/// instead of calling `license.penguintech.io`.
class FakeLicenseClient implements LicenseClient {
  FakeLicenseClient(this.stateToReturn);

  /// The [LicenseState] every [validateAndFetchFlags] call resolves to.
  final LicenseState stateToReturn;

  /// Number of times [keepalive] was called.
  int keepaliveCalls = 0;

  @override
  Future<LicenseState> validateAndFetchFlags() async => stateToReturn;

  @override
  Future<void> keepalive() async {
    keepaliveCalls++;
  }
}

/// Test double for [UpdateChecker] — returns a canned (possibly `null`)
/// [UpdateInfo] instead of calling the GitHub releases API.
class FakeUpdateChecker implements UpdateChecker {
  FakeUpdateChecker([this.infoToReturn]);

  /// The value every [check] call resolves to; `null` means "up to date".
  final UpdateInfo? infoToReturn;

  @override
  Future<UpdateInfo?> check() async => infoToReturn;
}
```

- [ ] **Step 3: Write the failing widget test `test/app_test.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/screens/home_screen.dart';
import 'package:gazer/screens/settings_screen.dart';

import 'helpers/fake_host_api.dart';
import 'helpers/fakes.dart';
import 'helpers/pump_app.dart';

void main() {
  late FakeGazerHostApi hostApi;
  late FakeSettingsRepository settingsRepo;
  late FakeLicenseClient licenseClient;

  setUp(() {
    hostApi = FakeGazerHostApi();
    settingsRepo = FakeSettingsRepository();
    licenseClient = FakeLicenseClient(
      LicenseState(
        status: LicenseStatus.valid,
        flags: const <String, bool>{
          'waddlebot.gazer.camera-stream': true,
          'waddlebot.gazer.uvc-capture': true,
          'waddlebot.gazer.adaptive-bitrate': true,
          'waddlebot.gazer.rtmp-auth': true,
        },
        lastFetched: DateTime.utc(2026, 9, 7),
        deviceId: 'test-device',
      ),
    );
  });

  List<Override> overrides() => <Override>[
        settingsRepositoryProvider.overrideWithValue(settingsRepo),
        gazerHostApiProvider.overrideWithValue(hostApi),
        licenseClientProvider.overrideWith((Ref ref) async => licenseClient),
        isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
        updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
      ];

  testWidgets('app builds and shows HomeScreen at the initial route', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides());
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(find.byType(SettingsScreen), findsNothing);
  });

  testWidgets('navigating to /settings shows SettingsScreen', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pumpAndSettle();
    expect(find.byType(SettingsScreen), findsOneWidget);
  });
}
```

- [ ] **Step 4: Run and confirm FAIL**

`make mobile-run CMD="flutter test test/app_test.dart"` — expected failure (nothing under `lib/`
exports these names yet):
```
Error: Target of URI doesn't exist: 'package:gazer/app.dart'.
Error: Target of URI doesn't exist: 'package:gazer/screens/home_screen.dart'.
Error: Target of URI doesn't exist: 'package:gazer/screens/settings_screen.dart'.
```

- [ ] **Step 5: Create `lib/l10n/app_en.arb`**

```json
{
  "@@locale": "en",
  "appTitle": "Gazer",
  "homeScreenTitle": "Gazer",
  "settingsScreenTitle": "Settings",
  "settingsButtonLabel": "Settings",
  "versionLabel": "Version {version}",
  "@versionLabel": { "placeholders": { "version": { "type": "String" } } },
  "sourcePickerTitle": "Select camera",
  "sourceBackCameraLabel": "Back camera",
  "sourceFrontCameraLabel": "Front camera",
  "sourceTileSemanticsLabel": "{name} camera source",
  "@sourceTileSemanticsLabel": { "placeholders": { "name": { "type": "String" } } },
  "goLiveButtonLabel": "Go Live",
  "goLiveButtonSemanticsLabel": "Go live button",
  "stopButtonLabel": "Stop",
  "stopButtonSemanticsLabel": "Stop stream button",
  "statusChipIdleLabel": "Idle",
  "statusChipPreparingLabel": "Preparing",
  "statusChipReadyLabel": "Ready",
  "statusChipConnectingLabel": "Connecting",
  "statusChipStreamingLabel": "Streaming",
  "statusChipReconnectingLabel": "Reconnecting",
  "statusChipStoppingLabel": "Stopping",
  "statusChipErrorLabel": "Error",
  "statusChipSemanticsLabel": "Stream status: {status}",
  "@statusChipSemanticsLabel": { "placeholders": { "status": { "type": "String" } } },
  "statusPanelTitle": "Status",
  "errorUsbPermissionDeniedMessage": "USB permission was denied.",
  "errorUsbPermissionDeniedAction": "Reconnect the device and grant permission when prompted.",
  "errorUvcNoUsableFormatMessage": "No usable video format was found on this device.",
  "errorUvcNoUsableFormatAction": "Try a different capture device, or use the phone camera.",
  "errorUvcOpenFailedMessage": "The capture device could not be opened.",
  "errorUvcOpenFailedAction": "Disconnect and reconnect the device, then try again.",
  "errorCameraUnavailableMessage": "The camera is unavailable.",
  "errorCameraUnavailableAction": "Check camera permission in system settings.",
  "errorCameraInUseMessage": "The camera is in use by another app.",
  "errorCameraInUseAction": "Close other apps using the camera and try again.",
  "errorEncoderFailedMessage": "The video encoder failed to start.",
  "errorEncoderFailedAction": "Lower the resolution or bitrate and try again.",
  "errorAudioSourceFailedMessage": "The audio source failed to start.",
  "errorAudioSourceFailedAction": "Choose a different audio source in Settings.",
  "errorRtmpAuthFailedMessage": "The server rejected the stream credentials.",
  "errorRtmpAuthFailedAction": "Check the username and password in Settings.",
  "errorRtmpConnectFailedMessage": "Could not connect to the streaming server.",
  "errorRtmpConnectFailedAction": "Check the URL and your network connection, then try again.",
  "errorRtmpDisconnectedMessage": "The stream was disconnected.",
  "errorRtmpDisconnectedAction": "Reconnecting automatically; check your network if this repeats.",
  "errorUsbDetachedMessage": "The USB device was disconnected.",
  "errorUsbDetachedAction": "Reconnect the device to resume.",
  "errorServiceStartDeniedMessage": "The streaming service could not start.",
  "errorServiceStartDeniedAction": "Grant the notification/camera permissions and try again.",
  "errorUnknownMessage": "An unexpected error occurred.",
  "errorUnknownAction": "Try again; open Status for details.",
  "targetSectionTitle": "Stream Target",
  "urlFieldLabel": "RTMP URL",
  "urlFieldHint": "rtmp://host/app",
  "streamKeyFieldLabel": "Stream Key",
  "revealStreamKeyLabel": "Show stream key",
  "usernameFieldLabel": "Username",
  "passwordFieldLabel": "Password",
  "revealPasswordLabel": "Show password",
  "qualitySectionTitle": "Quality",
  "resolutionFieldLabel": "Resolution",
  "frameRateFieldLabel": "Frame Rate",
  "frameRateOptionLabel": "{value} fps",
  "@frameRateOptionLabel": { "placeholders": { "value": { "type": "int" } } },
  "bitrateFieldLabel": "Video Bitrate",
  "bitrateValueLabel": "{value} kbps",
  "@bitrateValueLabel": { "placeholders": { "value": { "type": "int" } } },
  "adaptiveBitrateLabel": "Adaptive Bitrate",
  "audioSectionTitle": "Audio Source",
  "audioSourceAutoLabel": "Automatic",
  "audioSourceMicLabel": "Phone Microphone",
  "audioSourceUsbLabel": "USB Audio",
  "audioSourceSilenceLabel": "Silence",
  "developerSectionTitle": "Developer",
  "forceLibuvcLabel": "Force libuvc",
  "saveButtonLabel": "Save",
  "saveButtonSemanticsLabel": "Save settings",
  "settingsSavedMessage": "Settings saved",
  "validationUrlSchemeError": "URL must start with rtmp:// or rtmps://",
  "validationUrlHostError": "URL must include a host",
  "validationUrlPathError": "URL must include a path, e.g. /live",
  "validationAuthBothOrNeitherError": "Enter both username and password, or leave both blank",
  "validationRtmpAuthDisabledError": "Username/password authentication is not enabled for this license tier",
  "validationUnknownError": "This field is invalid",
  "statusPanelCameraLabel": "Camera",
  "statusPanelCameraOffLabel": "Off",
  "statusPanelCameraOnLabel": "On ({name})",
  "@statusPanelCameraOnLabel": { "placeholders": { "name": { "type": "String" } } },
  "statusPanelUvcLabel": "UVC Capture",
  "statusPanelUvcNotConnectedLabel": "No capture card connected",
  "statusPanelStreamLabel": "Stream",
  "statusPanelConnectionLabel": "Connection",
  "statusPanelConnectionProtocolLabel": "Protocol",
  "statusPanelConnectionHostLabel": "Host",
  "statusPanelConnectionPathLabel": "Path",
  "statusPanelConnectionKeyLabel": "Stream Key",
  "statusPanelConnectionAuthLabel": "Auth",
  "statusPanelConnectionAuthYes": "Yes",
  "statusPanelConnectionAuthNo": "No",
  "statusPanelStatsLabel": "Live Stats",
  "statusPanelBitrateLabel": "Bitrate: {value} kbps",
  "@statusPanelBitrateLabel": { "placeholders": { "value": { "type": "String" } } },
  "statusPanelFpsLabel": "FPS: {value}",
  "@statusPanelFpsLabel": { "placeholders": { "value": { "type": "String" } } },
  "statusPanelDroppedFramesLabel": "Dropped frames: {value}",
  "@statusPanelDroppedFramesLabel": { "placeholders": { "value": { "type": "String" } } },
  "statusPanelUptimeLabel": "Uptime: {value}s",
  "@statusPanelUptimeLabel": { "placeholders": { "value": { "type": "String" } } },
  "statusPanelReconnectCountLabel": "Reconnects: {value}",
  "@statusPanelReconnectCountLabel": { "placeholders": { "value": { "type": "String" } } },
  "statusPanelCongestionLabel": "Congestion: {value}%",
  "@statusPanelCongestionLabel": { "placeholders": { "value": { "type": "String" } } },
  "statusPanelConnectivityLabel": "Connectivity",
  "statusPanelOnlineLabel": "Online",
  "statusPanelOfflineLabel": "Offline",
  "statusPanelLicenseLabel": "License",
  "statusPanelLicenseStatusUnknown": "Unknown",
  "statusPanelLicenseStatusValid": "Valid",
  "statusPanelLicenseStatusGracePeriod": "Grace period",
  "statusPanelLicenseStatusInvalid": "Invalid",
  "statusPanelLicenseFetchingLabel": "Fetching features… (required to stream)",
  "statusPanelLicenseLastFetchedLabel": "Last fetched: {time}",
  "@statusPanelLicenseLastFetchedLabel": { "placeholders": { "time": { "type": "String" } } },
  "statusPanelUpdateAvailableLabel": "Update available: v{version}",
  "@statusPanelUpdateAvailableLabel": { "placeholders": { "version": { "type": "String" } } },
  "statusPanelUpdateNoneLabel": "Up to date",
  "statusPanelForegroundServiceLabel": "Foreground Service",
  "statusPanelForegroundServiceActiveLabel": "Active",
  "statusPanelForegroundServiceInactiveLabel": "Inactive",
  "statusPanelCloseButtonLabel": "Close"
}
```

- [ ] **Step 6: Create `lib/main.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

/// Entry point for the Gazer mobile app.
///
/// Wraps [GazerApp] in a [ProviderScope] so every Riverpod provider in the
/// widget tree resolves against the real (non-test) provider graph.
void main() {
  runApp(const ProviderScope(child: GazerApp()));
}
```

- [ ] **Step 7: Create `lib/app.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:go_router/go_router.dart';

import 'l10n/app_localizations.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';

/// Route table for the app: `'/'` → [HomeScreen], `'/settings'` →
/// [SettingsScreen]. Declared at file scope (rather than inside
/// [GazerApp]) so [GazerApp] stays `const` and tests share one instance.
final GoRouter gazerRouter = GoRouter(
  initialLocation: '/',
  routes: <RouteBase>[
    GoRoute(
      path: '/',
      name: 'home',
      builder: (BuildContext context, GoRouterState state) => const HomeScreen(),
    ),
    GoRoute(
      path: '/settings',
      name: 'settings',
      builder: (BuildContext context, GoRouterState state) => const SettingsScreen(),
    ),
  ],
);

/// Root widget for the Gazer mobile app.
///
/// Wires go_router navigation, the Elder theme, and the generated
/// [AppLocalizations] delegates. `ElderThemeData` (flutter_libs) is a
/// [ThemeExtension], not a [ThemeData], so it is installed via
/// `ThemeData(...).copyWith(extensions: [ElderThemeData.dark])`.
/// `themeMode` is [ThemeMode.system] but both `theme` and `darkTheme` are
/// set to the same Elder-dark [ThemeData], so the app renders dark
/// regardless of the platform brightness setting (house rule: dark
/// default for client apps with a single supported theme).
class GazerApp extends StatelessWidget {
  const GazerApp({super.key});

  static ThemeData get _elderDarkTheme => ThemeData.dark().copyWith(
        scaffoldBackgroundColor: ElderThemeData.dark.pageBackground,
        colorScheme: ThemeData.dark().colorScheme.copyWith(
              primary: ElderThemeData.dark.primaryButton,
              onPrimary: ElderThemeData.dark.primaryButtonText,
              error: ElderThemeData.dark.errorText,
            ),
        extensions: <ThemeExtension<dynamic>>[ElderThemeData.dark],
      );

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      onGenerateTitle: (BuildContext context) => AppLocalizations.of(context)!.appTitle,
      theme: _elderDarkTheme,
      darkTheme: _elderDarkTheme,
      themeMode: ThemeMode.system,
      routerConfig: gazerRouter,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
    );
  }
}
```

- [ ] **Step 8: Create `lib/screens/home_screen.dart` (nav-shell only)**

```dart
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../l10n/app_localizations.dart';

/// Landing screen for the Gazer app.
///
/// This task provides the navigation shell only (app bar + settings gear
/// button). Task 14 replaces the body with the source picker, Go
/// Live/Stop controls, and the status chip.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.homeScreenTitle),
        actions: <Widget>[
          Semantics(
            label: l10n.settingsButtonLabel,
            button: true,
            child: IconButton(
              icon: const Icon(Icons.settings),
              tooltip: l10n.settingsButtonLabel,
              onPressed: () => context.push('/settings'),
            ),
          ),
        ],
      ),
      body: const SizedBox.shrink(),
    );
  }
}
```

- [ ] **Step 9: Create `lib/screens/settings_screen.dart` (nav-shell only)**

```dart
import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';

/// Settings screen for the Gazer app.
///
/// This task provides the navigation shell only (app bar; the back
/// button is supplied automatically by go_router). Task 15 replaces the
/// body with the full target/quality/audio/developer form.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    return Scaffold(
      appBar: AppBar(title: Text(l10n.settingsScreenTitle)),
      body: const SizedBox.shrink(),
    );
  }
}
```

- [ ] **Step 10: Regenerate localizations** — `make mobile-codegen` — expected: writes
  `lib/l10n/app_localizations.dart` and `lib/l10n/app_localizations_en.dart` with no errors.

- [ ] **Step 11: Run and confirm PASS** — `make mobile-run CMD="flutter test test/app_test.dart"`
  — expected: `00:0X +2: All tests passed!`

- [ ] **Step 12: Lint** — `make mobile-lint` — expected: `No issues found!`

- [ ] **Step 13: Commit**

```bash
git add mobile/gazer/lib/main.dart mobile/gazer/lib/app.dart mobile/gazer/lib/l10n/app_en.arb \
        mobile/gazer/lib/l10n/app_localizations.dart mobile/gazer/lib/l10n/app_localizations_en.dart \
        mobile/gazer/lib/screens/home_screen.dart mobile/gazer/lib/screens/settings_screen.dart \
        mobile/gazer/test/helpers/pump_app.dart mobile/gazer/test/helpers/fakes.dart \
        mobile/gazer/test/app_test.dart
git commit -m "$(cat <<'EOF'
feat(gazer): app shell, router, theme, and localization

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
EOF
)"
```

---

### Task 14: HomeScreen, SourcePicker, StatusChip

**Files:**
- Modify: `mobile/gazer/lib/screens/home_screen.dart` (full body implementation)
- Create: `mobile/gazer/lib/widgets/source_picker.dart`
- Create: `mobile/gazer/lib/widgets/status_chip.dart`
- Create: `mobile/gazer/lib/l10n/error_text.dart` (new, not in the original file map — a small
  pure helper mapping `GazerErrorCode` → localized (message, action); needed once the enablement
  rule requires per-code copy and has no natural home in a frozen Task 4–11 file)
- Create: `mobile/gazer/lib/services/settings_validation.dart` (new, not in the original file
  map — combines `TargetValidator.validate()` with the license-gated `rtmpAuthDisabled` check the
  contract's enablement rule requires; both [HomeScreen] and Task 15's SettingsScreen call it so
  the two screens never disagree about validity)
- Create: `mobile/gazer/lib/screens/status_panel.dart` (minimal — a bottom sheet with only a
  title; Task 16 replaces it with the full panel)
- Test: `mobile/gazer/test/widgets/status_chip_test.dart`
- Test: `mobile/gazer/test/widgets/source_picker_test.dart`
- Test: `mobile/gazer/test/screens/home_screen_test.dart`

**Interfaces:**
- Consumes: `videoDevicesProvider` (`AutoDisposeFutureProvider<List<VideoDevice>>`),
  `settingsNotifierProvider` (`AsyncValue<GazerSettings>`), `pipelineStateProvider`
  (`AsyncValue<PipelineState>`), `pipelineControllerProvider` (`PipelineController`),
  `featureFlagsProvider` (`FeatureFlags`), `PipelineController.goLive(GazerSettings settings,
  {required List<VideoDevice> devices, required String videoDeviceId, required FeatureFlags flags,
  OutputOrientation orientation = OutputOrientation.landscape})`, `PipelineController.stop()`, `PipelineController.current`,
  sealed `PipelineState` subclasses (`IdleState`, `PreparingState`, `ReadyState`,
  `ConnectingState`, `StreamingState`, `ReconnectingState`, `StoppingState`, `ErrorState`),
  `GazerError`, `GazerErrorCode` (`lib/pigeon/pipeline.g.dart`), `VideoDevice`, `VideoDeviceKind`,
  `OutputOrientation`, `FlagKeys` (`lib/config/flag_keys.dart`), `TargetValidator`,
  `ValidationIssue` (`lib/services/target_validator.dart`).
- Produces: `SourcePicker`, `StatusChip`, `errorTextFor(AppLocalizations l10n, GazerErrorCode
  code) -> (String, String)`, `List<ValidationIssue> validateGazerSettings(GazerSettings
  settings, FeatureFlags flags)`, `showStatusPanel(BuildContext context)` (minimal bottom sheet
  in this task), full `HomeScreen`.
- **Go Live enablement rule** (verbatim from the contract, wired here): enabled iff settings
  valid (via `validateGazerSettings`) **AND** `flags.hasFetchedOnce && flags.isEnabled(FlagKeys.cameraStream)`
  **AND** pipeline state is `IdleState`/`ReadyState`/`ErrorState` **AND** a video device is
  selected. Stop is shown instead of Go Live while `ConnectingState`/`StreamingState`/`ReconnectingState`.

- [ ] **Step 1: Write the failing widget test `test/widgets/status_chip_test.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/l10n/app_localizations.dart';
import 'package:gazer/models/pipeline_state.dart';
import 'package:gazer/widgets/status_chip.dart';

Widget _wrap(Widget child) => MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: child),
    );

void main() {
  testWidgets('renders the correct color and label per state', (WidgetTester tester) async {
    const Map<PipelineState, Color> expected = <PipelineState, Color>{
      IdleState(): Colors.grey,
      PreparingState(): Colors.amber,
      ConnectingState(): Colors.blue,
      StreamingState(): Colors.green,
      ReconnectingState(1, Duration(seconds: 1)): Colors.orange,
      ErrorState(GazerError(code: GazerErrorCode.unknown)): Colors.red,
    };
    for (final MapEntry<PipelineState, Color> entry in expected.entries) {
      await tester.pumpWidget(_wrap(StatusChip(state: entry.key, onTap: () {})));
      final Chip chip = tester.widget<Chip>(find.byType(Chip));
      expect(chip.backgroundColor, entry.value, reason: '${entry.key}');
    }
  });

  testWidgets('tapping the chip invokes onTap', (WidgetTester tester) async {
    bool tapped = false;
    await tester.pumpWidget(_wrap(StatusChip(state: const IdleState(), onTap: () => tapped = true)));
    await tester.tap(find.byType(StatusChip));
    expect(tapped, isTrue);
  });
}
```

- [ ] **Step 2: Run and confirm FAIL** — `make mobile-run CMD="flutter test test/widgets/status_chip_test.dart"`
  — expected: `Error: Target of URI doesn't exist: 'package:gazer/widgets/status_chip.dart'.`

- [ ] **Step 3: Create `lib/widgets/status_chip.dart`**

```dart
import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/pipeline_state.dart';

/// Colour-coded chip summarising the current [PipelineState].
///
/// Tapping it invokes [onTap] — [HomeScreen] wires this to
/// `showStatusPanel`. Colours: idle/ready/stopping = grey, preparing =
/// amber, connecting = blue, streaming = green, reconnecting = orange,
/// error = red (per spec).
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.state, required this.onTap});

  final PipelineState state;
  final VoidCallback onTap;

  Color _colorFor(PipelineState s) {
    return switch (s) {
      IdleState() => Colors.grey,
      PreparingState() => Colors.amber,
      ReadyState() => Colors.grey,
      ConnectingState() => Colors.blue,
      StreamingState() => Colors.green,
      ReconnectingState() => Colors.orange,
      StoppingState() => Colors.grey,
      ErrorState() => Colors.red,
    };
  }

  String _labelFor(AppLocalizations l10n, PipelineState s) {
    return switch (s) {
      IdleState() => l10n.statusChipIdleLabel,
      PreparingState() => l10n.statusChipPreparingLabel,
      ReadyState() => l10n.statusChipReadyLabel,
      ConnectingState() => l10n.statusChipConnectingLabel,
      StreamingState() => l10n.statusChipStreamingLabel,
      ReconnectingState() => l10n.statusChipReconnectingLabel,
      StoppingState() => l10n.statusChipStoppingLabel,
      ErrorState() => l10n.statusChipErrorLabel,
    };
  }

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final String label = _labelFor(l10n, state);
    return Semantics(
      key: const Key('statusChip'),
      label: l10n.statusChipSemanticsLabel(label),
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Chip(
          backgroundColor: _colorFor(state),
          label: Text(label, style: const TextStyle(color: Colors.black)),
        ),
      ),
    );
  }
}
```

- [ ] **Step 4: Run and confirm PASS** — `make mobile-run CMD="flutter test test/widgets/status_chip_test.dart"`
  — expected: `00:0X +2: All tests passed!`

- [ ] **Step 5: Write the failing widget test `test/widgets/source_picker_test.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/l10n/app_localizations.dart';
import 'package:gazer/pigeon/pipeline.g.dart';
import 'package:gazer/widgets/source_picker.dart';

const List<VideoDevice> _devices = <VideoDevice>[
  VideoDevice(id: 'camera:back', kind: VideoDeviceKind.backCamera, name: 'Back Camera'),
  VideoDevice(id: 'camera:front', kind: VideoDeviceKind.frontCamera, name: 'Front Camera'),
];

void main() {
  testWidgets('renders one tile per device', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SourcePicker(devices: _devices, selectedId: 'camera:back', onSelected: (_) {}),
        ),
      ),
    );
    expect(find.byType(RadioListTile<String>), findsNWidgets(2));
    expect(find.text('Back camera'), findsOneWidget);
    expect(find.text('Front camera'), findsOneWidget);
  });

  testWidgets('tapping a tile calls onSelected with its id', (WidgetTester tester) async {
    String? selected;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SourcePicker(devices: _devices, selectedId: null, onSelected: (String id) => selected = id),
        ),
      ),
    );
    await tester.tap(find.text('Front camera'));
    expect(selected, 'camera:front');
  });
}
```

- [ ] **Step 6: Run and confirm FAIL** — `make mobile-run CMD="flutter test test/widgets/source_picker_test.dart"`
  — expected: `Error: Target of URI doesn't exist: 'package:gazer/widgets/source_picker.dart'.`

- [ ] **Step 7: Create `lib/widgets/source_picker.dart`**

```dart
import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../pigeon/pipeline.g.dart';

/// Lists selectable video sources (M1: back/front camera only) as
/// radio-style tiles.
///
/// [devices] comes from `videoDevicesProvider`; [selectedId] is the
/// currently-chosen `VideoDevice.id`; [onSelected] fires with the tapped
/// device's id.
class SourcePicker extends StatelessWidget {
  const SourcePicker({
    super.key,
    required this.devices,
    required this.selectedId,
    required this.onSelected,
  });

  final List<VideoDevice> devices;
  final String? selectedId;
  final ValueChanged<String> onSelected;

  String _labelFor(AppLocalizations l10n, VideoDevice d) {
    return switch (d.kind) {
      VideoDeviceKind.backCamera => l10n.sourceBackCameraLabel,
      VideoDeviceKind.frontCamera => l10n.sourceFrontCameraLabel,
      VideoDeviceKind.uvcCamera2 || VideoDeviceKind.uvcLibuvc => d.name,
    };
  }

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Text(l10n.sourcePickerTitle, style: Theme.of(context).textTheme.titleMedium),
        ),
        for (final VideoDevice d in devices)
          Semantics(
            label: l10n.sourceTileSemanticsLabel(_labelFor(l10n, d)),
            selected: d.id == selectedId,
            button: true,
            child: RadioListTile<String>(
              // 'camera:back' gets the fixed integration_test key; every
              // other tile still gets a stable per-device key so the list
              // never relies on Flutter's positional fallback.
              key: d.id == 'camera:back' ? const Key('backCameraOption') : ValueKey(d.id),
              value: d.id,
              groupValue: selectedId,
              onChanged: (String? id) {
                if (id != null) onSelected(id);
              },
              title: Text(_labelFor(l10n, d)),
            ),
          ),
      ],
    );
  }
}
```

- [ ] **Step 8: Run and confirm PASS** — `make mobile-run CMD="flutter test test/widgets/source_picker_test.dart"`
  — expected: `00:0X +2: All tests passed!`

- [ ] **Step 9: Create `lib/l10n/error_text.dart`**

```dart
import 'l10n.dart' show AppLocalizations;
import '../pigeon/pipeline.g.dart';

/// Maps a [GazerErrorCode] to its localized `(message, action)` pair.
///
/// Centralised so every error surface (today: [HomeScreen]'s error
/// banner) reads identical copy for the same code.
(String, String) errorTextFor(AppLocalizations l10n, GazerErrorCode code) {
  return switch (code) {
    GazerErrorCode.usbPermissionDenied =>
      (l10n.errorUsbPermissionDeniedMessage, l10n.errorUsbPermissionDeniedAction),
    GazerErrorCode.uvcNoUsableFormat =>
      (l10n.errorUvcNoUsableFormatMessage, l10n.errorUvcNoUsableFormatAction),
    GazerErrorCode.uvcOpenFailed => (l10n.errorUvcOpenFailedMessage, l10n.errorUvcOpenFailedAction),
    GazerErrorCode.cameraUnavailable =>
      (l10n.errorCameraUnavailableMessage, l10n.errorCameraUnavailableAction),
    GazerErrorCode.cameraInUse => (l10n.errorCameraInUseMessage, l10n.errorCameraInUseAction),
    GazerErrorCode.encoderFailed => (l10n.errorEncoderFailedMessage, l10n.errorEncoderFailedAction),
    GazerErrorCode.audioSourceFailed =>
      (l10n.errorAudioSourceFailedMessage, l10n.errorAudioSourceFailedAction),
    GazerErrorCode.rtmpAuthFailed => (l10n.errorRtmpAuthFailedMessage, l10n.errorRtmpAuthFailedAction),
    GazerErrorCode.rtmpConnectFailed =>
      (l10n.errorRtmpConnectFailedMessage, l10n.errorRtmpConnectFailedAction),
    GazerErrorCode.rtmpDisconnected =>
      (l10n.errorRtmpDisconnectedMessage, l10n.errorRtmpDisconnectedAction),
    GazerErrorCode.usbDetached => (l10n.errorUsbDetachedMessage, l10n.errorUsbDetachedAction),
    GazerErrorCode.serviceStartDenied =>
      (l10n.errorServiceStartDeniedMessage, l10n.errorServiceStartDeniedAction),
    GazerErrorCode.unknown => (l10n.errorUnknownMessage, l10n.errorUnknownAction),
  };
}
```

Note: replace the `import 'l10n.dart' show AppLocalizations;` line with
`import 'app_localizations.dart';` — written this way only to flag that `error_text.dart` lives
*inside* `lib/l10n/` (sibling to the generated file), so the import is `'app_localizations.dart'`,
not `'../l10n/app_localizations.dart'`.

- [ ] **Step 10: Create `lib/services/settings_validation.dart`**

```dart
import '../models/gazer_settings.dart';
import '../models/validation_issue.dart';
import '../services/feature_flags.dart';
import '../services/target_validator.dart';
import '../config/flag_keys.dart';

/// Combines [TargetValidator]'s structural checks with the license gate
/// the contract's Go Live rule requires: a username/password pair is
/// only valid when `FlagKeys.rtmpAuth` is enabled for this license tier.
///
/// Both [HomeScreen]'s enablement check and Task 15's `SettingsScreen`
/// call this — never `TargetValidator` alone — so the two screens can
/// never disagree about validity.
List<ValidationIssue> validateGazerSettings(GazerSettings settings, FeatureFlags flags) {
  final List<ValidationIssue> issues = <ValidationIssue>[
    ...const TargetValidator().validate(settings.target),
  ];
  final bool hasAuthPair = (settings.target.username?.isNotEmpty ?? false) ||
      (settings.target.password?.isNotEmpty ?? false);
  if (hasAuthPair && !flags.isEnabled(FlagKeys.rtmpAuth)) {
    issues.add(const ValidationIssue(field: 'username', messageKey: 'rtmpAuthDisabled'));
  }
  return issues;
}
```

- [ ] **Step 11: Create the initial `lib/screens/status_panel.dart`** (Task 16 extends this into the full diagnostic panel)

```dart
import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';

/// Opens the status panel as a modal bottom sheet.
///
/// Initial version for Task 14's HomeScreen wiring — shows only the
/// panel title. Task 16 extends both this function and [StatusPanel]
/// with the full diagnostic panel and the ≥600dp side-pane behaviour.
void showStatusPanel(BuildContext context) {
  showModalBottomSheet<void>(
    context: context,
    builder: (BuildContext context) => const StatusPanel(),
  );
}

/// Initial status panel body — Task 16 extends this with the full diagnostic content.
class StatusPanel extends StatelessWidget {
  const StatusPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(l10n.statusPanelTitle, style: Theme.of(context).textTheme.titleLarge),
      ),
    );
  }
}
```

- [ ] **Step 12: Write the failing widget test `test/screens/home_screen_test.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/services/pipeline_controller.dart';
import 'package:gazer/services/reconnect_policy.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  late FakeGazerHostApi hostApi;
  late FakeSettingsRepository settingsRepo;

  LicenseState _license({required bool flagsSet}) => LicenseState(
        status: LicenseStatus.valid,
        flags: <String, bool>{
          'waddlebot.gazer.camera-stream': flagsSet,
          'waddlebot.gazer.uvc-capture': flagsSet,
          'waddlebot.gazer.adaptive-bitrate': flagsSet,
          'waddlebot.gazer.rtmp-auth': flagsSet,
        },
        lastFetched: flagsSet ? DateTime.utc(2026, 9, 7) : null,
        deviceId: 'test-device',
      );

  setUp(() {
    hostApi = FakeGazerHostApi()
      ..videoDevices = <VideoDevice>[
        VideoDevice(id: 'camera:back', kind: VideoDeviceKind.backCamera, name: 'Back Camera'),
        VideoDevice(id: 'camera:front', kind: VideoDeviceKind.frontCamera, name: 'Front Camera'),
      ];
    settingsRepo = FakeSettingsRepository(
      GazerSettings.defaults().copyWith(
        target: const StreamTargetSettings(url: 'rtmp://example.com/live/mystream'),
      ),
    );
  });

  List<Override> overrides({required LicenseState license}) => <Override>[
        settingsRepositoryProvider.overrideWithValue(settingsRepo),
        gazerHostApiProvider.overrideWithValue(hostApi),
        // Wires hostApi.bridge into the controller under test so
        // hostApi.emitState(...) below actually reaches pipelineStateProvider
        // — see Task 11's FakeGazerHostApi doc (overriding gazerHostApiProvider
        // alone does not connect the two).
        pipelineControllerProvider.overrideWithValue(
          PipelineController(host: hostApi, events: hostApi.bridge, policy: ReconnectPolicy()),
        ),
        licenseClientProvider.overrideWith((Ref ref) async => FakeLicenseClient(license)),
        isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
        updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
      ];

  testWidgets('source picker lists the fake devices', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(license: _license(flagsSet: true)));
    expect(find.text('Back camera'), findsOneWidget);
    expect(find.text('Front camera'), findsOneWidget);
  });

  testWidgets('Go Live is disabled when flags have not been fetched', (WidgetTester tester) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: LicenseState.initial('test-device')),
    );
    final FilledButton button = tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Go Live'));
    expect(button.onPressed, isNull);
  });

  testWidgets('Go Live is enabled once settings and flags are valid', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(license: _license(flagsSet: true)));
    final FilledButton button = tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Go Live'));
    expect(button.onPressed, isNotNull);
  });

  testWidgets('tapping Go Live calls prepare then start with the effective URL', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(license: _license(flagsSet: true)));
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.pumpAndSettle();
    expect(hostApi.prepareCalls, hasLength(1));
    expect(hostApi.startCalls, hasLength(1));
    expect(hostApi.startCalls.single.url, 'rtmp://example.com/live/mystream');
  });

  testWidgets('Stop appears while streaming', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(license: _license(flagsSet: true)));
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.pumpAndSettle();
    await hostApi.emitState(NativePipelineState.streaming);
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilledButton, 'Stop'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Go Live'), findsNothing);
  });

  testWidgets('error state shows the localized message and action text', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(license: _license(flagsSet: true)));
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.pumpAndSettle();
    await hostApi.emitState(NativePipelineState.error, error: GazerErrorCode.rtmpConnectFailed);
    await tester.pumpAndSettle();
    expect(find.text('Could not connect to the streaming server.'), findsOneWidget);
    expect(find.text('Check the URL and your network connection, then try again.'), findsOneWidget);
  });
}
```

- [ ] **Step 13: Run and confirm FAIL** — `make mobile-run CMD="flutter test test/screens/home_screen_test.dart"`
  — expected: `Bad state: No element` / widget-not-found failures — `HomeScreen`'s body is still
  `SizedBox.shrink()` from Task 13, so `find.widgetWithText(FilledButton, 'Go Live')` finds
  nothing:
  ```
  The following TestFailure was thrown running a test:
  Expected: exactly one matching candidate
    Actual: _TextWidgetFinder:<zero widgets with text "Go Live" (ignoring offstage widgets)>
  ```

- [ ] **Step 14: Replace `lib/screens/home_screen.dart` with the full implementation**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../config/flag_keys.dart';
import '../l10n/app_localizations.dart';
import '../l10n/error_text.dart';
import '../models/gazer_settings.dart';
import '../models/pipeline_state.dart';
import '../models/validation_issue.dart';
import '../pigeon/pipeline.g.dart';
import '../providers/devices_provider.dart';
import '../providers/license_provider.dart';
import '../providers/pipeline_provider.dart';
import '../providers/settings_provider.dart';
import '../services/feature_flags.dart';
import '../services/settings_validation.dart';
import '../widgets/source_picker.dart';
import '../widgets/status_chip.dart';
import 'status_panel.dart';

/// Landing screen: source picker, Go Live / Stop controls, and the status
/// chip that opens [showStatusPanel].
///
/// The selected video device id is local widget state (M1 has no
/// persisted "last camera" preference); everything else is read from
/// Riverpod providers so the screen re-renders on every pipeline/settings
/// change.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  String? _selectedDeviceId;

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final List<VideoDevice> devices = ref.watch(videoDevicesProvider).valueOrNull ?? const <VideoDevice>[];
    final GazerSettings? settings = ref.watch(settingsNotifierProvider).valueOrNull;
    final FeatureFlags flags = ref.watch(featureFlagsProvider);
    final PipelineController controller = ref.watch(pipelineControllerProvider);
    final PipelineState state = ref.watch(pipelineStateProvider).valueOrNull ?? controller.current;

    if (_selectedDeviceId == null && devices.isNotEmpty) {
      _selectedDeviceId = devices.first.id;
    }

    final List<ValidationIssue> issues =
        settings == null ? const <ValidationIssue>[] : validateGazerSettings(settings, flags);
    final bool canGoLive = settings != null &&
        issues.isEmpty &&
        flags.hasFetchedOnce &&
        flags.isEnabled(FlagKeys.cameraStream) &&
        _selectedDeviceId != null &&
        (state is IdleState || state is ReadyState || state is ErrorState);
    final bool showStop = state is ConnectingState || state is StreamingState || state is ReconnectingState;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.homeScreenTitle),
        actions: <Widget>[
          Semantics(
            label: l10n.settingsButtonLabel,
            button: true,
            child: IconButton(
              key: const Key('settingsGearButton'),
              icon: const Icon(Icons.settings),
              tooltip: l10n.settingsButtonLabel,
              onPressed: () => context.push('/settings'),
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: <Widget>[
            StatusChip(state: state, onTap: () => showStatusPanel(context)),
            const SizedBox(height: 16),
            Expanded(
              child: SourcePicker(
                devices: devices,
                selectedId: _selectedDeviceId,
                onSelected: (String id) => setState(() => _selectedDeviceId = id),
              ),
            ),
            if (state is ErrorState) _ErrorBanner(error: state.error),
            const SizedBox(height: 16),
            if (showStop)
              Semantics(
                label: l10n.stopButtonSemanticsLabel,
                button: true,
                child: FilledButton(
                  key: const Key('stopButton'),
                  onPressed: () => controller.stop(),
                  child: Text(l10n.stopButtonLabel),
                ),
              )
            else
              Semantics(
                label: l10n.goLiveButtonSemanticsLabel,
                button: true,
                child: FilledButton(
                  key: const Key('goLiveButton'),
                  onPressed: canGoLive
                      ? () => controller.goLive(
                            settings!,
                            devices: devices,
                            videoDeviceId: _selectedDeviceId!,
                            flags: flags,
                            orientation: MediaQuery.of(context).orientation == Orientation.portrait
                                ? OutputOrientation.portrait
                                : OutputOrientation.landscape,
                          )
                      : null,
                  child: Text(l10n.goLiveButtonLabel),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Shows the localized message + action text for the current [GazerError].
class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.error});

  final GazerError error;

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final (String message, String action) = errorTextFor(l10n, error.code);
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(message),
            const SizedBox(height: 4),
            Text(action, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 15: Run and confirm PASS** — `make mobile-run CMD="flutter test test/screens/home_screen_test.dart"`
  — expected: `00:0X +6: All tests passed!`

- [ ] **Step 16: Re-run Task 13's suite to confirm no regression** —
  `make mobile-run CMD="flutter test test/app_test.dart test/widgets/status_chip_test.dart test/widgets/source_picker_test.dart"`
  — expected: `00:0X +6: All tests passed!`

- [ ] **Step 17: Lint** — `make mobile-lint` — expected: `No issues found!`

- [ ] **Step 18: Commit**

```bash
git add mobile/gazer/lib/screens/home_screen.dart mobile/gazer/lib/screens/status_panel.dart \
        mobile/gazer/lib/widgets/source_picker.dart mobile/gazer/lib/widgets/status_chip.dart \
        mobile/gazer/lib/l10n/error_text.dart mobile/gazer/lib/services/settings_validation.dart \
        mobile/gazer/test/widgets/status_chip_test.dart mobile/gazer/test/widgets/source_picker_test.dart \
        mobile/gazer/test/screens/home_screen_test.dart
git commit -m "$(cat <<'EOF'
feat(gazer): HomeScreen source picker, Go Live/Stop, and status chip

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
EOF
)"
```

---

### Task 15: SettingsScreen

**Files:**
- Modify: `mobile/gazer/lib/screens/settings_screen.dart` (full form implementation)
- Create: `mobile/gazer/lib/widgets/masked_text.dart`
- Test: `mobile/gazer/test/screens/settings_screen_test.dart`
- Test: `mobile/gazer/test/widgets/masked_text_test.dart`

**Interfaces:**
- Consumes: `settingsNotifierProvider` (`SettingsNotifier.update(GazerSettings s) ->
  Future<void>`), `featureFlagsProvider`, `validateGazerSettings` (Task 14),
  `GazerSettings`/`StreamTargetSettings`/`QualitySettings` (freezed `copyWith`), `Resolution`
  (`values`, `label`), `FrameRate` (`values`, `value`), `AudioSourceChoice`, `kMinBitrateKbps`,
  `kMaxBitrateKbps`, `kBitrateStepKbps` (`lib/models/quality.dart`).
- Produces: full `SettingsScreen`, `MaskedText`.
- **flutter_libs `FormBuilder` fit decision**: flutter_libs exports a `FormBuilder` widget
  (`packages/flutter_libs/lib/src/form_builder/form_builder.dart`:
  `FormBuilder({required FormConfig config, required Future<void> Function(Map<String, dynamic>)
  onSubmit, VoidCallback? onCancel, Map<String, dynamic> initialValues = const {}, bool modal =
  false})`) driven by `FieldConfig`/`FormConfig`
  (`lib/src/form_builder/form_builder_types.dart`). Its `FieldType` enum is `{text, email,
  password, number, textarea, select, checkbox, radio, date, time, datetimeLocal, tel, url}` —
  **no slider, no segmented-control, no switch variant** — so it cannot render the bitrate
  Slider, the FrameRate `SegmentedButton`, or a Material `Switch` this screen requires. Its
  per-field `validate: String? Function(dynamic)?` also returns one plain `String`, not a
  `ValidationIssue{field, messageKey}` — it has no channel for `validateGazerSettings`'s l10n-key
  output. Given the quality section cannot be expressed in `FieldConfig` at all, this task uses
  plain `TextFormField`/`DropdownButtonFormField`/`SegmentedButton`/`Slider`/`Switch` throughout
  for one consistent validation path, rather than mixing `FormBuilder` for some fields and raw
  widgets for others.

- [ ] **Step 1: Write the failing widget test `test/widgets/masked_text_test.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/widgets/masked_text.dart';

void main() {
  testWidgets('shows only the last 4 characters by default', (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: MaskedText(value: 'abcd1234efgh', revealSemanticsLabel: 'Show')),
      ),
    );
    expect(find.text('••••••••efgh'), findsOneWidget);
    expect(find.text('abcd1234efgh'), findsNothing);
  });

  testWidgets('reveals the full value when tapped', (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: MaskedText(value: 'abcd1234efgh', revealSemanticsLabel: 'Show')),
      ),
    );
    await tester.tap(find.byIcon(Icons.visibility));
    await tester.pump();
    expect(find.text('abcd1234efgh'), findsOneWidget);
  });
}
```

- [ ] **Step 2: Run and confirm FAIL** — `make mobile-run CMD="flutter test test/widgets/masked_text_test.dart"`
  — expected: `Error: Target of URI doesn't exist: 'package:gazer/widgets/masked_text.dart'.`

- [ ] **Step 3: Create `lib/widgets/masked_text.dart`**

```dart
import 'package:flutter/material.dart';

/// Displays a secret value masked except for its last 4 characters, with
/// a tap-to-reveal toggle showing the full value.
///
/// Used for the stream key display in [SettingsScreen] and the
/// connection-details section of the status panel — secrets never appear
/// in full until the user explicitly asks to see them.
class MaskedText extends StatefulWidget {
  const MaskedText({
    super.key,
    required this.value,
    required this.revealSemanticsLabel,
    this.maskChar = '•',
  });

  final String value;
  final String revealSemanticsLabel;
  final String maskChar;

  @override
  State<MaskedText> createState() => _MaskedTextState();
}

class _MaskedTextState extends State<MaskedText> {
  bool _revealed = false;

  String get _masked {
    final String v = widget.value;
    if (v.isEmpty) return '';
    if (v.length <= 4) return widget.maskChar * v.length;
    return widget.maskChar * (v.length - 4) + v.substring(v.length - 4);
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(_revealed ? widget.value : _masked),
        Semantics(
          label: widget.revealSemanticsLabel,
          button: true,
          child: IconButton(
            icon: Icon(_revealed ? Icons.visibility_off : Icons.visibility),
            onPressed: () => setState(() => _revealed = !_revealed),
          ),
        ),
      ],
    );
  }
}
```

- [ ] **Step 4: Run and confirm PASS** — `make mobile-run CMD="flutter test test/widgets/masked_text_test.dart"`
  — expected: `00:0X +2: All tests passed!`

- [ ] **Step 5: Write the failing widget test `test/screens/settings_screen_test.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  late FakeSettingsRepository settingsRepo;

  List<Override> overrides() => <Override>[
        settingsRepositoryProvider.overrideWithValue(settingsRepo),
        gazerHostApiProvider.overrideWithValue(FakeGazerHostApi()),
        licenseClientProvider.overrideWith(
          (Ref ref) async => FakeLicenseClient(
            LicenseState(
              status: LicenseStatus.valid,
              flags: const <String, bool>{
                'waddlebot.gazer.camera-stream': true,
                'waddlebot.gazer.uvc-capture': true,
                'waddlebot.gazer.adaptive-bitrate': true,
                'waddlebot.gazer.rtmp-auth': true,
              },
              lastFetched: DateTime.utc(2026, 9, 7),
              deviceId: 'test-device',
            ),
          ),
        ),
        isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
        updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
      ];

  setUp(() {
    settingsRepo = FakeSettingsRepository();
  });

  Future<void> pumpSettings(WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pumpAndSettle();
  }

  testWidgets('invalid URL shows an error and blocks save', (WidgetTester tester) async {
    await pumpSettings(tester);
    await tester.enterText(find.widgetWithText(TextFormField, 'RTMP URL'), 'http://bad');
    await tester.pump();
    expect(find.text('URL must start with rtmp:// or rtmps://'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    expect(settingsRepo.saved, isEmpty);
  });

  testWidgets('valid URL saves through the settings repository', (WidgetTester tester) async {
    await pumpSettings(tester);
    await tester.enterText(find.widgetWithText(TextFormField, 'RTMP URL'), 'rtmp://example.com/live/mystream');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(settingsRepo.saved, hasLength(1));
    expect(settingsRepo.saved.single.target.url, 'rtmp://example.com/live/mystream');
  });

  testWidgets('bitrate slider snaps to 100kbps steps', (WidgetTester tester) async {
    await pumpSettings(tester);
    final Slider slider = tester.widget<Slider>(find.byType(Slider));
    expect(slider.divisions, 45); // (5000 - 500) / 100
    expect(slider.min, 500);
    expect(slider.max, 5000);
  });

  testWidgets('username without password shows the both-or-neither error', (WidgetTester tester) async {
    await pumpSettings(tester);
    await tester.enterText(find.widgetWithText(TextFormField, 'RTMP URL'), 'rtmp://example.com/live/mystream');
    await tester.enterText(find.widgetWithText(TextFormField, 'Username'), 'alice');
    await tester.pump();
    expect(find.text('Enter both username and password, or leave both blank'), findsOneWidget);
  });

  testWidgets('secrets are obscured by default', (WidgetTester tester) async {
    await pumpSettings(tester);
    final TextFormField keyField = tester.widget<TextFormField>(find.widgetWithText(TextFormField, 'Stream Key'));
    final TextFormField pwField = tester.widget<TextFormField>(find.widgetWithText(TextFormField, 'Password'));
    expect(keyField.obscureText, isTrue);
    expect(pwField.obscureText, isTrue);
  });
}
```

- [ ] **Step 6: Run and confirm FAIL** — `make mobile-run CMD="flutter test test/screens/settings_screen_test.dart"`
  — expected: every finder in the test fails since `SettingsScreen`'s body is still
  `SizedBox.shrink()`:
  ```
  Expected: exactly one matching candidate
    Actual: _WidgetTypeFinder<TextFormField>:<zero widgets with type "TextFormField" and text "RTMP URL" (ignoring offstage widgets)>
  ```

- [ ] **Step 7: Replace `lib/screens/settings_screen.dart` with the full implementation**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:flutter_libs/flutter_libs.dart';

import '../l10n/app_localizations.dart';
import '../models/gazer_settings.dart';
import '../models/quality.dart';
import '../models/stream_target_settings.dart';
import '../models/validation_issue.dart';
import '../providers/license_provider.dart';
import '../providers/settings_provider.dart';
import '../services/feature_flags.dart';
import '../services/settings_validation.dart';
import '../services/target_validator.dart';

/// Settings screen: stream target, quality, audio source, and a
/// long-press-revealed developer section.
///
/// Validation runs on every keystroke via [validateGazerSettings] (the
/// same helper [HomeScreen] uses for its Go Live gate), so the two
/// screens can never disagree about whether the current settings are
/// streamable. Save persists through [SettingsNotifier.update].
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final TextEditingController _url = TextEditingController();
  final TextEditingController _streamKey = TextEditingController();
  final TextEditingController _username = TextEditingController();
  final TextEditingController _password = TextEditingController();
  GazerSettings? _draft;
  bool _initialized = false;
  bool _devUnlocked = false;
  bool _streamKeyObscured = true;
  bool _passwordObscured = true;

  void _seed(GazerSettings s) {
    _draft = s;
    _url.text = s.target.url;
    _streamKey.text = s.target.streamKey ?? '';
    _username.text = s.target.username ?? '';
    _password.text = s.target.password ?? '';
  }

  void _update(GazerSettings Function(GazerSettings) f) {
    setState(() => _draft = f(_draft!));
  }

  String _messageFor(AppLocalizations l10n, String messageKey) {
    return switch (messageKey) {
      // Keys match TargetValidator.validate()'s literal messageKey strings
      // (Task 5) exactly — 'error'-prefixed, not the bare 'urlScheme' etc.
      'errorUrlScheme' => l10n.validationUrlSchemeError,
      'errorUrlHost' => l10n.validationUrlHostError,
      'errorUrlPath' => l10n.validationUrlPathError,
      'errorAuthBothOrNeither' => l10n.validationAuthBothOrNeitherError,
      'rtmpAuthDisabled' => l10n.validationRtmpAuthDisabledError,
      _ => l10n.validationUnknownError,
    };
  }

  @override
  void dispose() {
    _url.dispose();
    _streamKey.dispose();
    _username.dispose();
    _password.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final AsyncValue<GazerSettings> settingsAsync = ref.watch(settingsNotifierProvider);
    final FeatureFlags flags = ref.watch(featureFlagsProvider);

    if (!_initialized && settingsAsync.hasValue) {
      _seed(settingsAsync.requireValue);
      _initialized = true;
    }

    if (_draft == null) {
      return Scaffold(appBar: AppBar(title: Text(l10n.settingsScreenTitle)), body: const Center(child: CircularProgressIndicator()));
    }

    final GazerSettings draft = _draft!;
    final Map<String, String> fieldErrors = <String, String>{
      for (final ValidationIssue issue in validateGazerSettings(draft, flags))
        issue.field: _messageFor(l10n, issue.messageKey),
    };
    final bool canSave = fieldErrors.isEmpty;

    return Scaffold(
      appBar: AppBar(title: Text(l10n.settingsScreenTitle)),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(l10n.targetSectionTitle, style: Theme.of(context).textTheme.titleMedium),
            TextFormField(
              key: const Key('targetUrlField'),
              controller: _url,
              decoration: InputDecoration(labelText: l10n.urlFieldLabel, hintText: l10n.urlFieldHint, errorText: fieldErrors['target']),
              onChanged: (String v) => _update((GazerSettings s) => s.copyWith(target: s.target.copyWith(url: v))),
            ),
            TextFormField(
              key: const Key('streamKeyField'),
              controller: _streamKey,
              obscureText: _streamKeyObscured,
              decoration: InputDecoration(
                labelText: l10n.streamKeyFieldLabel,
                suffixIcon: Semantics(
                  label: l10n.revealStreamKeyLabel,
                  button: true,
                  child: IconButton(
                    icon: Icon(_streamKeyObscured ? Icons.visibility : Icons.visibility_off),
                    onPressed: () => setState(() => _streamKeyObscured = !_streamKeyObscured),
                  ),
                ),
              ),
              onChanged: (String v) => _update((GazerSettings s) => s.copyWith(target: s.target.copyWith(streamKey: v))),
            ),
            TextFormField(
              controller: _username,
              decoration: InputDecoration(labelText: l10n.usernameFieldLabel, errorText: fieldErrors['username']),
              onChanged: (String v) => _update((GazerSettings s) => s.copyWith(target: s.target.copyWith(username: v))),
            ),
            TextFormField(
              controller: _password,
              obscureText: _passwordObscured,
              decoration: InputDecoration(
                labelText: l10n.passwordFieldLabel,
                errorText: fieldErrors['password'],
                suffixIcon: Semantics(
                  label: l10n.revealPasswordLabel,
                  button: true,
                  child: IconButton(
                    icon: Icon(_passwordObscured ? Icons.visibility : Icons.visibility_off),
                    onPressed: () => setState(() => _passwordObscured = !_passwordObscured),
                  ),
                ),
              ),
              onChanged: (String v) => _update((GazerSettings s) => s.copyWith(target: s.target.copyWith(password: v))),
            ),
            const Divider(),
            Text(l10n.qualitySectionTitle, style: Theme.of(context).textTheme.titleMedium),
            DropdownButtonFormField<Resolution>(
              initialValue: draft.quality.resolution,
              decoration: InputDecoration(labelText: l10n.resolutionFieldLabel),
              items: <DropdownMenuItem<Resolution>>[
                for (final Resolution r in Resolution.values) DropdownMenuItem<Resolution>(value: r, child: Text(r.label)),
              ],
              onChanged: (Resolution? r) {
                if (r != null) _update((GazerSettings s) => s.copyWith(quality: s.quality.copyWith(resolution: r)));
              },
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(l10n.frameRateFieldLabel, style: Theme.of(context).textTheme.labelLarge),
                  SegmentedButton<FrameRate>(
                    segments: <ButtonSegment<FrameRate>>[
                      for (final FrameRate fr in FrameRate.values)
                        ButtonSegment<FrameRate>(value: fr, label: Text(l10n.frameRateOptionLabel(fr.value))),
                    ],
                    selected: <FrameRate>{draft.quality.frameRate},
                    onSelectionChanged: (Set<FrameRate> s) =>
                        _update((GazerSettings gs) => gs.copyWith(quality: gs.quality.copyWith(frameRate: s.first))),
                  ),
                ],
              ),
            ),
            Text('${l10n.bitrateFieldLabel}: ${l10n.bitrateValueLabel(draft.quality.videoBitrateKbps)}'),
            Slider(
              min: kMinBitrateKbps.toDouble(),
              max: kMaxBitrateKbps.toDouble(),
              divisions: (kMaxBitrateKbps - kMinBitrateKbps) ~/ kBitrateStepKbps,
              value: draft.quality.videoBitrateKbps.toDouble(),
              label: l10n.bitrateValueLabel(draft.quality.videoBitrateKbps),
              onChanged: (double v) =>
                  _update((GazerSettings s) => s.copyWith(quality: s.quality.copyWith(videoBitrateKbps: v.round()))),
            ),
            SwitchListTile(
              title: Text(l10n.adaptiveBitrateLabel),
              value: draft.quality.adaptiveBitrate,
              onChanged: (bool v) =>
                  _update((GazerSettings s) => s.copyWith(quality: s.quality.copyWith(adaptiveBitrate: v))),
            ),
            const Divider(),
            Text(l10n.audioSectionTitle, style: Theme.of(context).textTheme.titleMedium),
            DropdownButtonFormField<AudioSourceChoice>(
              initialValue: draft.audio,
              decoration: InputDecoration(labelText: l10n.audioSectionTitle),
              items: <DropdownMenuItem<AudioSourceChoice>>[
                DropdownMenuItem<AudioSourceChoice>(value: AudioSourceChoice.auto, child: Text(l10n.audioSourceAutoLabel)),
                DropdownMenuItem<AudioSourceChoice>(value: AudioSourceChoice.mic, child: Text(l10n.audioSourceMicLabel)),
                DropdownMenuItem<AudioSourceChoice>(value: AudioSourceChoice.usbAudio, child: Text(l10n.audioSourceUsbLabel)),
                DropdownMenuItem<AudioSourceChoice>(value: AudioSourceChoice.silence, child: Text(l10n.audioSourceSilenceLabel)),
              ],
              onChanged: (AudioSourceChoice? a) {
                if (a != null) _update((GazerSettings s) => s.copyWith(audio: a));
              },
            ),
            const Divider(),
            GestureDetector(
              onLongPress: () => setState(() => _devUnlocked = !_devUnlocked),
              child: FutureBuilder<PackageInfo>(
                future: PackageInfo.fromPlatform(),
                builder: (BuildContext context, AsyncSnapshot<PackageInfo> snapshot) {
                  final String version = snapshot.data?.version ?? '';
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Column(
                      children: <Widget>[
                        if (version.isNotEmpty) ConsoleVersion(appName: l10n.appTitle, version: version),
                        Text(l10n.versionLabel(version), style: Theme.of(context).textTheme.bodySmall),
                      ],
                    ),
                  );
                },
              ),
            ),
            if (_devUnlocked) ...<Widget>[
              Text(l10n.developerSectionTitle, style: Theme.of(context).textTheme.titleMedium),
              SwitchListTile(
                title: Text(l10n.forceLibuvcLabel),
                value: draft.forceLibuvc,
                onChanged: (bool v) => _update((GazerSettings s) => s.copyWith(forceLibuvc: v)),
              ),
            ],
            const SizedBox(height: 16),
            Semantics(
              label: l10n.saveButtonSemanticsLabel,
              button: true,
              child: FilledButton(
                key: const Key('saveSettingsButton'),
                onPressed: canSave
                    ? () async {
                        await ref.read(settingsNotifierProvider.notifier).update(draft);
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(l10n.settingsSavedMessage)));
                      }
                    : null,
                child: Text(l10n.saveButtonLabel),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
```

Note: `Text.appTitle` is used as `ConsoleVersion`'s `appName` argument (per its constructor,
`ConsoleVersion({required String appName, required String version, String? environment,
Map<String, String>? metadata, ConsoleStyleConfig styleConfig = ConsoleStyleConfig.elder})` —
flutter_libs `packages/flutter_libs/lib/src/console_version/console_version.dart`); `ConsoleVersion`
renders `SizedBox.shrink()` and only logs to the developer console on mount, so the visible
`versionLabel` `Text` beside it is what the user actually sees — both are required by Task 15's
"ConsoleVersion/version display in the settings screen footer using package_info_plus" line.

- [ ] **Step 8: Run and confirm PASS** — `make mobile-run CMD="flutter test test/screens/settings_screen_test.dart"`
  — expected: `00:0X +6: All tests passed!`

- [ ] **Step 9: Re-run Tasks 13–14's suites to confirm no regression** —
  `make mobile-run CMD="flutter test test/app_test.dart test/screens/home_screen_test.dart test/widgets"`
  — expected: `00:0X +Y: All tests passed!`

- [ ] **Step 10: Lint** — `make mobile-lint` — expected: `No issues found!`

- [ ] **Step 11: Commit**

```bash
git add mobile/gazer/lib/screens/settings_screen.dart mobile/gazer/lib/widgets/masked_text.dart \
        mobile/gazer/test/screens/settings_screen_test.dart mobile/gazer/test/widgets/masked_text_test.dart
git commit -m "$(cat <<'EOF'
feat(gazer): SettingsScreen target/quality/audio/developer form

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
EOF
)"
```

---

### Task 16: StatusPanel and responsive layout

**Files:**
- Modify: `mobile/gazer/lib/screens/status_panel.dart` (full `StatusPanel` + real `showStatusPanel`)
- Modify: `mobile/gazer/lib/screens/home_screen.dart` (add the ≥600dp persistent right pane, flex 2:1)
- Test: `mobile/gazer/test/screens/status_panel_test.dart`
- Test: `mobile/gazer/test/screens/home_screen_responsive_test.dart`
- Test (goldens): `mobile/gazer/test/goldens/status_panel_golden_test.dart`
- Golden fixtures: `mobile/gazer/test/goldens/status_panel_phone_portrait.png`,
  `mobile/gazer/test/goldens/status_panel_tablet_landscape.png` (generated by Step 8, committed
  as binary PNGs — not reproduced as text in this plan)

**Interfaces:**
- Consumes: `pipelineStateProvider`, `pipelineControllerProvider`, `streamStatsProvider`
  (`AsyncValue<StreamStats>`), `isOnlineProvider` (`AsyncValue<bool>`), `licenseProvider`
  (`AsyncValue<LicenseState>`), `featureFlagsProvider`, `updateInfoProvider`
  (`AsyncValue<UpdateInfo?>`), `videoDevicesProvider`, `settingsNotifierProvider`, `StreamStats`
  (`currentBitrateKbps`, `fps`, `droppedFrames`, `uptime`, `reconnectCount`, `congestionPercent`),
  `LicenseState`/`LicenseStatus`, `UpdateInfo` (`latestVersion`, `releaseUrl`), `MaskedText`
  (Task 15), `url_launcher`'s `launchUrl(Uri uri)`.
- Produces: full `StatusPanel`, `showStatusPanel(BuildContext context)` (bottom sheet <600dp /
  no-op ≥600dp), the responsive `HomeScreen` two-pane layout.
- **Font choice for goldens**: this task keeps `flutter_test`'s default test font (no
  `flutter_test_config.dart`, no bundled Roboto). The default renders text with a fixed
  placeholder glyph, which makes golden comparisons deterministic across every machine that runs
  `make mobile-run` regardless of which system fonts the host or CI container has installed —
  the goldens below therefore verify *layout and colour*, not real glyph shapes. Real-font visual
  QA is the marketing-screenshots pass (`capturing-marketing-screenshots` skill), not these tests.

- [ ] **Step 1: Write the failing widget test `test/screens/status_panel_test.dart`**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/screens/status_panel.dart';
import 'package:gazer/services/pipeline_controller.dart';
import 'package:gazer/services/reconnect_policy.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  late FakeGazerHostApi hostApi;
  late FakeSettingsRepository settingsRepo;

  setUp(() {
    hostApi = FakeGazerHostApi();
    settingsRepo = FakeSettingsRepository(
      GazerSettings.defaults().copyWith(
        target: const StreamTargetSettings(url: 'rtmp://example.com/live/mystream', streamKey: 'demo-key-0001'),
      ),
    );
  });

  List<Override> overrides() => <Override>[
        settingsRepositoryProvider.overrideWithValue(settingsRepo),
        gazerHostApiProvider.overrideWithValue(hostApi),
        // Wires hostApi.bridge into the controller under test so
        // hostApi.emitStats(...) below actually reaches streamStatsProvider
        // — see Task 11's FakeGazerHostApi doc.
        pipelineControllerProvider.overrideWithValue(
          PipelineController(host: hostApi, events: hostApi.bridge, policy: ReconnectPolicy()),
        ),
        licenseClientProvider.overrideWith(
          (Ref ref) async => FakeLicenseClient(
            LicenseState(
              status: LicenseStatus.valid,
              flags: const <String, bool>{
                'waddlebot.gazer.camera-stream': true,
                'waddlebot.gazer.uvc-capture': true,
                'waddlebot.gazer.adaptive-bitrate': true,
                'waddlebot.gazer.rtmp-auth': true,
              },
              lastFetched: DateTime.utc(2026, 9, 7),
              deviceId: 'test-device',
            ),
          ),
        ),
        isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
        updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
      ];

  testWidgets('phone layout shows the chip and opens a bottom sheet', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(390, 844));
    expect(find.byType(StatusPanel), findsNothing);
    await tester.tap(find.text('Idle'));
    await tester.pumpAndSettle();
    expect(find.byType(StatusPanel), findsOneWidget);
    expect(find.text('No capture card connected'), findsOneWidget);
  });

  testWidgets('tablet layout shows the panel as a persistent pane', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(1280, 800));
    expect(find.byType(StatusPanel), findsOneWidget);
  });

  testWidgets('renders live stats from a stats sample', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(1280, 800));
    await hostApi.emitStats(
      const StatsSample(bitrateKbps: 2200, fps: 29.8, droppedVideoFrames: 3, sentBytes: 1000, congestionPercent: 0),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('2200'), findsOneWidget);
  });

  testWidgets('masked stream key shows only the last 4 characters', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(1280, 800));
    expect(find.text('•••••••••0001'), findsOneWidget);
    expect(find.text('demo-key-0001'), findsNothing);
  });
}
```

- [ ] **Step 2: Run and confirm FAIL** — `make mobile-run CMD="flutter test test/screens/status_panel_test.dart"`
  — expected: fails on the tablet-pane assertion first (`StatusPanel` is not yet rendered inline
  by `HomeScreen`), and on the stats/masked-key assertions since the initial `StatusPanel`
  from Task 14 renders only the title:
  ```
  Expected: exactly one matching candidate
    Actual: _WidgetTypeFinder<StatusPanel>:<zero widgets with type "StatusPanel" (ignoring offstage widgets)>
  ```

- [ ] **Step 3: Replace `lib/screens/status_panel.dart` with the full implementation**

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/app_localizations.dart';
import '../models/gazer_settings.dart';
import '../models/license_state.dart';
import '../models/pipeline_state.dart';
import '../models/stream_stats.dart';
import '../models/update_info.dart';
import '../pigeon/pipeline.g.dart';
import '../providers/connectivity_provider.dart';
import '../providers/devices_provider.dart';
import '../providers/license_provider.dart';
import '../providers/pipeline_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/update_provider.dart';
import '../services/feature_flags.dart';
import '../widgets/masked_text.dart';

/// Opens the status panel as a modal bottom sheet on phones (<600dp
/// width). On tablets (≥600dp) this is a no-op — [HomeScreen] already
/// renders [StatusPanel] as a persistent right pane at that breakpoint.
void showStatusPanel(BuildContext context) {
  if (MediaQuery.of(context).size.width >= 600) return;
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (BuildContext context) => const FractionallySizedBox(
      heightFactor: 0.85,
      child: StatusPanel(),
    ),
  );
}

/// Full diagnostic panel: camera/UVC/stream state, connection details
/// (secrets masked via [MaskedText]), live stats, connectivity, license
/// status, update notice, and foreground-service state.
///
/// Rendered as a bottom sheet body (<600dp, via [showStatusPanel]) or as
/// [HomeScreen]'s persistent right pane (≥600dp) — the widget itself does
/// not know which; it always renders the same content.
class StatusPanel extends ConsumerWidget {
  const StatusPanel({super.key});

  String _streamStateLabel(AppLocalizations l10n, PipelineState s) {
    return switch (s) {
      IdleState() => l10n.statusChipIdleLabel,
      PreparingState() => l10n.statusChipPreparingLabel,
      ReadyState() => l10n.statusChipReadyLabel,
      ConnectingState() => l10n.statusChipConnectingLabel,
      StreamingState() => l10n.statusChipStreamingLabel,
      ReconnectingState() => l10n.statusChipReconnectingLabel,
      StoppingState() => l10n.statusChipStoppingLabel,
      ErrorState() => l10n.statusChipErrorLabel,
    };
  }

  String _licenseStatusLabel(AppLocalizations l10n, LicenseStatus? status) {
    return switch (status) {
      LicenseStatus.valid => l10n.statusPanelLicenseStatusValid,
      LicenseStatus.gracePeriod => l10n.statusPanelLicenseStatusGracePeriod,
      LicenseStatus.invalid => l10n.statusPanelLicenseStatusInvalid,
      LicenseStatus.unknown => l10n.statusPanelLicenseStatusUnknown,
      null => l10n.statusPanelLicenseStatusUnknown,
    };
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final PipelineController controller = ref.watch(pipelineControllerProvider);
    final PipelineState state = ref.watch(pipelineStateProvider).valueOrNull ?? controller.current;
    final StreamStats stats = ref.watch(streamStatsProvider).valueOrNull ?? StreamStats.zero();
    final bool online = ref.watch(isOnlineProvider).valueOrNull ?? false;
    final AsyncValue<LicenseState> licenseAsync = ref.watch(licenseProvider);
    final FeatureFlags flags = ref.watch(featureFlagsProvider);
    final UpdateInfo? update = ref.watch(updateInfoProvider).valueOrNull;
    final List<VideoDevice> devices = ref.watch(videoDevicesProvider).valueOrNull ?? const <VideoDevice>[];
    final GazerSettings? settings = ref.watch(settingsNotifierProvider).valueOrNull;

    final bool cameraOn = state is! IdleState && state is! ErrorState;
    final String? deviceLabel = cameraOn && devices.isNotEmpty ? devices.first.name : null;
    final Uri? url = settings == null ? null : Uri.tryParse(settings.target.url);

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(l10n.statusPanelTitle, style: Theme.of(context).textTheme.titleLarge),
            const Divider(),
            _row(context, l10n.statusPanelCameraLabel,
                cameraOn ? l10n.statusPanelCameraOnLabel(deviceLabel ?? '') : l10n.statusPanelCameraOffLabel),
            _row(context, l10n.statusPanelUvcLabel, l10n.statusPanelUvcNotConnectedLabel),
            _row(context, l10n.statusPanelStreamLabel, _streamStateLabel(l10n, state)),
            const Divider(),
            Text(l10n.statusPanelConnectionLabel, style: Theme.of(context).textTheme.titleMedium),
            if (settings != null) ...<Widget>[
              _row(context, l10n.statusPanelConnectionProtocolLabel, url?.scheme ?? ''),
              _row(context, l10n.statusPanelConnectionHostLabel, url?.host ?? ''),
              _row(context, l10n.statusPanelConnectionPathLabel, url?.path ?? ''),
              Row(
                children: <Widget>[
                  Expanded(child: Text(l10n.statusPanelConnectionKeyLabel)),
                  MaskedText(value: settings.target.streamKey ?? '', revealSemanticsLabel: l10n.revealStreamKeyLabel),
                ],
              ),
              _row(
                context,
                l10n.statusPanelConnectionAuthLabel,
                (settings.target.username?.isNotEmpty ?? false)
                    ? l10n.statusPanelConnectionAuthYes
                    : l10n.statusPanelConnectionAuthNo,
              ),
            ],
            const Divider(),
            Text(l10n.statusPanelStatsLabel, style: Theme.of(context).textTheme.titleMedium),
            Text(l10n.statusPanelBitrateLabel(stats.currentBitrateKbps.toString())),
            Text(l10n.statusPanelFpsLabel(stats.fps.toStringAsFixed(1))),
            Text(l10n.statusPanelDroppedFramesLabel(stats.droppedFrames.toString())),
            Text(l10n.statusPanelUptimeLabel(stats.uptime.inSeconds.toString())),
            Text(l10n.statusPanelReconnectCountLabel(stats.reconnectCount.toString())),
            Text(l10n.statusPanelCongestionLabel(stats.congestionPercent.toStringAsFixed(0))),
            const Divider(),
            _row(context, l10n.statusPanelConnectivityLabel,
                online ? l10n.statusPanelOnlineLabel : l10n.statusPanelOfflineLabel),
            const Divider(),
            Text(l10n.statusPanelLicenseLabel, style: Theme.of(context).textTheme.titleMedium),
            if (!flags.hasFetchedOnce)
              Text(l10n.statusPanelLicenseFetchingLabel)
            else ...<Widget>[
              _row(context, l10n.statusPanelLicenseLabel, _licenseStatusLabel(l10n, licenseAsync.valueOrNull?.status)),
              if (licenseAsync.valueOrNull?.lastFetched != null)
                Text(l10n.statusPanelLicenseLastFetchedLabel(licenseAsync.value!.lastFetched!.toIso8601String())),
            ],
            const Divider(),
            if (update == null)
              Text(l10n.statusPanelUpdateNoneLabel)
            else
              Semantics(
                link: true,
                label: l10n.statusPanelUpdateAvailableLabel(update.latestVersion),
                child: InkWell(
                  onTap: () => launchUrl(update.releaseUrl),
                  child: Text(
                    l10n.statusPanelUpdateAvailableLabel(update.latestVersion),
                    style: const TextStyle(decoration: TextDecoration.underline),
                  ),
                ),
              ),
            const Divider(),
            _row(
              context,
              l10n.statusPanelForegroundServiceLabel,
              state is! IdleState ? l10n.statusPanelForegroundServiceActiveLabel : l10n.statusPanelForegroundServiceInactiveLabel,
            ),
          ],
        ),
      ),
    );
  }

  Widget _row(BuildContext context, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: <Widget>[
          Expanded(child: Text(label)),
          Text(value, style: Theme.of(context).textTheme.bodyMedium),
        ],
      ),
    );
  }
}
```

- [ ] **Step 4: Replace `lib/screens/home_screen.dart` with the responsive two-pane layout**
  (same imports/state as Task 14, `body` changed to branch on width; full file below)

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../config/flag_keys.dart';
import '../l10n/app_localizations.dart';
import '../l10n/error_text.dart';
import '../models/gazer_settings.dart';
import '../models/pipeline_state.dart';
import '../models/validation_issue.dart';
import '../pigeon/pipeline.g.dart';
import '../providers/devices_provider.dart';
import '../providers/license_provider.dart';
import '../providers/pipeline_provider.dart';
import '../providers/settings_provider.dart';
import '../services/feature_flags.dart';
import '../services/settings_validation.dart';
import '../widgets/source_picker.dart';
import '../widgets/status_chip.dart';
import 'status_panel.dart';

/// Landing screen: source picker, Go Live / Stop controls, and the status
/// chip that opens [showStatusPanel].
///
/// Responsive per spec: below 600dp width the body is the controls
/// column only (status surfaced via the chip's bottom sheet); at 600dp
/// and above, [StatusPanel] renders as a persistent right pane at a 2:1
/// flex split against the controls column.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  String? _selectedDeviceId;

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final List<VideoDevice> devices = ref.watch(videoDevicesProvider).valueOrNull ?? const <VideoDevice>[];
    final GazerSettings? settings = ref.watch(settingsNotifierProvider).valueOrNull;
    final FeatureFlags flags = ref.watch(featureFlagsProvider);
    final PipelineController controller = ref.watch(pipelineControllerProvider);
    final PipelineState state = ref.watch(pipelineStateProvider).valueOrNull ?? controller.current;

    if (_selectedDeviceId == null && devices.isNotEmpty) {
      _selectedDeviceId = devices.first.id;
    }

    final List<ValidationIssue> issues =
        settings == null ? const <ValidationIssue>[] : validateGazerSettings(settings, flags);
    final bool canGoLive = settings != null &&
        issues.isEmpty &&
        flags.hasFetchedOnce &&
        flags.isEnabled(FlagKeys.cameraStream) &&
        _selectedDeviceId != null &&
        (state is IdleState || state is ReadyState || state is ErrorState);
    final bool showStop = state is ConnectingState || state is StreamingState || state is ReconnectingState;

    final Widget controls = Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        children: <Widget>[
          StatusChip(state: state, onTap: () => showStatusPanel(context)),
          const SizedBox(height: 16),
          Expanded(
            child: SourcePicker(
              devices: devices,
              selectedId: _selectedDeviceId,
              onSelected: (String id) => setState(() => _selectedDeviceId = id),
            ),
          ),
          if (state is ErrorState) _ErrorBanner(error: state.error),
          const SizedBox(height: 16),
          if (showStop)
            Semantics(
              label: l10n.stopButtonSemanticsLabel,
              button: true,
              child: FilledButton(
                key: const Key('stopButton'),
                onPressed: () => controller.stop(),
                child: Text(l10n.stopButtonLabel),
              ),
            )
          else
            Semantics(
              label: l10n.goLiveButtonSemanticsLabel,
              button: true,
              child: FilledButton(
                key: const Key('goLiveButton'),
                onPressed: canGoLive
                    ? () => controller.goLive(
                          settings!,
                          devices: devices,
                          videoDeviceId: _selectedDeviceId!,
                          flags: flags,
                          orientation: MediaQuery.of(context).orientation == Orientation.portrait
                              ? OutputOrientation.portrait
                              : OutputOrientation.landscape,
                        )
                    : null,
                child: Text(l10n.goLiveButtonLabel),
              ),
            ),
        ],
      ),
    );

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.homeScreenTitle),
        actions: <Widget>[
          Semantics(
            label: l10n.settingsButtonLabel,
            button: true,
            child: IconButton(
              key: const Key('settingsGearButton'),
              icon: const Icon(Icons.settings),
              tooltip: l10n.settingsButtonLabel,
              onPressed: () => context.push('/settings'),
            ),
          ),
        ],
      ),
      body: MediaQuery.of(context).size.width >= 600
          ? Row(
              children: <Widget>[
                Expanded(flex: 2, child: controls),
                const VerticalDivider(width: 1),
                const Expanded(flex: 1, child: StatusPanel()),
              ],
            )
          : controls,
    );
  }
}

/// Shows the localized message + action text for the current [GazerError].
class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.error});

  final GazerError error;

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final (String message, String action) = errorTextFor(l10n, error.code);
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(message),
            const SizedBox(height: 4),
            Text(action, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
```

- [ ] **Step 5: Run and confirm PASS** — `make mobile-run CMD="flutter test test/screens/status_panel_test.dart"`
  — expected: `00:0X +4: All tests passed!`

- [ ] **Step 6: Write the responsive-layout test `test/screens/home_screen_responsive_test.dart`**
  (new file — not a failing/passing pair since Step 4 above already implements the behaviour it
  checks; run once to confirm PASS)

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/screens/status_panel.dart';
import 'package:gazer/widgets/status_chip.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  List<Override> overrides() => <Override>[
        settingsRepositoryProvider.overrideWithValue(FakeSettingsRepository()),
        gazerHostApiProvider.overrideWithValue(FakeGazerHostApi()),
        licenseClientProvider.overrideWith(
          (Ref ref) async => FakeLicenseClient(LicenseState.initial('test-device')),
        ),
        isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
        updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
      ];

  testWidgets('phone width (390) shows the chip but not the side pane', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(390, 844));
    expect(find.byType(StatusChip), findsOneWidget);
    expect(find.byType(StatusPanel), findsNothing);
  });

  testWidgets('tablet width (1280) shows the side pane', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(1280, 800));
    expect(find.byType(StatusPanel), findsOneWidget);
  });
}
```

- [ ] **Step 7: Run and confirm PASS** — `make mobile-run CMD="flutter test test/screens/home_screen_responsive_test.dart"`
  — expected: `00:0X +2: All tests passed!`

- [ ] **Step 8: Write the golden tests, generate, and commit the fixtures**

`test/goldens/status_panel_golden_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/screens/status_panel.dart';
import 'package:gazer/widgets/status_chip.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  late FakeGazerHostApi hostApi;

  List<Override> overrides() => <Override>[
        settingsRepositoryProvider.overrideWithValue(
          FakeSettingsRepository(
            GazerSettings.defaults().copyWith(
              target: const StreamTargetSettings(url: 'rtmp://example.com/live/mystream', streamKey: 'demo-key-0001'),
            ),
          ),
        ),
        gazerHostApiProvider.overrideWithValue(hostApi),
        licenseClientProvider.overrideWith(
          (Ref ref) async => FakeLicenseClient(
            LicenseState(
              status: LicenseStatus.valid,
              flags: const <String, bool>{
                'waddlebot.gazer.camera-stream': true,
                'waddlebot.gazer.uvc-capture': true,
                'waddlebot.gazer.adaptive-bitrate': true,
                'waddlebot.gazer.rtmp-auth': true,
              },
              lastFetched: DateTime.utc(2026, 9, 7),
              deviceId: 'test-device',
            ),
          ),
        ),
        isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
        updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
      ];

  setUp(() {
    hostApi = FakeGazerHostApi();
  });

  testWidgets('status panel — phone portrait', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(390, 844));
    await tester.tap(find.byType(StatusChip));
    await tester.pumpAndSettle();
    await expectLater(find.byType(StatusPanel), matchesGoldenFile('status_panel_phone_portrait.png'));
  });

  testWidgets('status panel — tablet landscape', (WidgetTester tester) async {
    await pumpGazerApp(tester, overrides: overrides(), size: const Size(1280, 800));
    await expectLater(find.byType(StatusPanel), matchesGoldenFile('status_panel_tablet_landscape.png'));
  });
}
```

Generate and review, then run for real:
1. `make mobile-run CMD="flutter test --update-goldens test/goldens/status_panel_golden_test.dart"`
   — expected: `00:0X +2: All tests passed!` and creates
   `mobile/gazer/test/goldens/status_panel_phone_portrait.png` +
   `mobile/gazer/test/goldens/status_panel_tablet_landscape.png`.
2. Visually inspect both PNGs (layout, colours, no clipped/overlapping content) before committing
   — an `--update-goldens` run always reports PASS, so this manual look is the only gate on
   whether the fixture is actually correct, not just "whatever rendered."
3. `make mobile-run CMD="flutter test test/goldens/status_panel_golden_test.dart"` (no
   `--update-goldens`) — expected: `00:0X +2: All tests passed!` — this is the real regression
   gate; every later change to `StatusPanel` must keep passing it or intentionally regenerate.

- [ ] **Step 9: Re-run every Part C suite to confirm no regression** —
  `make mobile-run CMD="flutter test test/app_test.dart test/screens test/widgets test/goldens"`
  — expected: `00:0X +N: All tests passed!`

- [ ] **Step 10: Lint** — `make mobile-lint` — expected: `No issues found!`

- [ ] **Step 11: Commit**

```bash
git add mobile/gazer/lib/screens/status_panel.dart mobile/gazer/lib/screens/home_screen.dart \
        mobile/gazer/test/screens/status_panel_test.dart \
        mobile/gazer/test/screens/home_screen_responsive_test.dart \
        mobile/gazer/test/goldens/status_panel_golden_test.dart \
        mobile/gazer/test/goldens/status_panel_phone_portrait.png \
        mobile/gazer/test/goldens/status_panel_tablet_landscape.png
git commit -m "$(cat <<'EOF'
feat(gazer): StatusPanel and responsive two-pane HomeScreen layout

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
EOF
)"
```


# Part D — Tasks 17–20: Kotlin native bridge

Writer D scope per the skeleton contract. Consumes Tasks 1–6 (toolchain, Flutter/Android
scaffold, `io.waddlebot.gazer.pigeon.Pipeline.g.kt` generated by Task 6). Every file path, class
name, and function signature below matches the skeleton's SHARED CONTRACT verbatim unless a
verified RootEncoder 2.8.1 API constraint required documenting a deviation — every such deviation
is called out explicitly with the verification evidence, never silently substituted.

## RootEncoder 2.8.1 API verification (done before writing any code below)

Fetched directly from `raw.githubusercontent.com/pedroSG94/RootEncoder/2.8.1/...` (commit tag
`2.8.1`). Exact signatures quoted here are used verbatim in the Kotlin below.

- `library/src/main/java/com/pedro/library/base/StreamBase.kt`:
  `abstract class StreamBase(context: Context, vSource: VideoSource, aSource: AudioSource)`;
  `fun prepareVideo(width: Int, height: Int, bitrate: Int, fps: Int = 30, iFrameInterval: Int = 2, rotation: Int = 0, profile: Int = -1, level: Int = -1, recordWidth: Int = 0, recordHeight: Int = 0, recordBitrate: Int = bitrate): Boolean`;
  `fun prepareAudio(sampleRate: Int, isStereo: Boolean, bitrate: Int, echoCanceler: Boolean = false, noiseSuppressor: Boolean = false): Boolean`;
  `fun startStream(endPoint: String)`; `fun stopStream(): Boolean`; `fun setVideoBitrateOnFly(bitrate: Int)`;
  `abstract fun getStreamClient(): StreamBaseClient`; `fun release()`.
  Confirmed: `prepareVideo` only calls `videoSource.init(...)` (resolution check, no camera open);
  the actual `videoSource.start(surfaceTexture)` (camera open) happens later, inside `startStream()`.
- `library/src/main/java/com/pedro/library/generic/GenericStream.kt`:
  `class GenericStream(context: Context, private val connectChecker: ConnectChecker, videoSource: VideoSource, audioSource: AudioSource): StreamBase(context, videoSource, audioSource)`;
  `override fun getStreamClient(): GenericStreamClient`.
- `library/src/main/java/com/pedro/library/util/streamclient/GenericStreamClient.kt` (fetched in
  full): wraps `rtmpClient`/`rtspClient`/`srtClient`/`udpClient` (all `private`). Exposes
  `override fun setAuthorization(user: String?, password: String?)`, `override fun setReTries(reTries: Int)`,
  `override fun hasCongestion(percentUsed: Float): Boolean`, `override fun getSentVideoFrames(): Long`,
  `override fun getDroppedVideoFrames(): Long`, `fun addCertificates(certificates: TrustManager?)`.
  **VERIFIED GAP:** `GenericStreamClient` does **not** declare `setTlsHostVerification` and does not
  expose its wrapped `rtmpClient` — that method exists only on `RtmpStreamClient` directly (protocol-
  specific), confirmed by fetching `RtmpStreamClient.kt`: `fun setTlsHostVerification(enabled: Boolean)`.
  Since `RootEncoderEngine` wraps `GenericStream` (per the skeleton, mandatory), its
  `getStreamClient()` returns `GenericStreamClient`, not `RtmpStreamClient` — `setTlsHostVerification`
  is unreachable through the generic client in 2.8.1. `RootEncoderEngine.setTlsHostVerification` is
  therefore documented as a no-op beyond `addCertificates(null)` (system trust) — see Task 18.
- `encoder/src/main/java/com/pedro/encoder/input/sources/video/Camera2Source.kt` (fetched in full):
  `class Camera2Source(context: Context): VideoSource()`; `private var facing = CameraHelper.Facing.BACK`;
  `fun camerasAvailable(): Array<String> = camera.camerasAvailable`; `fun getCurrentCameraId() = camera.getCurrentCameraId()`;
  `fun openCameraId(id: String) { if (isRunning()) camera.reOpenCamera(id) }`;
  `fun switchCamera() { facing = if (facing == BACK) FRONT else BACK; if (isRunning()) { stop(); start(it) } }`.
  **VERIFIED DEVIATION from the task brief's assumed pattern:** `openCameraId(id)` is a no-op unless
  `isRunning()` is already true (it calls `Camera2ApiManager.reOpenCamera`, meant for switching the
  active physical camera id on an already-open source — the M2 Camera2-external use case, not cold
  facing selection). `Camera2Source` only exposes initial facing selection via `switchCamera()`,
  which flips the internal `facing` field unconditionally and only restarts the camera if already
  running — safe to call immediately after construction. `VideoSourceFactory.create()` (Task 18)
  therefore uses `switchCamera()` for `"camera:front"`, not `openCameraId`. Documented inline in the
  Kotlin KDoc, not silently substituted.
- `encoder/src/main/java/com/pedro/encoder/input/sources/video/VideoSource.kt` (fetched in full):
  `abstract class VideoSource { protected abstract fun create(width: Int, height: Int, fps: Int, rotation: Int): Boolean; abstract fun start(surfaceTexture: SurfaceTexture); abstract fun stop(); abstract fun release(); abstract fun isRunning(): Boolean; fun init(width: Int, height: Int, fps: Int, rotation: Int): Boolean }`.
- `encoder/src/main/java/com/pedro/encoder/input/sources/audio/MicrophoneSource.kt`:
  `class MicrophoneSource(var audioSource: Int = MediaRecorder.AudioSource.DEFAULT): AudioSource(), GetMicrophoneData`.
- `encoder/src/main/java/com/pedro/encoder/input/sources/audio/AudioSource.kt` (fetched in full):
  `abstract class AudioSource { protected var getMicrophoneData: GetMicrophoneData? = null; var sampleRate = 0; var isStereo = true; fun init(sampleRate: Int, isStereo: Boolean, echoCanceler: Boolean, noiseSuppressor: Boolean): Boolean; protected abstract fun create(sampleRate: Int, isStereo: Boolean, echoCanceler: Boolean, noiseSuppressor: Boolean): Boolean; abstract fun start(getMicrophoneData: GetMicrophoneData); abstract fun stop(); abstract fun isRunning(): Boolean; abstract fun release() }`.
- `encoder/src/main/java/com/pedro/encoder/input/audio/GetMicrophoneData.kt`: plain (non-`fun`)
  `interface GetMicrophoneData { fun inputPCMData(frame: Frame) }` — **no Kotlin SAM/lambda
  conversion possible**; every implementation below uses an explicit `object : GetMicrophoneData`.
- `encoder/src/main/java/com/pedro/encoder/Frame.kt` (fetched in full): two constructors —
  video `constructor(buffer: ByteArray, orientation: Int, flip: Boolean, format: Int, timeStamp: Long)`
  and audio `constructor(buffer: ByteArray, offset: Int, size: Int, timeStamp: Long)`. `SilenceAudioSource`
  uses the audio constructor.
- `common/src/main/java/com/pedro/common/ConnectChecker.kt`: `interface ConnectChecker: BitrateChecker { fun onConnectionStarted(url: String); fun onConnectionSuccess(); fun onConnectionFailed(reason: String); fun onDisconnect(); fun onAuthError(); fun onAuthSuccess() }`.
- `common/src/main/java/com/pedro/common/BitrateChecker.java`: `public interface BitrateChecker { default void onNewBitrate(long bitrate) {} default void onStreamingStats(StreamingStatsReport report) {} }` — both have empty default bodies, so `GazerPipeline` overrides only `onNewBitrate`.
- `library/src/main/java/com/pedro/library/util/BitrateAdapter.java`: `public class BitrateAdapter { public BitrateAdapter(Listener listener); public interface Listener { void onBitrateAdapted(int bitrate); } public void adaptBitrate(long actualBitrate); public void adaptBitrate(long actualBitrate, boolean hasCongestion); }` — `Listener` is a Java SAM, so a trailing Kotlin lambda converts directly (`BitrateAdapter { adapted -> ... }`).
- `encoder/src/main/java/com/pedro/encoder/input/video/Camera2ApiManager.kt`: confirmed
  `private val cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager` —
  a hard cast in the constructor, so any JUnit test that constructs a real `Camera2Source` must stub
  `context.getSystemService(Context.CAMERA_SERVICE)` to return a `CameraManager` mock or the
  constructor throws.

**Not independently re-verified in this pass** (used from the design spec / general Android SDK
knowledge, not RootEncoder-specific): `android.hardware.camera2.CameraManager`/`CameraCharacteristics`
LENS_FACING lookup (standard Android SDK, not a RootEncoder type). Exact current stable Maven Central
versions for `androidx.test:runner`, `androidx.test:rules`, `androidx.test.ext:junit` could not be
confirmed over the network in this session (search.maven.org timed out repeatedly); Task 20 pins
plausible current stable versions and includes an explicit re-verification step before trusting them,
mirroring Task 2's pattern for JUnit5/MockK/JaCoCo/ktlint.

**Pigeon Kotlin codegen assumption — VERIFIED against the actual Pigeon 28.0.0 generator source**
(`packages/pigeon/lib/src/kotlin/kotlin_generator.dart` at tag `28.0.0`, `flutter/packages`
upstream, and the `28.0.0` entry in that package's `CHANGELOG.md`): Task 6 (writer B) generates
`Pipeline.g.kt` with Pigeon 28.0.0's Kotlin conventions — Dart `int` → Kotlin `Long`, Dart `double`
→ Kotlin `Double`, enum constants in `SCREAMING_SNAKE_CASE` (e.g. `VideoDeviceKind.BACK_CAMERA`),
data classes as Kotlin `data class`. **Breaking change in 28.0.0** (this pin, not an older Pigeon):
"Updates Kotlin and Swift generators to generate `suspend` functions ... for `@FlutterApi` methods
by default, and for `@HostApi` methods annotated with `@async`. Use `@asyncCallback` if
callback-style signatures are required." The `pigeons/pipeline.dart` contract (Task 6) never uses
`@asyncCallback`, so the actual generated surface is:
- `@HostApi` `@async` methods (`requestUsbPermission`, `prepare`, `start`, `stop`) are declared as
  `suspend fun name(...): T` in the `GazerHostApi` interface — **no callback parameter**. The
  generated `companion object { fun setUp(...) }` wraps every call to the implementation in its own
  `CoroutineScope(Dispatchers.Main).launch { ... }`, catching any thrown exception and replying with
  it — `PigeonHostApiImpl` (Task 20) never manages that scope itself, it only implements the
  `suspend fun` and returns a value or throws.
- `@FlutterApi` methods (all of `GazerFlutterApi`'s — `onStateChanged`, `onStats`, `onUsbAttached`,
  `onUsbDetached`, `onAuthResult`) are likewise generated as `suspend fun name(...)`, implemented
  with `suspendCancellableCoroutine { continuation -> channel.send(...) { ... continuation.resume(...) } }`.
  Calling any of them from Kotlin therefore requires a coroutine context — this is why
  `PigeonHostApiImpl` (Task 20) carries an injectable `mainScope: CoroutineScope` and calls
  `mainScope.launch { flutterApi.onX(...) }` instead of the pre-28 pattern of
  `handler.post { flutterApi.onX(...) { } }`.
- `interface`-level `GazerHostApi.setUp(...)`/`GazerFlutterApi(binaryMessenger)` call shapes are
  unaffected (Kotlin default-parameter elision still allows the 2-arg calls already used below).
- Requires `kotlinx-coroutines-core` (compile-time: `CoroutineScope`/`launch`/`suspendCancellableCoroutine`
  are referenced directly by the generated code) and, in the running app, `kotlinx-coroutines-android`
  (`Dispatchers.Main` only resolves to a real dispatcher at runtime via that artifact's
  `ServiceLoader` factory) — both added to `android/gradle/libs.versions.toml` and
  `android/app/build.gradle.kts` in Task 2, since Task 6's generated file needs them to compile too.

All Kotlin in Tasks 17–20 is written against this verified suspend-based surface; if Task 6's
actual generated output ever differs (e.g. a future Pigeon patch release reverts the default), the
compile step in Task 18's first run against `Pipeline.g.kt` fails loudly and the fix is a rename in
this task, not a redesign.

---

### Task 17: Android manifest, permissions, service declaration, test harness

**Files:**
- Modify: `mobile/gazer/android/app/src/main/AndroidManifest.xml`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/ManifestContentTest.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/HarnessSmokeTest.kt`

**Interfaces:**
- Consumes: none new (Task 2's Flutter/Gradle scaffold, `libs.junit.jupiter` / `libs.mockk` catalog
  aliases from Task 2).
- Produces: no Kotlin API — declares the `.pipeline.StreamService` component name that Task 20
  implements; a green `ManifestContentTest`/`HarnessSmokeTest` + JaCoCo report is the deliverable.

- [ ] **Step 1: Write the failing manifest-content test.**
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/ManifestContentTest.kt`:
  ```kotlin
  package io.waddlebot.gazer

  import org.junit.jupiter.api.Assertions.assertFalse
  import org.junit.jupiter.api.Assertions.assertTrue
  import org.junit.jupiter.api.BeforeAll
  import org.junit.jupiter.api.Test
  import org.w3c.dom.Document
  import org.w3c.dom.Element
  import java.io.File
  import javax.xml.parsers.DocumentBuilderFactory

  /**
   * Parses the real AndroidManifest.xml from source with a plain XML DOM parser (no Android
   * framework, no Robolectric) and asserts the M1-required permissions, the StreamService
   * foreground-service declaration, and the M1 no-USB constraint. Exists so a manifest
   * regression (missing permission, wrong service flags) fails a JVM unit test instead of only
   * surfacing at runtime on-device.
   */
  class ManifestContentTest {

      companion object {
          private lateinit var document: Document

          @BeforeAll
          @JvmStatic
          fun loadManifest() {
              val manifestFile = File("src/main/AndroidManifest.xml")
              require(manifestFile.exists()) { "AndroidManifest.xml not found at ${manifestFile.absolutePath}" }
              val builder = DocumentBuilderFactory.newInstance().newDocumentBuilder()
              document = builder.parse(manifestFile)
          }
      }

      private fun permissionNames(): List<String> {
          val nodes = document.getElementsByTagName("uses-permission")
          return (0 until nodes.length).map { (nodes.item(it) as Element).getAttribute("android:name") }
      }

      @Test
      fun `declares camera and microphone permissions`() {
          val names = permissionNames()
          assertTrue(names.contains("android.permission.CAMERA"))
          assertTrue(names.contains("android.permission.RECORD_AUDIO"))
      }

      @Test
      fun `declares foreground service permissions for camera and microphone`() {
          val names = permissionNames()
          assertTrue(names.contains("android.permission.FOREGROUND_SERVICE"))
          assertTrue(names.contains("android.permission.FOREGROUND_SERVICE_CAMERA"))
          assertTrue(names.contains("android.permission.FOREGROUND_SERVICE_MICROPHONE"))
      }

      @Test
      fun `declares network, notification and wake lock permissions`() {
          val names = permissionNames()
          assertTrue(names.contains("android.permission.INTERNET"))
          assertTrue(names.contains("android.permission.POST_NOTIFICATIONS"))
          assertTrue(names.contains("android.permission.WAKE_LOCK"))
      }

      @Test
      fun `declares no USB permissions or features in M1`() {
          val names = permissionNames()
          assertFalse(names.any { it.contains("USB", ignoreCase = true) })
          val features = document.getElementsByTagName("uses-feature")
          val featureNames = (0 until features.length).map { (features.item(it) as Element).getAttribute("android:name") }
          assertFalse(featureNames.any { it.contains("usb", ignoreCase = true) })
      }

      @Test
      fun `declares StreamService as a non-exported camera and microphone foreground service`() {
          val services = document.getElementsByTagName("service")
          val streamService = (0 until services.length)
              .map { services.item(it) as Element }
              .firstOrNull { it.getAttribute("android:name") == ".pipeline.StreamService" }
          requireNotNull(streamService) { "StreamService not declared in AndroidManifest.xml" }
          val serviceType = streamService.getAttribute("android:foregroundServiceType")
          assertTrue(serviceType.contains("camera"))
          assertTrue(serviceType.contains("microphone"))
          assertFalse(streamService.getAttribute("android:exported").toBoolean())
      }
  }
  ```

- [ ] **Step 2: Run — expected FAIL.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.ManifestContentTest'"`
  Expected: 5 tests run, ≥4 failures — the Task 2 `flutter create` template manifest declares only
  `INTERNET` (Flutter's default) and has no `CAMERA`/`RECORD_AUDIO`/`FOREGROUND_SERVICE*`/
  `POST_NOTIFICATIONS`/`WAKE_LOCK` permissions and no `.pipeline.StreamService`, so
  `declares StreamService as a non-exported...` fails on `requireNotNull` and the permission tests
  fail their `assertTrue` calls.

- [ ] **Step 3: Implement the full manifest.**
  `mobile/gazer/android/app/src/main/AndroidManifest.xml`:
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <manifest xmlns:android="http://schemas.android.com/apk/res/android">

      <uses-permission android:name="android.permission.CAMERA" />
      <uses-permission android:name="android.permission.RECORD_AUDIO" />
      <uses-permission android:name="android.permission.INTERNET" />
      <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
      <uses-permission android:name="android.permission.FOREGROUND_SERVICE_CAMERA" />
      <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MICROPHONE" />
      <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
      <uses-permission android:name="android.permission.WAKE_LOCK" />

      <uses-feature android:name="android.hardware.camera" android:required="true" />
      <uses-feature android:name="android.hardware.camera.autofocus" android:required="false" />
      <uses-feature android:name="android.hardware.microphone" android:required="true" />

      <application
          android:label="Gazer"
          android:name="${applicationName}"
          android:icon="@mipmap/ic_launcher">
          <activity
              android:name=".MainActivity"
              android:exported="true"
              android:launchMode="singleTop"
              android:theme="@style/LaunchTheme"
              android:configChanges="orientation|keyboardHidden|keyboard|screenSize|smallestScreenSize|locale|layoutDirection|fontScale|screenLayout|density|uiMode"
              android:hardwareAccelerated="true"
              android:windowSoftInputMode="adjustResize">
              <meta-data
                  android:name="io.flutter.embedding.android.NormalTheme"
                  android:resource="@style/NormalTheme" />
              <intent-filter>
                  <action android:name="android.intent.action.MAIN" />
                  <category android:name="android.intent.category.LAUNCHER" />
              </intent-filter>
          </activity>

          <service
              android:name=".pipeline.StreamService"
              android:foregroundServiceType="camera|microphone"
              android:exported="false" />

          <meta-data
              android:name="flutterEmbedding"
              android:value="2" />
      </application>
  </manifest>
  ```
  No `android.hardware.usb.host` feature, no USB permission — M1 has no UVC support (deferred to
  M2/M3 per the spec's Milestones section).

- [ ] **Step 4: Run — expected PASS.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.ManifestContentTest'"`
  Expected: `5 tests completed, 0 failed`.

- [ ] **Step 5: Write the JUnit5 harness smoke test.**
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/HarnessSmokeTest.kt`:
  ```kotlin
  package io.waddlebot.gazer

  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.Assertions.assertNotNull
  import org.junit.jupiter.api.Test

  /**
   * Trivial JVM-only tests proving the JUnit5 + JaCoCo unit-test harness (Task 2) actually
   * executes and reports coverage for this module. A canary: if gradle/test wiring breaks, this
   * fails loudly here instead of every later Kotlin test in Tasks 18–20 silently not running.
   */
  class HarnessSmokeTest {

      @Test
      fun `arithmetic sanity check proves the JUnit5 runner executes`() {
          assertEquals(4, 2 + 2)
      }

      @Test
      fun `MainActivity can be constructed by the JVM unit test harness`() {
          // Plain object allocation only (no lifecycle call) - proves MainActivity links against
          // the Flutter embedding classpath from the unit-test target too, and gives JaCoCo a
          // non-trivial denominator for this class ahead of Task 20's real wiring.
          assertNotNull(MainActivity())
      }
  }
  ```

- [ ] **Step 6: Verify `libs.junit.jupiter` / `libs.mockk` catalog aliases exist (Task 2 output).**
  `make mobile-run CMD="grep -q 'junit-jupiter' android/gradle/libs.versions.toml && grep -q 'mockk' android/gradle/libs.versions.toml && echo ALIASES_OK"`
  Expected stdout: `ALIASES_OK`. If missing, stop — Task 2 is incomplete; do not proceed by
  hand-rolling a dependency version here.

- [ ] **Step 7: Run the full Kotlin unit-test + coverage target — expected PASS with a report path.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest jacocoTestReport"`
  Expected: `BUILD SUCCESSFUL`, output includes
  `Generating HTML report... file:///work/android/app/build/reports/jacoco/jacocoTestReport/html/index.html`.
  Then assert the file actually exists on the host (non-zero-denominator check, not just trusting
  the log line): `test -f mobile/gazer/android/app/build/reports/jacoco/jacocoTestReport/html/index.html && echo REPORT_OK`.

- [ ] **Step 8: Confirm the debug APK still builds inside the container.**
  `make mobile-run CMD="flutter build apk --debug"`
  Expected: `BUILD SUCCESSFUL`, `Built build/app/outputs/flutter-apk/app-debug.apk`.

- [ ] **Step 9: Lint.**
  `make mobile-lint`
  Expected: ktlint + gradle lint + `flutter analyze` all pass, 0 issues in the two new files.

- [ ] **Step 10: Commit.**
  ```bash
  git add mobile/gazer/android/app/src/main/AndroidManifest.xml \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/ManifestContentTest.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/HarnessSmokeTest.kt
  git commit -m "$(cat <<'EOF'
  feat(gazer): declare M1 Android permissions, StreamService, and JUnit5+JaCoCo harness smoke tests

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 18: StreamEngine, RootEncoderEngine, source factories

**Files:**
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamEngine.kt`
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/VideoSourceFactory.kt`
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/AudioSourceFactory.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/VideoSourceFactoryTest.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/AudioSourceFactoryTest.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/SilenceAudioSourceTest.kt`
- Modify: `mobile/gazer/android/app/build.gradle.kts` (narrow JaCoCo exclusion for `RootEncoderEngine`)

**Interfaces:**
- Consumes: RootEncoder 2.8.1 `com.pedro.library.generic.GenericStream`, `com.pedro.library.base.StreamBase`,
  `com.pedro.encoder.input.sources.video.{VideoSource, Camera2Source}`,
  `com.pedro.encoder.input.sources.audio.{AudioSource, MicrophoneSource}`, `com.pedro.encoder.Frame`,
  `com.pedro.encoder.input.audio.GetMicrophoneData`, `com.pedro.common.ConnectChecker` — all verified
  above; Pigeon `io.waddlebot.gazer.pigeon.{VideoDevice, VideoDeviceKind, AudioDevice, AudioDeviceKind}` from Task 6.
- Produces (verbatim per skeleton):
  `interface StreamEngine { fun prepareVideo(width: Int, height: Int, bitrateBps: Int, fps: Int, rotation: Int): Boolean; fun prepareAudio(sampleRate: Int, stereo: Boolean, bitrateBps: Int): Boolean; fun startStream(url: String); fun stopStream(): Boolean; fun setVideoBitrateOnFly(bitrateBps: Int); fun setAuthorization(user: String?, password: String?); fun setReTries(n: Int); fun setTlsHostVerification(enabled: Boolean); fun sentVideoFrames(): Long; fun droppedVideoFrames(): Long; fun hasCongestion(percentUsed: Float): Boolean; fun release() }`;
  `class RootEncoderEngine(context: Context, listener: ConnectChecker, video: VideoSource, audio: AudioSource) : StreamEngine`;
  `class VideoSourceFactory(context: Context, cameraIds: CameraIds) { fun list(): List<VideoDevice>; fun create(deviceId: String): VideoSource }` with
  `interface CameraIds { fun byFacing(facing: Int): String? }` and `class CameraManagerIds(cameraManager: CameraManager) : CameraIds`;
  `class AudioSourceFactory { fun list(): List<AudioDevice>; fun create(deviceId: String): AudioSource }`;
  `class SilenceAudioSource : AudioSource()`.
  **RootEncoderEngine itself has no JUnit test in this task** — it constructs a real
  `GenericStream`/`Camera2ApiManager`/`MediaCodec` stack that cannot run on the JVM unit-test
  target; it is exercised indirectly by Task 20's instrumented `StreamServiceTest`, and excluded
  from the JaCoCo coverage denominator in Step 8 below for the same reason (mirrors the design
  spec's own precedent for native/JNI code: "no coverage number claimed").

  **`VideoSourceFactory.create()` behaviour:** builds a bare `Camera2Source(context)` for
  `"camera:back"` and calls `switchCamera()` (never `openCameraId`) for `"camera:front"` — see the
  verified `Camera2Source` gap at the top of this file: `openCameraId(id)` is a no-op unless the
  source `isRunning()` already, so it cannot select the initial facing before `prepare()`/`start()`;
  `switchCamera()` flips the internal facing field unconditionally and only restarts the camera if
  already running, which is safe to call immediately after construction. Full rationale is in the
  KDoc on `create()` in Step 3 below.

- [ ] **Step 1: Write the failing VideoSourceFactory test.**
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/VideoSourceFactoryTest.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline.sources

  import android.content.Context
  import android.hardware.camera2.CameraCharacteristics
  import android.hardware.camera2.CameraManager
  import io.mockk.every
  import io.mockk.mockk
  import io.waddlebot.gazer.pigeon.VideoDeviceKind
  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.Assertions.assertThrows
  import org.junit.jupiter.api.Test

  /**
   * VideoSourceFactory covers list()/create() using a fake CameraIds, so no real CameraManager or
   * camera hardware is required. Camera2Source's actual capture behaviour is exercised only on an
   * emulator/device via Task 20's instrumented StreamServiceTest.
   */
  class VideoSourceFactoryTest {

      private class FakeCameraIds(private val ids: Map<Int, String>) : CameraIds {
          override fun byFacing(facing: Int): String? = ids[facing]
      }

      /** Context stub satisfying Camera2ApiManager's constructor (Context.getSystemService(CAMERA_SERVICE) as CameraManager). */
      private fun fakeContext(): Context {
          val context = mockk<Context>()
          val cameraManager = mockk<CameraManager>(relaxed = true)
          every { context.getSystemService(Context.CAMERA_SERVICE) } returns cameraManager
          return context
      }

      @Test
      fun `list returns both cameras when both facings exist`() {
          val ids = FakeCameraIds(
              mapOf(
                  CameraCharacteristics.LENS_FACING_BACK to "0",
                  CameraCharacteristics.LENS_FACING_FRONT to "1",
              ),
          )
          val devices = VideoSourceFactory(fakeContext(), ids).list()

          assertEquals(2, devices.size)
          assertEquals("camera:back", devices[0].id)
          assertEquals(VideoDeviceKind.BACK_CAMERA, devices[0].kind)
          assertEquals("camera:front", devices[1].id)
          assertEquals(VideoDeviceKind.FRONT_CAMERA, devices[1].kind)
      }

      @Test
      fun `list omits front camera when hardware lacks it`() {
          val ids = FakeCameraIds(mapOf(CameraCharacteristics.LENS_FACING_BACK to "0"))
          val devices = VideoSourceFactory(fakeContext(), ids).list()

          assertEquals(1, devices.size)
          assertEquals("camera:back", devices[0].id)
      }

      @Test
      fun `list returns empty when the device has no camera`() {
          val devices = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap())).list()

          assertEquals(0, devices.size)
      }

      @Test
      fun `create builds a back camera source without throwing`() {
          val factory = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap()))

          val source = factory.create("camera:back")

          assertEquals(false, source.isRunning())
      }

      @Test
      fun `create builds a front camera source without throwing`() {
          val factory = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap()))

          val source = factory.create("camera:front")

          assertEquals(false, source.isRunning())
      }

      @Test
      fun `create rejects an unknown device id`() {
          val factory = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap()))

          assertThrows(IllegalArgumentException::class.java) { factory.create("camera:external") }
      }
  }
  ```

- [ ] **Step 2: Run — expected FAIL.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.sources.VideoSourceFactoryTest'"`
  Expected: compile error — `unresolved reference: VideoSourceFactory`, `unresolved reference: CameraIds`.

- [ ] **Step 3: Implement VideoSourceFactory.kt.**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/VideoSourceFactory.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline.sources

  import android.content.Context
  import android.hardware.camera2.CameraCharacteristics
  import android.hardware.camera2.CameraManager
  import com.pedro.encoder.input.sources.video.Camera2Source
  import com.pedro.encoder.input.sources.video.VideoSource
  import io.waddlebot.gazer.pigeon.VideoDevice
  import io.waddlebot.gazer.pigeon.VideoDeviceKind

  /**
   * Resolves a Pigeon video device id ("camera:back"/"camera:front") to a physical Android
   * camera, indirected behind an interface so tests can fake CameraManager without Robolectric.
   */
  interface CameraIds {
      /** Returns the camera id for [facing] (a CameraCharacteristics.LENS_FACING_* constant), or null if absent. */
      fun byFacing(facing: Int): String?
  }

  /** Production [CameraIds] backed by the real [CameraManager]. */
  class CameraManagerIds(private val cameraManager: CameraManager) : CameraIds {
      override fun byFacing(facing: Int): String? {
          for (id in cameraManager.cameraIdList) {
              val characteristics = cameraManager.getCameraCharacteristics(id)
              if (characteristics.get(CameraCharacteristics.LENS_FACING) == facing) {
                  return id
              }
          }
          return null
      }
  }

  /**
   * Lists and creates RootEncoder [VideoSource]s for M1's phone-camera-only device set. UVC and
   * Camera2-external sources are out of scope until M2 (see the M2 plan).
   */
  class VideoSourceFactory(private val context: Context, private val cameraIds: CameraIds) {

      /** Lists back/front camera as [VideoDevice]s, omitting any facing the hardware lacks. */
      fun list(): List<VideoDevice> {
          val devices = mutableListOf<VideoDevice>()
          if (cameraIds.byFacing(CameraCharacteristics.LENS_FACING_BACK) != null) {
              devices.add(VideoDevice(id = "camera:back", kind = VideoDeviceKind.BACK_CAMERA, name = "Back camera"))
          }
          if (cameraIds.byFacing(CameraCharacteristics.LENS_FACING_FRONT) != null) {
              devices.add(VideoDevice(id = "camera:front", kind = VideoDeviceKind.FRONT_CAMERA, name = "Front camera"))
          }
          return devices
      }

      /**
       * Builds a [Camera2Source] for [deviceId]. VERIFIED (RootEncoder 2.8.1): Camera2Source
       * defaults to CameraHelper.Facing.BACK and only exposes facing selection via
       * switchCamera(), which flips the internal facing field unconditionally and only restarts
       * the camera if already running - safe to call immediately after construction, before
       * prepare()/start(). openCameraId(id) is NOT usable here: it is a no-op unless the source
       * isRunning() already (it calls Camera2ApiManager.reOpenCamera, meant for switching
       * physical camera ids on an already-open external/Camera2 source in M2, not cold facing
       * selection).
       */
      fun create(deviceId: String): VideoSource {
          val source = Camera2Source(context)
          when (deviceId) {
              "camera:back" -> Unit
              "camera:front" -> source.switchCamera()
              else -> throw IllegalArgumentException("Unknown video device id: $deviceId")
          }
          return source
      }
  }
  ```

- [ ] **Step 4: Run — expected PASS.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.sources.VideoSourceFactoryTest'"`
  Expected: `6 tests completed, 0 failed`.

- [ ] **Step 5: Write the failing AudioSourceFactory + SilenceAudioSource tests.**
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/AudioSourceFactoryTest.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline.sources

  import com.pedro.encoder.input.sources.audio.MicrophoneSource
  import io.waddlebot.gazer.pigeon.AudioDeviceKind
  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.Assertions.assertThrows
  import org.junit.jupiter.api.Assertions.assertTrue
  import org.junit.jupiter.api.Test

  class AudioSourceFactoryTest {

      @Test
      fun `list returns mic and silence`() {
          val devices = AudioSourceFactory().list()

          assertEquals(2, devices.size)
          assertEquals("audio:mic", devices[0].id)
          assertEquals(AudioDeviceKind.MIC, devices[0].kind)
          assertEquals("audio:silence", devices[1].id)
          assertEquals(AudioDeviceKind.SILENCE, devices[1].kind)
      }

      @Test
      fun `create builds a MicrophoneSource for audio-mic`() {
          val source = AudioSourceFactory().create("audio:mic")

          assertTrue(source is MicrophoneSource)
      }

      @Test
      fun `create builds a SilenceAudioSource for audio-silence`() {
          val source = AudioSourceFactory().create("audio:silence")

          assertTrue(source is SilenceAudioSource)
      }

      @Test
      fun `create rejects an unknown device id`() {
          assertThrows(IllegalArgumentException::class.java) { AudioSourceFactory().create("audio:usb") }
      }
  }
  ```
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/SilenceAudioSourceTest.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline.sources

  import com.pedro.encoder.Frame
  import com.pedro.encoder.input.audio.GetMicrophoneData
  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.Assertions.assertFalse
  import org.junit.jupiter.api.Assertions.assertTrue
  import org.junit.jupiter.api.Test
  import java.util.concurrent.CopyOnWriteArrayList
  import java.util.concurrent.CountDownLatch
  import java.util.concurrent.TimeUnit

  /**
   * SilenceAudioSource must behave like any other RootEncoder AudioSource: start() returns
   * immediately and frames arrive asynchronously via GetMicrophoneData, sized for the sample
   * rate and channel count passed to init().
   */
  class SilenceAudioSourceTest {

      @Test
      fun `delivers zeroed PCM16 frames of the expected byte length within 200ms`() {
          val sampleRate = 48000
          val isStereo = true
          val expectedBytes = (sampleRate * 20 / 1000) * 2 * 2 // 20ms chunk * stereo * PCM16

          val received = CopyOnWriteArrayList<Frame>()
          val latch = CountDownLatch(1)
          val sink = object : GetMicrophoneData {
              override fun inputPCMData(frame: Frame) {
                  received.add(frame)
                  latch.countDown()
              }
          }

          val source = SilenceAudioSource()
          assertTrue(source.init(sampleRate, isStereo, echoCanceler = false, noiseSuppressor = false))
          source.start(sink)

          assertTrue(latch.await(200, TimeUnit.MILLISECONDS), "no frame delivered within 200ms")
          assertEquals(expectedBytes, received.first().size)
          assertTrue(received.first().buffer.all { it == 0.toByte() })

          source.stop()
          assertFalse(source.isRunning())
      }

      @Test
      fun `isRunning reflects start and stop`() {
          val source = SilenceAudioSource()
          source.init(48000, isStereo = false, echoCanceler = false, noiseSuppressor = false)
          assertFalse(source.isRunning())

          source.start(object : GetMicrophoneData {
              override fun inputPCMData(frame: Frame) = Unit
          })
          assertTrue(source.isRunning())

          source.stop()
          assertFalse(source.isRunning())
      }
  }
  ```

- [ ] **Step 6: Run — expected FAIL.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.sources.AudioSourceFactoryTest' --tests 'io.waddlebot.gazer.pipeline.sources.SilenceAudioSourceTest'"`
  Expected: compile error — `unresolved reference: AudioSourceFactory`, `unresolved reference: SilenceAudioSource`.

- [ ] **Step 7: Implement AudioSourceFactory.kt (includes SilenceAudioSource).**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/AudioSourceFactory.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline.sources

  import com.pedro.encoder.Frame
  import com.pedro.encoder.input.audio.GetMicrophoneData
  import com.pedro.encoder.input.sources.audio.AudioSource
  import com.pedro.encoder.input.sources.audio.MicrophoneSource
  import io.waddlebot.gazer.pigeon.AudioDevice
  import io.waddlebot.gazer.pigeon.AudioDeviceKind
  import java.util.concurrent.atomic.AtomicBoolean

  /**
   * Lists and creates RootEncoder [AudioSource]s for M1: phone mic or synthesized silence. USB
   * audio is out of scope until M2.
   */
  class AudioSourceFactory {

      /** Lists the mic and silence audio devices - both always available. */
      fun list(): List<AudioDevice> = listOf(
          AudioDevice(id = "audio:mic", kind = AudioDeviceKind.MIC, name = "Phone microphone"),
          AudioDevice(id = "audio:silence", kind = AudioDeviceKind.SILENCE, name = "Silence"),
      )

      /** Builds the [AudioSource] for [deviceId]. */
      fun create(deviceId: String): AudioSource = when (deviceId) {
          "audio:mic" -> MicrophoneSource()
          "audio:silence" -> SilenceAudioSource()
          else -> throw IllegalArgumentException("Unknown audio device id: $deviceId")
      }
  }

  /**
   * [AudioSource] that feeds zeroed PCM16 frames at the configured sample rate instead of reading
   * a microphone - selected by the user for streams that should carry no live audio. Runs its own
   * daemon thread so it behaves like every other AudioSource: start() returns immediately and
   * frames arrive asynchronously via [GetMicrophoneData].
   */
  class SilenceAudioSource : AudioSource() {

      private companion object {
          const val CHUNK_MILLIS = 20L
      }

      private val running = AtomicBoolean(false)
      private var thread: Thread? = null

      override fun create(sampleRate: Int, isStereo: Boolean, echoCanceler: Boolean, noiseSuppressor: Boolean): Boolean = true

      override fun start(getMicrophoneData: GetMicrophoneData) {
          this.getMicrophoneData = getMicrophoneData
          if (isRunning()) return
          running.set(true)
          val channels = if (isStereo) 2 else 1
          val samplesPerChunk = (sampleRate * CHUNK_MILLIS / 1000L).toInt().coerceAtLeast(1)
          val bufferSize = samplesPerChunk * channels * 2 // PCM16 = 2 bytes/sample
          val silence = ByteArray(bufferSize)
          val sink = getMicrophoneData
          thread = Thread({
              while (running.get()) {
                  sink.inputPCMData(Frame(silence, 0, silence.size, System.nanoTime() / 1000))
                  try {
                      Thread.sleep(CHUNK_MILLIS)
                  } catch (_: InterruptedException) {
                      return@Thread
                  }
              }
          }, "gazer-silence-audio").apply {
              isDaemon = true
              start()
          }
      }

      override fun stop() {
          running.set(false)
          thread?.interrupt()
          thread?.join(CHUNK_MILLIS * 2)
          thread = null
      }

      override fun isRunning(): Boolean = running.get()

      override fun release() = Unit
  }
  ```

- [ ] **Step 8: Run — expected PASS.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.sources.AudioSourceFactoryTest' --tests 'io.waddlebot.gazer.pipeline.sources.SilenceAudioSourceTest'"`
  Expected: `6 tests completed, 0 failed`.

- [ ] **Step 9: Implement StreamEngine.kt + RootEncoderEngine, and exclude RootEncoderEngine from the JaCoCo denominator.**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamEngine.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import android.content.Context
  import com.pedro.common.ConnectChecker
  import com.pedro.encoder.input.sources.audio.AudioSource
  import com.pedro.encoder.input.sources.video.VideoSource
  import com.pedro.library.generic.GenericStream

  /**
   * Bridge between GazerPipeline and whatever RTMP/H.264 implementation backs it. Exists so
   * GazerPipeline's state machine and tests never touch RootEncoder types directly - only this
   * narrow surface, verified against RootEncoder 2.8.1's StreamBase and GenericStreamClient.
   */
  interface StreamEngine {
      fun prepareVideo(width: Int, height: Int, bitrateBps: Int, fps: Int, rotation: Int): Boolean
      fun prepareAudio(sampleRate: Int, stereo: Boolean, bitrateBps: Int): Boolean
      fun startStream(url: String)
      fun stopStream(): Boolean
      fun setVideoBitrateOnFly(bitrateBps: Int)
      fun setAuthorization(user: String?, password: String?)
      fun setReTries(n: Int)
      fun setTlsHostVerification(enabled: Boolean)
      fun sentVideoFrames(): Long
      fun droppedVideoFrames(): Long
      fun hasCongestion(percentUsed: Float): Boolean
      fun release()
  }

  /**
   * Wraps RootEncoder's GenericStream (Camera2/Mic -> MediaCodec H.264/AAC -> RTMP/RTMPS) behind
   * StreamEngine. Deliberately thin: every method is a 1:1 forward to a verified RootEncoder 2.8.1
   * API, so GazerPipelineTest exercises this class only indirectly via a fake StreamEngine -
   * RootEncoderEngine itself is exercised by the instrumented StreamServiceTest in Task 20, the
   * only place a real Camera2/MediaCodec/socket stack can run.
   */
  class RootEncoderEngine(
      context: Context,
      connectChecker: ConnectChecker,
      videoSource: VideoSource,
      audioSource: AudioSource,
  ) : StreamEngine {

      private val stream = GenericStream(context, connectChecker, videoSource, audioSource)

      override fun prepareVideo(width: Int, height: Int, bitrateBps: Int, fps: Int, rotation: Int): Boolean =
          stream.prepareVideo(width, height, bitrateBps, fps, rotation = rotation)

      override fun prepareAudio(sampleRate: Int, stereo: Boolean, bitrateBps: Int): Boolean =
          stream.prepareAudio(sampleRate, stereo, bitrateBps)

      override fun startStream(url: String) {
          stream.startStream(url)
      }

      override fun stopStream(): Boolean = stream.stopStream()

      override fun setVideoBitrateOnFly(bitrateBps: Int) {
          stream.setVideoBitrateOnFly(bitrateBps)
      }

      override fun setAuthorization(user: String?, password: String?) {
          stream.getStreamClient().setAuthorization(user, password)
      }

      override fun setReTries(n: Int) {
          stream.getStreamClient().setReTries(n)
      }

      /**
       * VERIFIED GAP (RootEncoder 2.8.1): `GenericStreamClient` — the type returned by
       * `GenericStream.getStreamClient()` — does not declare `setTlsHostVerification`; only the
       * protocol-specific `RtmpStreamClient` does, and `GenericStreamClient` does not expose its
       * wrapped `RtmpStreamClient`. [enabled] is therefore accepted but otherwise unused;
       * `addCertificates(null)` (system trust) is the closest control available on the generic
       * client, so this override is a documented no-op beyond that — the [StreamEngine] interface
       * keeps the method (it is part of the shared contract every engine implements), only this
       * RootEncoder-backed implementation cannot honor it fully in 2.8.1.
       */
      override fun setTlsHostVerification(enabled: Boolean) {
          stream.getStreamClient().addCertificates(null)
      }

      override fun sentVideoFrames(): Long = stream.getStreamClient().getSentVideoFrames()

      override fun droppedVideoFrames(): Long = stream.getStreamClient().getDroppedVideoFrames()

      override fun hasCongestion(percentUsed: Float): Boolean = stream.getStreamClient().hasCongestion(percentUsed)

      override fun release() {
          stream.release()
      }
  }
  ```
  Modify `mobile/gazer/android/app/build.gradle.kts` — add (near the existing JaCoCo config from
  Task 2):
  ```kotlin
  tasks.withType<JacocoReport>().configureEach {
      classDirectories.setFrom(
          classDirectories.files.map {
              fileTree(it) {
                  // RootEncoderEngine wraps RootEncoder's GenericStream (real Camera2/MediaCodec/
                  // socket stack); it cannot run on the JVM unit-test target and is exercised by
                  // the instrumented StreamServiceTest (Task 20) instead. Excluded here so the
                  // JaCoCo >=90% gate does not count admittedly-uncovered forwarding calls
                  // against a class that unit tests structurally cannot reach - narrow, single
                  // class, documented, not a blanket exclusion.
                  exclude("**/pipeline/RootEncoderEngine.class")
              }
          },
      )
  }
  ```

- [ ] **Step 10: Run — expected PASS (compiles, existing tests still green).**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest jacocoTestReport"`
  Expected: `BUILD SUCCESSFUL`, all prior + new tests green, JaCoCo report generated excluding
  `RootEncoderEngine.class` from the denominator.

- [ ] **Step 11: Lint.**
  `make mobile-lint`

- [ ] **Step 12: Commit.**
  ```bash
  git add mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamEngine.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/VideoSourceFactory.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/sources/AudioSourceFactory.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/VideoSourceFactoryTest.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/AudioSourceFactoryTest.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/sources/SilenceAudioSourceTest.kt \
          mobile/gazer/android/app/build.gradle.kts
  git commit -m "$(cat <<'EOF'
  feat(gazer): add StreamEngine/RootEncoderEngine and video/audio source factories

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 19: ErrorMapper, StatsSampler, GazerPipeline

**Files:**
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/ErrorMapper.kt`
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StatsSampler.kt`
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/PipelineListener.kt`
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/GazerPipeline.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/ErrorMapperTest.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/StatsSamplerTest.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/GazerPipelineTest.kt`

**Interfaces:**
- Consumes: `StreamEngine`, `VideoSourceFactory`, `AudioSourceFactory` (Task 18); RootEncoder
  `ConnectChecker`/`BitrateAdapter` (verified above); Pigeon `StreamConfig`, `StreamTarget`,
  `PrepareResult`, `StatsSample`, `StateEvent`, `NativePipelineState`, `GazerErrorCode`,
  `OutputOrientation` (Task 6).
- Produces (verbatim per skeleton, `StatsSampler` extended with an injectable `Ticker` per the
  task brief's explicit instruction to make ticks testable):
  `object ErrorMapper { fun fromReason(reason: String): GazerErrorCode }`;
  `class StatsSampler(engine: () -> StreamEngine?, ticker: Ticker = ScheduledExecutorTicker(), intervalMs: Long = 1000, onSample: (StatsSample) -> Unit)` with `fun onBitrate(bps: Long)`, `fun start()`, `fun stop()`, `fun tick()`;
  `interface PipelineListener { fun onState(state: NativePipelineState, error: GazerErrorCode? = null, detail: String? = null); fun onStats(sample: StatsSample); fun onAuthResult(ok: Boolean) }`;
  `class GazerPipeline(engineFactory: (ConnectChecker, VideoSource, AudioSource) -> StreamEngine, videoSources: VideoSourceFactory, audioSources: AudioSourceFactory, listener: PipelineListener, statsSampler: StatsSampler) : ConnectChecker` with `fun prepare(config: StreamConfig): PrepareResult`, `fun start(target: StreamTarget)`, `fun stop()`, `fun setVideoBitrate(kbps: Int)`, `val state: NativePipelineState`.

- [ ] **Step 1: Write the failing ErrorMapper test.**
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/ErrorMapperTest.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import io.waddlebot.gazer.pigeon.GazerErrorCode
  import org.junit.jupiter.api.Assertions.assertAll
  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.Test

  /** Table-driven coverage of every ErrorMapper.fromReason rule, including case-insensitivity. */
  class ErrorMapperTest {

      private val cases = listOf(
          "401 Unauthorized" to GazerErrorCode.RTMP_AUTH_FAILED,
          "auth failed" to GazerErrorCode.RTMP_AUTH_FAILED,
          "AUTH FAILED" to GazerErrorCode.RTMP_AUTH_FAILED,
          "Unauthorized access" to GazerErrorCode.RTMP_AUTH_FAILED,
          "UNAUTHORIZED" to GazerErrorCode.RTMP_AUTH_FAILED,
          "Connection timeout" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "TIMEOUT" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "Connection refused" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "REFUSED" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "Host unreachable" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "UNREACHABLE" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "Failed to connect" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "FAILED TO CONNECT" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "java.net.UnknownHostException: example.com" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "UNKNOWNHOST" to GazerErrorCode.RTMP_CONNECT_FAILED,
          "Encoder error" to GazerErrorCode.ENCODER_FAILED,
          "ENCODER" to GazerErrorCode.ENCODER_FAILED,
          "codec configuration failed" to GazerErrorCode.ENCODER_FAILED,
          "CODEC" to GazerErrorCode.ENCODER_FAILED,
          "some other reason" to GazerErrorCode.UNKNOWN,
          "" to GazerErrorCode.UNKNOWN,
      )

      @Test
      fun `maps every reason string to the correct GazerErrorCode`() {
          assertAll(
              cases.map { (reason, expected) ->
                  { assertEquals(expected, ErrorMapper.fromReason(reason), "reason=\"$reason\"") }
              },
          )
      }
  }
  ```

- [ ] **Step 2: Run — expected FAIL.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.ErrorMapperTest'"`
  Expected: compile error — `unresolved reference: ErrorMapper`.

- [ ] **Step 3: Implement ErrorMapper.kt.**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/ErrorMapper.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import io.waddlebot.gazer.pigeon.GazerErrorCode

  /**
   * Classifies RootEncoder's free-text ConnectChecker.onConnectionFailed(reason) strings into a
   * Pigeon GazerErrorCode Dart can branch on - RootEncoder never returns a structured error type,
   * only reason strings, so this table is the single place that interprets them.
   */
  object ErrorMapper {
      private val authMarkers = listOf("401", "auth", "unauthorized")
      private val connectMarkers = listOf("timeout", "refused", "unreachable", "failed to connect", "unknownhost")
      private val encoderMarkers = listOf("encoder", "codec")

      /** Maps a ConnectChecker reason string to a GazerErrorCode, case-insensitively. */
      fun fromReason(reason: String): GazerErrorCode {
          val lower = reason.lowercase()
          return when {
              authMarkers.any { lower.contains(it) } -> GazerErrorCode.RTMP_AUTH_FAILED
              connectMarkers.any { lower.contains(it) } -> GazerErrorCode.RTMP_CONNECT_FAILED
              encoderMarkers.any { lower.contains(it) } -> GazerErrorCode.ENCODER_FAILED
              else -> GazerErrorCode.UNKNOWN
          }
      }
  }
  ```

- [ ] **Step 4: Run — expected PASS.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.ErrorMapperTest'"`

- [ ] **Step 5: Write the failing StatsSampler test.**
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/StatsSamplerTest.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import io.mockk.every
  import io.mockk.mockk
  import io.waddlebot.gazer.pigeon.StatsSample
  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.Test

  private class FakeTicker : Ticker {
      var scheduledTask: (() -> Unit)? = null
      var cancelled = false

      override fun schedule(periodMs: Long, task: () -> Unit): TickerHandle {
          scheduledTask = task
          return object : TickerHandle {
              override fun cancel() {
                  cancelled = true
              }
          }
      }

      fun fireTick() = scheduledTask?.invoke()
  }

  class StatsSamplerTest {

      @Test
      fun `computes fps from the sentVideoFrames delta between ticks`() {
          val engine = mockk<StreamEngine>(relaxed = true)
          every { engine.sentVideoFrames() } returnsMany listOf(30L, 60L)
          every { engine.droppedVideoFrames() } returns 0L
          every { engine.hasCongestion(20f) } returns false
          val ticker = FakeTicker()
          val samples = mutableListOf<StatsSample>()
          val sampler = StatsSampler(engine = { engine }, ticker = ticker, intervalMs = 1000) { samples.add(it) }

          sampler.start()
          ticker.fireTick()
          ticker.fireTick()

          assertEquals(2, samples.size)
          assertEquals(30.0, samples[0].fps)
          assertEquals(30.0, samples[1].fps)
      }

      @Test
      fun `reports dropped frames from the engine`() {
          val engine = mockk<StreamEngine>(relaxed = true)
          every { engine.sentVideoFrames() } returns 0L
          every { engine.droppedVideoFrames() } returns 7L
          every { engine.hasCongestion(20f) } returns false
          val ticker = FakeTicker()
          val samples = mutableListOf<StatsSample>()
          val sampler = StatsSampler(engine = { engine }, ticker = ticker) { samples.add(it) }

          sampler.start()
          ticker.fireTick()

          assertEquals(7L, samples.single().droppedVideoFrames)
      }

      @Test
      fun `bitrateKbps reflects the latest onBitrate value in kbps`() {
          val engine = mockk<StreamEngine>(relaxed = true)
          every { engine.sentVideoFrames() } returns 0L
          every { engine.droppedVideoFrames() } returns 0L
          every { engine.hasCongestion(20f) } returns false
          val ticker = FakeTicker()
          val samples = mutableListOf<StatsSample>()
          val sampler = StatsSampler(engine = { engine }, ticker = ticker) { samples.add(it) }
          sampler.start()

          sampler.onBitrate(2_048_000L)
          ticker.fireTick()

          assertEquals(2048L, samples.single().bitrateKbps)
      }

      @Test
      fun `congestionPercent is 100 when the engine reports congestion else 0`() {
          val engine = mockk<StreamEngine>(relaxed = true)
          every { engine.sentVideoFrames() } returns 0L
          every { engine.droppedVideoFrames() } returns 0L
          every { engine.hasCongestion(20f) } returns true
          val ticker = FakeTicker()
          val samples = mutableListOf<StatsSample>()
          val sampler = StatsSampler(engine = { engine }, ticker = ticker) { samples.add(it) }
          sampler.start()

          ticker.fireTick()

          assertEquals(100.0, samples.single().congestionPercent)
      }

      @Test
      fun `stop cancels the ticker`() {
          val ticker = FakeTicker()
          val sampler = StatsSampler(engine = { null }, ticker = ticker) { }
          sampler.start()

          sampler.stop()

          assertEquals(true, ticker.cancelled)
      }

      @Test
      fun `tick is a no-op when the engine is not yet available`() {
          val ticker = FakeTicker()
          val samples = mutableListOf<StatsSample>()
          val sampler = StatsSampler(engine = { null }, ticker = ticker) { samples.add(it) }
          sampler.start()

          ticker.fireTick()

          assertEquals(0, samples.size)
      }
  }
  ```

- [ ] **Step 6: Run — expected FAIL.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.StatsSamplerTest'"`
  Expected: compile error — `unresolved reference: Ticker`, `unresolved reference: StatsSampler`.

- [ ] **Step 7: Implement StatsSampler.kt.**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StatsSampler.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import io.waddlebot.gazer.pigeon.StatsSample
  import java.util.concurrent.Executors
  import java.util.concurrent.ScheduledExecutorService
  import java.util.concurrent.ScheduledFuture
  import java.util.concurrent.TimeUnit

  /**
   * Schedules periodic StreamEngine polling. Ticking is indirected behind Ticker so
   * StatsSamplerTest/GazerPipelineTest can fire samples deterministically instead of racing a
   * real 1Hz timer.
   */
  interface Ticker {
      /** Schedules [task] to run every [periodMs] ms; returns a handle to cancel it. */
      fun schedule(periodMs: Long, task: () -> Unit): TickerHandle
  }

  /** Cancels a scheduled [Ticker] task. */
  interface TickerHandle {
      fun cancel()
  }

  /** Production Ticker backed by a single-thread ScheduledExecutorService. */
  class ScheduledExecutorTicker(
      private val executor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor(),
  ) : Ticker {
      override fun schedule(periodMs: Long, task: () -> Unit): TickerHandle {
          val future: ScheduledFuture<*> = executor.scheduleAtFixedRate(task, periodMs, periodMs, TimeUnit.MILLISECONDS)
          return object : TickerHandle {
              override fun cancel() {
                  future.cancel(false)
              }
          }
      }
  }

  /**
   * Polls a StreamEngine at [intervalMs] and emits StatsSample values via [onSample]: bitrate
   * from the most recent ConnectChecker.onNewBitrate value (fed through onBitrate), fps from the
   * delta of sentVideoFrames() between ticks, dropped frames and cumulative sent bytes from the
   * engine's counters, and congestion as 0/100 from StreamEngine.hasCongestion(20f).
   */
  class StatsSampler(
      private val engine: () -> StreamEngine?,
      private val ticker: Ticker = ScheduledExecutorTicker(),
      private val intervalMs: Long = 1000,
      private val onSample: (StatsSample) -> Unit,
  ) {
      private companion object {
          const val CONGESTION_THRESHOLD_PERCENT = 20f
      }

      private var handle: TickerHandle? = null
      private var lastBitrateBps: Long = 0
      private var lastSentVideoFrames: Long = 0
      private var sentBytesAccumulator: Long = 0

      /** Feeds the latest ConnectChecker.onNewBitrate(bitrate) value in bits per second. */
      fun onBitrate(bps: Long) {
          lastBitrateBps = bps
      }

      /** Starts periodic sampling; call once per streaming session. */
      fun start() {
          stop()
          lastSentVideoFrames = 0
          sentBytesAccumulator = 0
          handle = ticker.schedule(intervalMs) { tick() }
      }

      /** Stops periodic sampling; safe to call repeatedly. */
      fun stop() {
          handle?.cancel()
          handle = null
      }

      /** Computes and emits one StatsSample from the current engine state; exposed so tests can call ticks manually. */
      fun tick() {
          val current = engine() ?: return
          val sentVideoFrames = current.sentVideoFrames()
          val deltaFrames = (sentVideoFrames - lastSentVideoFrames).coerceAtLeast(0)
          lastSentVideoFrames = sentVideoFrames
          val fps = deltaFrames * 1000.0 / intervalMs
          val droppedVideoFrames = current.droppedVideoFrames()
          val bitrateKbps = lastBitrateBps / 1000
          sentBytesAccumulator += (lastBitrateBps / 8.0 * (intervalMs / 1000.0)).toLong()
          val congestionPercent = if (current.hasCongestion(CONGESTION_THRESHOLD_PERCENT)) 100.0 else 0.0
          onSample(
              StatsSample(
                  bitrateKbps = bitrateKbps,
                  fps = fps,
                  droppedVideoFrames = droppedVideoFrames,
                  sentBytes = sentBytesAccumulator,
                  congestionPercent = congestionPercent,
              ),
          )
      }
  }
  ```

- [ ] **Step 8: Run — expected PASS.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.StatsSamplerTest'"`
  Expected: `6 tests completed, 0 failed`.

- [ ] **Step 9: Write the failing GazerPipeline test (implementation pulls in PipelineListener.kt too).**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/PipelineListener.kt` (write
  now, since the test file below imports it and it has no independent test of its own — it is a
  pure interface exercised entirely through `GazerPipelineTest`):
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import io.waddlebot.gazer.pigeon.GazerErrorCode
  import io.waddlebot.gazer.pigeon.NativePipelineState
  import io.waddlebot.gazer.pigeon.StatsSample

  /**
   * Sink for GazerPipeline's native-side facts - state transitions, stats samples, and RTMP auth
   * results - so GazerPipeline never depends on Handler/Pigeon directly. PigeonHostApiImpl
   * (Task 20) implements this to post events to Dart on the main thread.
   */
  interface PipelineListener {
      fun onState(state: NativePipelineState, error: GazerErrorCode? = null, detail: String? = null)
      fun onStats(sample: StatsSample)
      fun onAuthResult(ok: Boolean)
  }
  ```
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/GazerPipelineTest.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import com.pedro.encoder.input.sources.audio.AudioSource
  import com.pedro.encoder.input.sources.video.VideoSource
  import io.mockk.every
  import io.mockk.mockk
  import io.mockk.verify
  import io.waddlebot.gazer.pigeon.GazerErrorCode
  import io.waddlebot.gazer.pigeon.NativePipelineState
  import io.waddlebot.gazer.pigeon.OutputOrientation
  import io.waddlebot.gazer.pigeon.StreamConfig
  import io.waddlebot.gazer.pigeon.StreamTarget
  import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
  import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory
  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.Assertions.assertFalse
  import org.junit.jupiter.api.Assertions.assertTrue
  import org.junit.jupiter.api.BeforeEach
  import org.junit.jupiter.api.Test

  class GazerPipelineTest {

      private lateinit var engine: StreamEngine
      private lateinit var videoSources: VideoSourceFactory
      private lateinit var audioSources: AudioSourceFactory
      private lateinit var listener: PipelineListener
      private lateinit var statsSampler: StatsSampler
      private lateinit var pipeline: GazerPipeline

      private val validConfig = StreamConfig(
          videoDeviceId = "camera:back",
          audioDeviceId = "audio:mic",
          width = 1280L,
          height = 720L,
          fps = 30L,
          videoBitrateKbps = 2000L,
          adaptiveBitrate = false,
          audioBitrateKbps = 128L,
          orientation = OutputOrientation.LANDSCAPE,
      )

      @BeforeEach
      fun setUp() {
          engine = mockk(relaxed = true)
          every { engine.prepareVideo(any(), any(), any(), any(), any()) } returns true
          every { engine.prepareAudio(any(), any(), any()) } returns true
          every { engine.hasCongestion(20f) } returns false
          videoSources = mockk(relaxed = true)
          every { videoSources.create(any()) } returns mockk<VideoSource>(relaxed = true)
          audioSources = mockk(relaxed = true)
          every { audioSources.create(any()) } returns mockk<AudioSource>(relaxed = true)
          listener = mockk(relaxed = true)
          statsSampler = mockk(relaxed = true)
          pipeline = GazerPipeline(
              engineFactory = { _, _, _ -> engine },
              videoSources = videoSources,
              audioSources = audioSources,
              listener = listener,
              statsSampler = statsSampler,
          )
      }

      @Test
      fun `happy path from prepare through start to streaming`() {
          val result = pipeline.prepare(validConfig)
          assertTrue(result.ok)
          assertEquals(NativePipelineState.READY, pipeline.state)

          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
          assertEquals(NativePipelineState.CONNECTING, pipeline.state)

          pipeline.onConnectionSuccess()
          assertEquals(NativePipelineState.STREAMING, pipeline.state)
          verify { listener.onState(NativePipelineState.STREAMING) }
      }

      @Test
      fun `connect failed maps the reason to a GazerErrorCode and reports it`() {
          pipeline.prepare(validConfig)
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

          pipeline.onConnectionFailed("Connection timeout")

          assertEquals(NativePipelineState.ERROR, pipeline.state)
          verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_CONNECT_FAILED, "Connection timeout") }
      }

      @Test
      fun `disconnect while streaming reports rtmpDisconnected`() {
          pipeline.prepare(validConfig)
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
          pipeline.onConnectionSuccess()

          pipeline.onDisconnect()

          assertEquals(NativePipelineState.ERROR, pipeline.state)
          verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_DISCONNECTED, any()) }
      }

      @Test
      fun `disconnect while connecting goes back to idle`() {
          pipeline.prepare(validConfig)
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

          pipeline.onDisconnect()

          assertEquals(NativePipelineState.IDLE, pipeline.state)
          verify { listener.onState(NativePipelineState.IDLE) }
      }

      @Test
      fun `auth error reports rtmpAuthFailed and onAuthResult false`() {
          pipeline.prepare(validConfig)
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

          pipeline.onAuthError()

          verify { listener.onAuthResult(false) }
          verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_AUTH_FAILED, any()) }
      }

      @Test
      fun `auth success reports onAuthResult true`() {
          pipeline.prepare(validConfig)
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

          pipeline.onAuthSuccess()

          verify { listener.onAuthResult(true) }
      }

      @Test
      fun `setReTries(0) is always called after a successful prepare`() {
          pipeline.prepare(validConfig)

          verify { engine.setReTries(0) }
      }

      @Test
      fun `adaptive bitrate on invokes setVideoBitrateOnFly via BitrateAdapter on new bitrate`() {
          pipeline.prepare(validConfig.copy(adaptiveBitrate = true))
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
          pipeline.onConnectionSuccess()

          pipeline.onNewBitrate(1_500_000L)

          verify { engine.setVideoBitrateOnFly(any()) }
      }

      @Test
      fun `adaptive bitrate off never calls setVideoBitrateOnFly from onNewBitrate`() {
          pipeline.prepare(validConfig.copy(adaptiveBitrate = false))
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
          pipeline.onConnectionSuccess()

          pipeline.onNewBitrate(1_500_000L)

          verify(exactly = 0) { engine.setVideoBitrateOnFly(any()) }
      }

      @Test
      fun `prepare with an invalid config returns a failed PrepareResult`() {
          val result = pipeline.prepare(validConfig.copy(width = 0L))

          assertFalse(result.ok)
          assertEquals(GazerErrorCode.ENCODER_FAILED, result.error)
      }

      @Test
      fun `start from the wrong state reports onState error unknown`() {
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

          verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.UNKNOWN, any()) }
      }

      @Test
      fun `stop from any state returns to idle via stopping`() {
          pipeline.prepare(validConfig)
          pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
          pipeline.onConnectionSuccess()

          pipeline.stop()

          assertEquals(NativePipelineState.IDLE, pipeline.state)
          verify { listener.onState(NativePipelineState.STOPPING) }
          verify { listener.onState(NativePipelineState.IDLE) }
          verify { engine.stopStream() }
          verify { engine.release() }
      }

      @Test
      fun `onConnectionStarted reports connecting`() {
          pipeline.prepare(validConfig)

          pipeline.onConnectionStarted("rtmp://example.com/live/key")

          assertEquals(NativePipelineState.CONNECTING, pipeline.state)
      }

      @Test
      fun `setVideoBitrate clamps to the 500 to 5000 kbps range`() {
          pipeline.prepare(validConfig)

          pipeline.setVideoBitrate(100)
          verify { engine.setVideoBitrateOnFly(500_000) }

          pipeline.setVideoBitrate(9000)
          verify { engine.setVideoBitrateOnFly(5_000_000) }
      }
  }
  ```

- [ ] **Step 10: Run — expected FAIL.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.GazerPipelineTest'"`
  Expected: compile error — `unresolved reference: GazerPipeline`.

- [ ] **Step 11: Implement GazerPipeline.kt.**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/GazerPipeline.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import com.pedro.common.ConnectChecker
  import com.pedro.encoder.input.sources.audio.AudioSource
  import com.pedro.encoder.input.sources.video.VideoSource
  import com.pedro.library.util.BitrateAdapter
  import io.waddlebot.gazer.pigeon.GazerErrorCode
  import io.waddlebot.gazer.pigeon.NativePipelineState
  import io.waddlebot.gazer.pigeon.OutputOrientation
  import io.waddlebot.gazer.pigeon.PrepareResult
  import io.waddlebot.gazer.pigeon.StreamConfig
  import io.waddlebot.gazer.pigeon.StreamTarget
  import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
  import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory

  /**
   * Owns the native streaming state machine: builds sources and a StreamEngine from a
   * StreamConfig, drives RootEncoder's ConnectChecker callbacks into Pigeon
   * NativePipelineState/GazerErrorCode events, and wires BitrateAdapter only when the config asks
   * for adaptive bitrate. Every decision beyond "is this config well-formed" belongs to Dart
   * (ReconnectPolicy, source selection) - this class only reports facts and executes commands.
   */
  class GazerPipeline(
      private val engineFactory: (ConnectChecker, VideoSource, AudioSource) -> StreamEngine,
      private val videoSources: VideoSourceFactory,
      private val audioSources: AudioSourceFactory,
      private val listener: PipelineListener,
      private val statsSampler: StatsSampler,
  ) : ConnectChecker {

      private companion object {
          const val CONGESTION_THRESHOLD_PERCENT = 20f
          const val MIN_BITRATE_KBPS = 500
          const val MAX_BITRATE_KBPS = 5000
          const val AUDIO_SAMPLE_RATE = 48000
      }

      var state: NativePipelineState = NativePipelineState.IDLE
          private set

      private var engine: StreamEngine? = null
      private var bitrateAdapter: BitrateAdapter? = null
      private var adaptiveBitrate = false

      /**
       * Validates [config], builds the video/audio sources and a fresh StreamEngine, and
       * prepares both the video and audio pipelines. Returns a failed PrepareResult (never
       * throws) if the config is out of range or RootEncoder rejects it.
       */
      fun prepare(config: StreamConfig): PrepareResult {
          val validationError = validate(config)
          if (validationError != null) {
              transitionToError(GazerErrorCode.ENCODER_FAILED, validationError)
              return PrepareResult(ok = false, error = GazerErrorCode.ENCODER_FAILED, detail = validationError)
          }

          state = NativePipelineState.PREPARING
          listener.onState(NativePipelineState.PREPARING)

          val videoSource = videoSources.create(config.videoDeviceId)
          val audioSource = audioSources.create(config.audioDeviceId)
          val newEngine = engineFactory(this, videoSource, audioSource)

          val rotation = if (config.orientation == OutputOrientation.PORTRAIT) 90 else 0
          val videoOk = runCatching {
              newEngine.prepareVideo(
                  width = config.width.toInt(),
                  height = config.height.toInt(),
                  bitrateBps = (config.videoBitrateKbps * 1000).toInt(),
                  fps = config.fps.toInt(),
                  rotation = rotation,
              )
          }.getOrElse { false }
          if (!videoOk) {
              newEngine.release()
              val detail = "prepareVideo failed for ${config.width}x${config.height}@${config.fps}"
              transitionToError(GazerErrorCode.ENCODER_FAILED, detail)
              return PrepareResult(ok = false, error = GazerErrorCode.ENCODER_FAILED, detail = detail)
          }

          val audioOk = runCatching {
              newEngine.prepareAudio(
                  sampleRate = AUDIO_SAMPLE_RATE,
                  stereo = true,
                  bitrateBps = (config.audioBitrateKbps * 1000).toInt(),
              )
          }.getOrElse { false }
          if (!audioOk) {
              newEngine.release()
              val detail = "prepareAudio failed for ${config.audioBitrateKbps}kbps"
              transitionToError(GazerErrorCode.AUDIO_SOURCE_FAILED, detail)
              return PrepareResult(ok = false, error = GazerErrorCode.AUDIO_SOURCE_FAILED, detail = detail)
          }

          newEngine.setReTries(0)
          adaptiveBitrate = config.adaptiveBitrate
          bitrateAdapter = if (config.adaptiveBitrate) {
              BitrateAdapter { adapted -> newEngine.setVideoBitrateOnFly(adapted) }
          } else {
              null
          }
          engine = newEngine
          state = NativePipelineState.READY
          listener.onState(NativePipelineState.READY)
          return PrepareResult(
              ok = true,
              negotiatedWidth = config.width,
              negotiatedHeight = config.height,
              negotiatedFps = config.fps,
              negotiatedFormat = "H264/AAC",
          )
      }

      /** Starts streaming to [target]; only valid from state=READY, otherwise reports GazerErrorCode.UNKNOWN. */
      fun start(target: StreamTarget) {
          val currentEngine = engine
          if (state != NativePipelineState.READY || currentEngine == null) {
              transitionToError(GazerErrorCode.UNKNOWN, "start() called from state=$state")
              return
          }
          currentEngine.setAuthorization(target.username, target.password)
          state = NativePipelineState.CONNECTING
          listener.onState(NativePipelineState.CONNECTING)
          statsSampler.start()
          currentEngine.startStream(target.url)
      }

      /** Stops streaming from any state, releasing the engine and returning to idle. */
      fun stop() {
          state = NativePipelineState.STOPPING
          listener.onState(NativePipelineState.STOPPING)
          statsSampler.stop()
          val currentEngine = engine
          if (currentEngine != null) {
              runCatching { currentEngine.stopStream() }
              runCatching { currentEngine.release() }
          }
          engine = null
          bitrateAdapter = null
          state = NativePipelineState.IDLE
          listener.onState(NativePipelineState.IDLE)
      }

      /** Sets the live video bitrate, clamped to the supported 500..5000 kbps range. */
      fun setVideoBitrate(kbps: Int) {
          val clamped = kbps.coerceIn(MIN_BITRATE_KBPS, MAX_BITRATE_KBPS)
          engine?.setVideoBitrateOnFly(clamped * 1000)
      }

      private fun validate(config: StreamConfig): String? {
          if (config.width <= 0 || config.height <= 0) return "width/height must be positive"
          if (config.width % 2 != 0L || config.height % 2 != 0L) return "width/height must be divisible by 2"
          if (config.fps !in 1L..120L) return "fps out of range: ${config.fps}"
          if (config.videoBitrateKbps <= 0) return "videoBitrateKbps must be positive"
          if (config.audioBitrateKbps <= 0) return "audioBitrateKbps must be positive"
          return null
      }

      private fun transitionToError(error: GazerErrorCode, detail: String?) {
          state = NativePipelineState.ERROR
          listener.onState(NativePipelineState.ERROR, error, detail)
      }

      // ConnectChecker (RootEncoder callbacks) - see ErrorMapper for reason-string classification.

      override fun onConnectionStarted(url: String) {
          state = NativePipelineState.CONNECTING
          listener.onState(NativePipelineState.CONNECTING)
      }

      override fun onConnectionSuccess() {
          state = NativePipelineState.STREAMING
          listener.onState(NativePipelineState.STREAMING)
      }

      override fun onConnectionFailed(reason: String) {
          statsSampler.stop()
          transitionToError(ErrorMapper.fromReason(reason), reason)
      }

      override fun onDisconnect() {
          statsSampler.stop()
          if (state == NativePipelineState.STREAMING) {
              transitionToError(GazerErrorCode.RTMP_DISCONNECTED, "RootEncoder onDisconnect while streaming")
          } else {
              state = NativePipelineState.IDLE
              listener.onState(NativePipelineState.IDLE)
          }
      }

      override fun onAuthError() {
          listener.onAuthResult(false)
          transitionToError(GazerErrorCode.RTMP_AUTH_FAILED, "RootEncoder onAuthError")
      }

      override fun onAuthSuccess() {
          listener.onAuthResult(true)
      }

      override fun onNewBitrate(bitrate: Long) {
          statsSampler.onBitrate(bitrate)
          if (adaptiveBitrate) {
              val currentEngine = engine ?: return
              bitrateAdapter?.adaptBitrate(bitrate, currentEngine.hasCongestion(CONGESTION_THRESHOLD_PERCENT))
          }
      }
  }
  ```

- [ ] **Step 12: Run — expected PASS.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.pipeline.GazerPipelineTest'"`
  Expected: `15 tests completed, 0 failed`.

- [ ] **Step 13: Full module test + coverage gate.**
  `make mobile-test-android`
  Expected: `BUILD SUCCESSFUL`, JaCoCo coverage ≥90% (excluding `RootEncoderEngine.class` per Task
  18's documented exclusion).

- [ ] **Step 14: Lint.**
  `make mobile-lint`

- [ ] **Step 15: Commit.**
  ```bash
  git add mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/ErrorMapper.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StatsSampler.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/PipelineListener.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/GazerPipeline.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/ErrorMapperTest.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/StatsSamplerTest.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/pipeline/GazerPipelineTest.kt
  git commit -m "$(cat <<'EOF'
  feat(gazer): add ErrorMapper, StatsSampler, and the GazerPipeline state machine

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 20: StreamService, PigeonHostApiImpl, MainActivity

**Files:**
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamService.kt`
- Create: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/PigeonHostApiImpl.kt`
- Modify: `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/MainActivity.kt`
- Create, Test: `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/PigeonHostApiImplTest.kt`
- Create, Test: `mobile/gazer/android/app/src/androidTest/kotlin/io/waddlebot/gazer/StreamServiceTest.kt`
- Verify only: `mobile/gazer/android/gradle/libs.versions.toml`, `mobile/gazer/android/app/build.gradle.kts` (androidTest aliases/deps and `testInstrumentationRunner` are already added by Task 2 — this task does not modify either file)

**Interfaces:**
- Consumes: `GazerHostApi`, `GazerFlutterApi`, and the Pigeon data/enum types (Task 6);
  `GazerPipeline`, `PipelineListener`, `StatsSampler`, `Ticker` (Task 19); `RootEncoderEngine`,
  `VideoSourceFactory`, `AudioSourceFactory`, `CameraManagerIds` (Task 18).
- Produces (verbatim per skeleton, adjusted for the Pigeon 28.0.0 suspend-based codegen verified
  below): `class StreamService : Service()` with
  `companion object { fun start(context: Context); fun stop(context: Context); const val ACTION_STOP = "io.waddlebot.gazer.action.STOP" }`
  and a binder exposing `val pipeline: GazerPipeline`;
  `class PigeonHostApiImpl(context: Context, flutterApi: GazerFlutterApi, videoDevices: () -> List<VideoDevice>, audioDevices: () -> List<AudioDevice>, mainScope: CoroutineScope = CoroutineScope(Dispatchers.Main.immediate)) : GazerHostApi, PipelineListener`
  — the contract's `mainHandler: Handler` parameter is replaced by an injectable `mainScope:
  CoroutineScope` (see the Pigeon codegen verification above the Task 17 heading): Pigeon 28
  generates `GazerFlutterApi`'s methods as `suspend fun`, so relaying a `PipelineListener` callback
  to Dart now means launching a coroutine on the main dispatcher, not posting a `Runnable` to a
  `Handler`; `GazerHostApi`'s `@async` methods (`requestUsbPermission`/`prepare`/`start`/`stop`) are
  implemented here as plain `suspend fun` overrides with no callback parameter — Pigeon's generated
  `setUp` already wraps every call in its own `CoroutineScope(Dispatchers.Main).launch { }` with
  try/catch-to-reply, so this class never manages that scope itself, only the outbound
  `PipelineListener → GazerFlutterApi` direction needs `mainScope`;
  `interface PipelineHost { fun pipeline(): GazerPipeline }`;
  `MainActivity : FlutterActivity` wiring `GazerHostApi.setUp(flutterEngine.dartExecutor.binaryMessenger, impl)`
  and `GazerFlutterApi(messenger)`. `VideoSourceFactory.create()` (Task 18) resolves `"camera:back"`
  as a bare `Camera2Source(context)` and `"camera:front"` via `switchCamera()` (never
  `openCameraId`, which is a documented RootEncoder 2.8.1 no-op before `start()` — see Task 18's
  verification note and its `create()` KDoc).

- [ ] **Step 1: Verify the androidTest dependency aliases and wiring already added by Task 2 (JUnit4, not JUnit5 - AndroidJUnitRunner is JUnit4-based).**
  Task 2 already defines every alias this task needs — `androidxTestRunner` (1.7.0), `androidxTestRules`
  (1.7.0), `androidxTestExtJunit` (1.3.0), `junit4` (4.13.2), the matching `[libraries]` entries, and
  already wires `testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"` plus
  `androidTestImplementation(libs.androidx.test.runner/.rules/.ext.junit/.junit4)` into
  `android/app/build.gradle.kts`. This task does **not** redeclare any of that (a second
  `[versions]`/`[libraries]` block for the same alias names would be a duplicate-key TOML error) —
  it only verifies Task 2's output is present before relying on it:
  ```bash
  make mobile-run CMD="grep -q 'androidx-test-runner' android/gradle/libs.versions.toml \
    && grep -q 'junit4 = ' android/gradle/libs.versions.toml \
    && grep -q 'testInstrumentationRunner' android/app/build.gradle.kts \
    && echo ANDROIDTEST_ALIASES_OK"
  ```
  Expected: `ANDROIDTEST_ALIASES_OK`. If missing, stop — Task 2 is incomplete; fix it there, never
  by hand-rolling a second declaration in this task.

- [ ] **Step 2: Write the failing PigeonHostApiImpl test.**
  `mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/PigeonHostApiImplTest.kt`:
  ```kotlin
  package io.waddlebot.gazer

  import io.mockk.coVerify
  import io.mockk.every
  import io.mockk.mockk
  import io.mockk.verify
  import io.waddlebot.gazer.pigeon.AudioDevice
  import io.waddlebot.gazer.pigeon.AudioDeviceKind
  import io.waddlebot.gazer.pigeon.GazerFlutterApi
  import io.waddlebot.gazer.pigeon.NativePipelineState
  import io.waddlebot.gazer.pigeon.OutputOrientation
  import io.waddlebot.gazer.pigeon.PrepareResult
  import io.waddlebot.gazer.pigeon.StatsSample
  import io.waddlebot.gazer.pigeon.StreamConfig
  import io.waddlebot.gazer.pigeon.StreamTarget
  import io.waddlebot.gazer.pigeon.VideoDevice
  import io.waddlebot.gazer.pigeon.VideoDeviceKind
  import io.waddlebot.gazer.pipeline.GazerPipeline
  import io.waddlebot.gazer.pipeline.PipelineHost
  import kotlinx.coroutines.CoroutineScope
  import kotlinx.coroutines.Dispatchers
  import kotlinx.coroutines.runBlocking
  import org.junit.jupiter.api.Assertions.assertEquals
  import org.junit.jupiter.api.BeforeEach
  import org.junit.jupiter.api.Test

  /**
   * GazerHostApi's `@async` methods (`requestUsbPermission`/`prepare`/`start`/`stop`) are Pigeon
   * 28's default `suspend fun` shape (no callback parameter) - see the Pigeon codegen
   * verification note above Task 17. JUnit5 test methods can't be `suspend fun` themselves, so
   * each one wraps its body in `runBlocking { }` (from kotlinx-coroutines-core, already a Task 2
   * dependency). `mainScope` is injected as `Dispatchers.Unconfined` rather than the production
   * default `Dispatchers.Main.immediate`: this plain JVM unit test has no Robolectric/Android
   * Looper, so `Dispatchers.Main` is never installed here - Unconfined runs `launch { }` bodies
   * eagerly on the calling thread, so a `coVerify` immediately after calling
   * `impl.onStats()`/`impl.onAuthResult()` already sees the flutterApi call applied.
   */
  class PigeonHostApiImplTest {

      private lateinit var pipeline: GazerPipeline
      private lateinit var flutterApi: GazerFlutterApi
      private lateinit var impl: PigeonHostApiImpl

      private val videoDevice = VideoDevice(id = "camera:back", kind = VideoDeviceKind.BACK_CAMERA, name = "Back camera")
      private val audioDevice = AudioDevice(id = "audio:mic", kind = AudioDeviceKind.MIC, name = "Phone microphone")

      @BeforeEach
      fun setUp() {
          pipeline = mockk(relaxed = true)
          flutterApi = mockk(relaxed = true)
          impl = PigeonHostApiImpl(
              context = mockk(relaxed = true),
              flutterApi = flutterApi,
              videoDevices = { listOf(videoDevice) },
              audioDevices = { listOf(audioDevice) },
              mainScope = CoroutineScope(Dispatchers.Unconfined),
          )
          impl.host = object : PipelineHost {
              override fun pipeline(): GazerPipeline = pipeline
          }
      }

      @Test
      fun `listVideoDevices returns the injected device list`() {
          assertEquals(listOf(videoDevice), impl.listVideoDevices())
      }

      @Test
      fun `listAudioDevices returns the injected device list`() {
          assertEquals(listOf(audioDevice), impl.listAudioDevices())
      }

      @Test
      fun `requestUsbPermission always resolves false in M1`() = runBlocking {
          assertEquals(false, impl.requestUsbPermission("camera:external"))
      }

      @Test
      fun `prepare delegates to the bound pipeline and returns its result`() = runBlocking {
          val config = StreamConfig(
              videoDeviceId = "camera:back",
              audioDeviceId = "audio:mic",
              width = 1280L,
              height = 720L,
              fps = 30L,
              videoBitrateKbps = 2000L,
              adaptiveBitrate = true,
              audioBitrateKbps = 128L,
              orientation = OutputOrientation.LANDSCAPE,
          )
          every { pipeline.prepare(config) } returns PrepareResult(ok = true)

          val result = impl.prepare(config)

          assertEquals(true, result.ok)
          verify { pipeline.prepare(config) }
      }

      @Test
      fun `start delegates to the bound pipeline`() = runBlocking {
          val target = StreamTarget(url = "rtmp://example.com/live/key")

          impl.start(target)

          verify { pipeline.start(target) }
      }

      @Test
      fun `stop delegates to the bound pipeline`() = runBlocking {
          impl.stop()

          verify { pipeline.stop() }
      }

      @Test
      fun `setVideoBitrate delegates to the bound pipeline`() {
          impl.setVideoBitrate(3000L)

          verify { pipeline.setVideoBitrate(3000) }
      }

      @Test
      fun `getState returns idle when no service is bound`() {
          impl.host = null

          assertEquals(NativePipelineState.IDLE, impl.getState())
      }

      @Test
      fun `getState delegates to the bound pipeline`() {
          every { pipeline.state } returns NativePipelineState.STREAMING

          assertEquals(NativePipelineState.STREAMING, impl.getState())
      }

      @Test
      fun `onStats calls the Flutter API on the main scope`() {
          val sample = StatsSample(bitrateKbps = 2000L, fps = 30.0, droppedVideoFrames = 0L, sentBytes = 0L, congestionPercent = 0.0)

          impl.onStats(sample)

          coVerify { flutterApi.onStats(sample) }
      }

      @Test
      fun `onAuthResult calls the Flutter API on the main scope`() {
          impl.onAuthResult(true)

          coVerify { flutterApi.onAuthResult(true) }
      }
  }
  ```

- [ ] **Step 3: Run — expected FAIL.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.PigeonHostApiImplTest'"`
  Expected: compile error — `unresolved reference: PigeonHostApiImpl`, `unresolved reference: PipelineHost`.

- [ ] **Step 4: Implement StreamService.kt (defines PipelineHost is used by PigeonHostApiImpl, not StreamService — declared alongside it below).**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamService.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  import android.app.Notification
  import android.app.NotificationChannel
  import android.app.NotificationManager
  import android.app.PendingIntent
  import android.app.Service
  import android.content.BroadcastReceiver
  import android.content.Context
  import android.content.Intent
  import android.content.IntentFilter
  import android.content.pm.ServiceInfo
  import android.hardware.camera2.CameraManager
  import android.os.Binder
  import android.os.Build
  import android.os.IBinder
  import android.os.PowerManager
  import androidx.core.app.NotificationCompat
  import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
  import io.waddlebot.gazer.pipeline.sources.CameraManagerIds
  import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory
  import java.util.concurrent.TimeUnit

  /**
   * Fans PipelineListener calls out to every attached listener, so PigeonHostApiImpl can attach
   * itself after binding without ever replacing StreamService's own wake-lock-controlling
   * listener - GazerPipeline's `listener` constructor field (fixed at construction, per the
   * SHARED CONTRACT) never changes.
   */
  class RelayPipelineListener : PipelineListener {
      private val listeners = mutableListOf<PipelineListener>()

      fun attach(listener: PipelineListener) {
          listeners.add(listener)
      }

      fun detach(listener: PipelineListener) {
          listeners.remove(listener)
      }

      override fun onState(state: NativePipelineState, error: GazerErrorCode?, detail: String?) {
          listeners.forEach { it.onState(state, error, detail) }
      }

      override fun onStats(sample: StatsSample) {
          listeners.forEach { it.onStats(sample) }
      }

      override fun onAuthResult(ok: Boolean) {
          listeners.forEach { it.onAuthResult(ok) }
      }
  }

  /**
   * Foreground service hosting the live GazerPipeline. Owns the persistent "gazer.stream"
   * notification (with a Stop action broadcasting ACTION_STOP), a partial wake lock held only
   * while streaming, and stops the pipeline in onDestroy so a killed/removed app never leaves
   * RootEncoder running against a camera or socket.
   */
  class StreamService : Service() {

      companion object {
          private const val NOTIFICATION_CHANNEL_ID = "gazer.stream"
          private const val NOTIFICATION_ID = 1001
          const val ACTION_STOP = "io.waddlebot.gazer.action.STOP"
          private const val WAKE_LOCK_TAG = "gazer:stream-service"

          /** Starts the service in the foreground; safe to call repeatedly. */
          fun start(context: Context) {
              context.startForegroundService(Intent(context, StreamService::class.java))
          }

          /** Stops the service; safe to call when not running. */
          fun stop(context: Context) {
              context.stopService(Intent(context, StreamService::class.java))
          }
      }

      /** Binder exposing the live pipeline and a way to attach the bound client as a listener. */
      inner class LocalBinder : Binder() {
          val pipeline: GazerPipeline get() = this@StreamService.pipeline

          fun setListener(listener: PipelineListener) {
              listenerRelay.attach(listener)
          }
      }

      private val binder = LocalBinder()
      private val listenerRelay = RelayPipelineListener()
      private var wakeLock: PowerManager.WakeLock? = null

      private val pipeline: GazerPipeline by lazy { buildPipeline() }

      private val stopReceiver = object : BroadcastReceiver() {
          override fun onReceive(context: Context, intent: Intent) {
              if (intent.action == ACTION_STOP) {
                  pipeline.stop()
              }
          }
      }

      override fun onCreate() {
          super.onCreate()
          createNotificationChannel()
          val filter = IntentFilter(ACTION_STOP)
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
              registerReceiver(stopReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
          } else {
              @Suppress("UnspecifiedRegisterReceiverFlag")
              registerReceiver(stopReceiver, filter)
          }
          listenerRelay.attach(
              object : PipelineListener {
                  override fun onState(state: NativePipelineState, error: GazerErrorCode?, detail: String?) {
                      when (state) {
                          NativePipelineState.STREAMING -> acquireWakeLock()
                          NativePipelineState.IDLE -> releaseWakeLock()
                          else -> Unit
                      }
                  }

                  override fun onStats(sample: StatsSample) = Unit

                  override fun onAuthResult(ok: Boolean) = Unit
              },
          )
      }

      override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
          val notification = buildNotification()
          val serviceType = ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
              startForeground(NOTIFICATION_ID, notification, serviceType)
          } else {
              startForeground(NOTIFICATION_ID, notification)
          }
          return START_NOT_STICKY
      }

      override fun onBind(intent: Intent?): IBinder = binder

      override fun onDestroy() {
          pipeline.stop()
          releaseWakeLock()
          runCatching { unregisterReceiver(stopReceiver) }
          super.onDestroy()
      }

      private fun buildPipeline(): GazerPipeline {
          var activeEngine: StreamEngine? = null
          val statsSampler = StatsSampler(engine = { activeEngine }) { sample -> listenerRelay.onStats(sample) }
          val cameraManager = applicationContext.getSystemService(Context.CAMERA_SERVICE) as CameraManager
          return GazerPipeline(
              engineFactory = { checker, video, audio ->
                  RootEncoderEngine(applicationContext, checker, video, audio).also { activeEngine = it }
              },
              videoSources = VideoSourceFactory(applicationContext, CameraManagerIds(cameraManager)),
              audioSources = AudioSourceFactory(),
              listener = listenerRelay,
              statsSampler = statsSampler,
          )
      }

      private fun createNotificationChannel() {
          val manager = getSystemService(NotificationManager::class.java)
          val channel = NotificationChannel(NOTIFICATION_CHANNEL_ID, "Gazer streaming", NotificationManager.IMPORTANCE_LOW)
          manager.createNotificationChannel(channel)
      }

      private fun buildNotification(): Notification {
          val stopIntent = PendingIntent.getBroadcast(
              this,
              0,
              Intent(ACTION_STOP),
              PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
          )
          return NotificationCompat.Builder(this, NOTIFICATION_CHANNEL_ID)
              .setContentTitle("Gazer is live")
              .setSmallIcon(android.R.drawable.presence_video_online)
              .setOngoing(true)
              .addAction(0, "Stop", stopIntent)
              .build()
      }

      private fun acquireWakeLock() {
          if (wakeLock?.isHeld == true) return
          val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
          wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKE_LOCK_TAG).apply {
              setReferenceCounted(false)
              acquire(TimeUnit.HOURS.toMillis(4))
          }
      }

      private fun releaseWakeLock() {
          wakeLock?.let { if (it.isHeld) it.release() }
          wakeLock = null
      }
  }
  ```

- [ ] **Step 5: Implement PigeonHostApiImpl.kt.**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/PigeonHostApiImpl.kt`:
  ```kotlin
  package io.waddlebot.gazer

  import android.content.ComponentName
  import android.content.Context
  import android.content.Intent
  import android.content.ServiceConnection
  import android.os.IBinder
  import io.waddlebot.gazer.pigeon.AudioDevice
  import io.waddlebot.gazer.pigeon.GazerErrorCode
  import io.waddlebot.gazer.pigeon.GazerFlutterApi
  import io.waddlebot.gazer.pigeon.GazerHostApi
  import io.waddlebot.gazer.pigeon.NativePipelineState
  import io.waddlebot.gazer.pigeon.PrepareResult
  import io.waddlebot.gazer.pigeon.StateEvent
  import io.waddlebot.gazer.pigeon.StatsSample
  import io.waddlebot.gazer.pigeon.StreamConfig
  import io.waddlebot.gazer.pigeon.StreamTarget
  import io.waddlebot.gazer.pigeon.VideoDevice
  import io.waddlebot.gazer.pipeline.GazerPipeline
  import io.waddlebot.gazer.pipeline.PipelineHost
  import io.waddlebot.gazer.pipeline.PipelineListener
  import io.waddlebot.gazer.pipeline.StreamService
  import kotlinx.coroutines.CompletableDeferred
  import kotlinx.coroutines.CoroutineScope
  import kotlinx.coroutines.Dispatchers
  import kotlinx.coroutines.launch

  /**
   * Implements the Pigeon GazerHostApi: binds/starts StreamService on prepare(), forwards every
   * command to the bound GazerPipeline, and relays PipelineListener facts back to Dart via
   * GazerFlutterApi. Pigeon 28 generates `@async` GazerHostApi methods as plain `suspend fun` (no
   * callback parameter) - the generated `setUp` wrapper already runs each call in its own
   * `CoroutineScope(Dispatchers.Main).launch { }` and replies with the result or a caught
   * exception, so this class never manages that scope itself. GazerFlutterApi is generated the
   * same way (its methods are `suspend fun` too), which is why every `PipelineListener` callback
   * below runs inside [mainScope] instead of a `Handler.post { }` callback.
   */
  class PigeonHostApiImpl(
      private val context: Context,
      private val flutterApi: GazerFlutterApi,
      private val videoDevices: () -> List<VideoDevice>,
      private val audioDevices: () -> List<AudioDevice>,
      private val mainScope: CoroutineScope = CoroutineScope(Dispatchers.Main.immediate),
  ) : GazerHostApi, PipelineListener {

      /** Test/composition seam - `internal` so PigeonHostApiImplTest can inject a fake without a real ServiceConnection. */
      internal var host: PipelineHost? = null
      private var hostDeferred: CompletableDeferred<PipelineHost>? = null

      private val connection = object : ServiceConnection {
          override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
              val serviceBinder = binder as? StreamService.LocalBinder ?: return
              serviceBinder.setListener(this@PigeonHostApiImpl)
              val boundHost = object : PipelineHost {
                  override fun pipeline(): GazerPipeline = serviceBinder.pipeline
              }
              host = boundHost
              hostDeferred?.complete(boundHost)
              hostDeferred = null
          }

          override fun onServiceDisconnected(name: ComponentName?) {
              host = null
          }
      }

      override fun listVideoDevices(): List<VideoDevice> = videoDevices()

      override fun listAudioDevices(): List<AudioDevice> = audioDevices()

      override suspend fun requestUsbPermission(deviceId: String): Boolean {
          // M1 lists no USB devices; always deny so Dart's UI never offers a USB source.
          return false
      }

      override suspend fun prepare(config: StreamConfig): PrepareResult {
          val currentHost = host ?: awaitBoundHost()
          if (currentHost == null) {
              postState(NativePipelineState.ERROR, GazerErrorCode.SERVICE_START_DENIED, "bindService failed")
              return PrepareResult(ok = false, error = GazerErrorCode.SERVICE_START_DENIED, detail = "bindService failed")
          }
          return currentHost.pipeline().prepare(config)
      }

      override suspend fun start(target: StreamTarget) {
          host?.pipeline()?.start(target)
      }

      override suspend fun stop() {
          host?.pipeline()?.stop()
      }

      override fun setVideoBitrate(kbps: Long) {
          host?.pipeline()?.setVideoBitrate(kbps.toInt())
      }

      override fun getState(): NativePipelineState = host?.pipeline()?.state ?: NativePipelineState.IDLE

      /** Binds StreamService and suspends until its ServiceConnection connects; null if bindService() itself refuses to even start binding. */
      private suspend fun awaitBoundHost(): PipelineHost? {
          val deferred = CompletableDeferred<PipelineHost>()
          hostDeferred = deferred
          val bound = bindService()
          if (!bound) {
              hostDeferred = null
              return null
          }
          return deferred.await()
      }

      private fun bindService(): Boolean {
          StreamService.start(context)
          return context.bindService(Intent(context, StreamService::class.java), connection, Context.BIND_AUTO_CREATE)
      }

      // PipelineListener - each call launches on mainScope, since GazerFlutterApi's methods are
      // suspend functions (Pigeon 28 default for @FlutterApi) that must run on the main thread,
      // the same thread platform channel messages are always sent from.

      override fun onState(state: NativePipelineState, error: GazerErrorCode?, detail: String?) {
          postState(state, error, detail)
      }

      override fun onStats(sample: StatsSample) {
          mainScope.launch { flutterApi.onStats(sample) }
      }

      override fun onAuthResult(ok: Boolean) {
          mainScope.launch { flutterApi.onAuthResult(ok) }
      }

      private fun postState(state: NativePipelineState, error: GazerErrorCode?, detail: String?) {
          mainScope.launch { flutterApi.onStateChanged(StateEvent(state = state, error = error, detail = detail)) }
      }
  }
  ```
  Add the `PipelineHost` seam alongside `StreamService` in the same `pipeline` package:
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/PipelineHost.kt`:
  ```kotlin
  package io.waddlebot.gazer.pipeline

  /** Thin seam over StreamService's binder so PigeonHostApiImplTest can fake the bound connection. */
  interface PipelineHost {
      fun pipeline(): GazerPipeline
  }
  ```

- [ ] **Step 6: Run — expected PASS.**
  `make mobile-run CMD="./gradlew :app:testDebugUnitTest --tests 'io.waddlebot.gazer.PigeonHostApiImplTest'"`
  Expected: `11 tests completed, 0 failed`.

- [ ] **Step 7: Wire MainActivity.**
  `mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/MainActivity.kt`:
  ```kotlin
  package io.waddlebot.gazer

  import android.content.Context
  import android.hardware.camera2.CameraManager
  import io.flutter.embedding.android.FlutterActivity
  import io.flutter.embedding.engine.FlutterEngine
  import io.waddlebot.gazer.pigeon.GazerFlutterApi
  import io.waddlebot.gazer.pigeon.GazerHostApi
  import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
  import io.waddlebot.gazer.pipeline.sources.CameraManagerIds
  import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory

  /**
   * Sole platform-channel wiring point: registers PigeonHostApiImpl as the GazerHostApi and hands
   * it a GazerFlutterApi for native->Dart events. Runtime permission requests (CAMERA,
   * RECORD_AUDIO, POST_NOTIFICATIONS) are handled entirely in Dart via permission_handler before
   * Go Live is ever called - this activity never requests permissions itself. PigeonHostApiImpl's
   * `mainScope` is left at its default (`CoroutineScope(Dispatchers.Main.immediate)`) here - a
   * real running app always has `kotlinx-coroutines-android`'s Main dispatcher installed, unlike
   * the plain-JVM PigeonHostApiImplTest, which injects an explicit test scope instead.
   */
  class MainActivity : FlutterActivity() {

      override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
          super.configureFlutterEngine(flutterEngine)
          val messenger = flutterEngine.dartExecutor.binaryMessenger
          val flutterApi = GazerFlutterApi(messenger)
          val cameraManager = applicationContext.getSystemService(Context.CAMERA_SERVICE) as CameraManager
          val impl = PigeonHostApiImpl(
              context = applicationContext,
              flutterApi = flutterApi,
              videoDevices = { VideoSourceFactory(applicationContext, CameraManagerIds(cameraManager)).list() },
              audioDevices = { AudioSourceFactory().list() },
          )
          GazerHostApi.setUp(messenger, impl)
      }
  }
  ```

- [ ] **Step 8: Write the instrumented StreamServiceTest (androidTest, JUnit4).**
  `mobile/gazer/android/app/src/androidTest/kotlin/io/waddlebot/gazer/StreamServiceTest.kt`:
  ```kotlin
  package io.waddlebot.gazer

  import android.app.NotificationManager
  import android.content.Context
  import android.content.Intent
  import androidx.test.core.app.ApplicationProvider
  import androidx.test.ext.junit.runners.AndroidJUnit4
  import androidx.test.rule.ServiceTestRule
  import io.waddlebot.gazer.pipeline.StreamService
  import org.junit.Assert.assertTrue
  import org.junit.Rule
  import org.junit.Test
  import org.junit.runner.RunWith

  /**
   * Instrumented lifecycle test: StreamService must post its foreground notification on start and
   * remove it cleanly on stop. Cannot run on the JVM unit-test target since it needs a real
   * NotificationManager and Android service lifecycle - this is also RootEncoderEngine's only
   * coverage, since it can't run outside a real Camera2/MediaCodec-capable device or emulator.
   */
  @RunWith(AndroidJUnit4::class)
  class StreamServiceTest {

      @get:Rule
      val serviceRule = ServiceTestRule()

      private val context: Context = ApplicationProvider.getApplicationContext()
      private val notificationManager: NotificationManager =
          context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

      @Test
      fun startPostsTheForegroundNotificationAndStopRemovesIt() {
          serviceRule.startService(Intent(context, StreamService::class.java))

          val hasNotification = pollUntil(timeoutMs = 5000) {
              notificationManager.activeNotifications.any { it.packageName == context.packageName }
          }
          assertTrue("expected an active notification after start", hasNotification)

          context.stopService(Intent(context, StreamService::class.java))

          val notificationGone = pollUntil(timeoutMs = 5000) {
              notificationManager.activeNotifications.none { it.packageName == context.packageName }
          }
          assertTrue("expected the notification to be removed after stop", notificationGone)
      }

      private fun pollUntil(timeoutMs: Long, intervalMs: Long = 100, condition: () -> Boolean): Boolean {
          val deadline = System.currentTimeMillis() + timeoutMs
          while (System.currentTimeMillis() < deadline) {
              if (condition()) return true
              Thread.sleep(intervalMs)
          }
          return condition()
      }
  }
  ```
  This androidTest is **not** run by Task 20 itself — it requires an emulator/device, which this
  toolchain container does not provide. It compiles here (Step 9) and runs for real in CI's
  emulator job (writer E's Task 21); locally it runs via
  `make mobile-run CMD="./gradlew connectedDebugAndroidTest"` with an emulator attached
  (`adb devices` shows one) or a physical device over USB debugging.

- [ ] **Step 9: Compile the androidTest source set (no emulator required for this check).**
  `make mobile-run CMD="./gradlew :app:compileDebugAndroidTestKotlin"`
  Expected: `BUILD SUCCESSFUL` — proves `StreamServiceTest.kt` compiles against the new
  `androidx.test`/JUnit4 dependencies without needing a connected device.

- [ ] **Step 10: Full module unit-test + coverage gate.**
  `make mobile-test-android`
  Expected: `BUILD SUCCESSFUL`, JaCoCo coverage ≥90% across all of Tasks 17–20's production Kotlin
  (excluding the documented `RootEncoderEngine.class` exclusion).

- [ ] **Step 11: Build the debug APK and verify the manifest survived, without adb.**
  `make mobile-run CMD="flutter build apk --debug"`
  Then, still inside the container, decode the built APK's manifest directly (no device/`adb`
  needed):
  `make mobile-run CMD="\$ANDROID_HOME/build-tools/36.0.0/aapt2 dump xmltree build/app/outputs/flutter-apk/app-debug.apk --file AndroidManifest.xml | grep -A3 'StreamService'"`
  Expected output includes `StreamService` and `foregroundServiceType` with the camera/microphone
  flags — confirms Task 17's manifest and Task 20's service registration both made it into the
  final build artifact.

- [ ] **Step 12: Lint.**
  `make mobile-lint`

- [ ] **Step 13: Commit.**
  ```bash
  git add mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/StreamService.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/pipeline/PipelineHost.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/PigeonHostApiImpl.kt \
          mobile/gazer/android/app/src/main/kotlin/io/waddlebot/gazer/MainActivity.kt \
          mobile/gazer/android/app/src/test/kotlin/io/waddlebot/gazer/PigeonHostApiImplTest.kt \
          mobile/gazer/android/app/src/androidTest/kotlin/io/waddlebot/gazer/StreamServiceTest.kt
  git commit -m "$(cat <<'EOF'
  feat(gazer): wire StreamService, PigeonHostApiImpl, and MainActivity to the Pigeon channel

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```


# Part E — Tasks 21–22 (Writer E: Integration & Release)

Assumes Tasks 1–20 landed exactly per the skeleton contract: toolchain image + make targets, CI workflow through the `security` job, the full Dart app (HomeScreen/SettingsScreen/StatusPanel/providers/PipelineController), the Kotlin bridge (GazerPipeline/StreamService/PigeonHostApiImpl), and `StreamServiceTest` (androidTest). The emulator has no RTMP server — the integration flow below asserts failure handling (Connecting → Reconnecting), never a live stream.

Package name: `gazer` (from `flutter create --project-name gazer`) — all Dart imports use `package:gazer/...`.

Action pin looked up for this part: **reactivecircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d** (tag `v2.38.0`, resolved `git ls-remote`-style via `gh api repos/ReactiveCircus/android-emulator-runner/releases/latest` → tag → `gh api .../git/refs/tags/v2.38.0` → annotated tag object → `gh api .../git/tags/<tag-sha>` → underlying commit `a421e43855164a8197daf9d8d40fe71c6996bb0d`, checked 2026-09-07).

---

### Task 21: Integration test and CI emulator job

**Files:**
- Create: `mobile/gazer/lib/config/debug_overrides.dart`
- Create: `mobile/gazer/scripts/decode_screenshots.py`
- Create: `mobile/gazer/scripts/run_integration_test.sh`
- Create: `mobile/gazer/integration_test/go_live_unreachable_test.dart`
- Test: `mobile/gazer/test/config/debug_overrides_test.dart`
- Test: `mobile/gazer/test/providers/license_provider_debug_override_test.dart`
- Modify: `mobile/gazer/lib/providers/license_provider.dart` (apply `DebugOverrides` inside `license()`)
- Modify: `mobile/gazer/pubspec.yaml` (ensure `integration_test: sdk: flutter` dev dependency)
- Modify: `mobile/gazer/Dockerfile` (add emulator + system-image sdkmanager packages, verify `python3`)
- Modify: `Makefile` (repo root) — add `mobile-test-integration`
- Modify: `.github/workflows/gazer-mobile.yml` — add `integration` job

**Interfaces:**
- Consumes: `PipelineController`/`pipelineControllerProvider`, `pipelineStateProvider` (`@riverpod Stream<PipelineState> pipelineState(Ref ref)`), `PipelineState`/`ConnectingState`/`ReconnectingState`/`IdleState`, `GazerApp`, `AppLocalizations`, `settingsNotifierProvider` (`Future<GazerSettings> build()`), `licenseClientProvider`, `LicenseState`/`LicenseStatus`. Also consumes, read-only (Tasks 13–16 already ship these — see Step 8 below): widget `Key('settingsGearButton')`/`Key('goLiveButton')`/`Key('stopButton')` (`home_screen.dart`), `Key('backCameraOption')` (`source_picker.dart`), `Key('statusChip')` (`status_chip.dart`), `Key('targetUrlField')`/`Key('streamKeyField')`/`Key('saveSettingsButton')` (`settings_screen.dart`), and l10n getters `l10n.sourceBackCameraLabel`, `l10n.statusChipIdleLabel`, `l10n.statusChipConnectingLabel`, `l10n.statusChipReconnectingLabel`, `l10n.settingsSavedMessage` (`app_en.arb`, Task 13).
- Produces: `class DebugOverrides { static const String flagsOverride; static bool get enabled; static Set<String> get flags; }`; modified `Future<LicenseState> license(Ref ref)` that force-enables `DebugOverrides.flags` when `DebugOverrides.enabled`; `make mobile-test-integration`; CI job `integration`.

- [ ] **Step 1: Verify `integration_test` SDK dependency is declared.**
  Run:
  ```
  grep -n "integration_test:" mobile/gazer/pubspec.yaml
  ```
  Expected: either it's already present under `dev_dependencies` (Task 2 scaffold) — nothing to do — or it prints nothing, in which case add under `dev_dependencies:`:
  ```yaml
  dev_dependencies:
    integration_test:
      sdk: flutter
  ```
  Run `make mobile-run CMD="flutter pub get"` — expected: `Got dependencies!` with no version-solve error. Commit only if the file changed:
  ```
  git add mobile/gazer/pubspec.yaml mobile/gazer/pubspec.lock
  git commit -m "$(cat <<'EOF'
  chore(gazer): declare integration_test SDK dev dependency

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 2: Failing test for `DebugOverrides`.**
  Create `mobile/gazer/test/config/debug_overrides_test.dart`:
  ```dart
  import 'package:flutter/foundation.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/config/debug_overrides.dart';

  /// Covers DebugOverrides across however this file was invoked:
  /// `make mobile-test` runs it with no define (flagsOverride == ''), and
  /// Step 4 below runs it a second time with
  /// `--dart-define=GAZER_FLAGS_OVERRIDE=camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture`
  /// to exercise the non-empty parsing path. kDebugMode is always true
  /// under `flutter test`, so `enabled` can only be proven to require BOTH
  /// conditions by pairing this file's assertions with the release-build
  /// code-review guard documented in Step 6 — it cannot be proven by a
  /// single `flutter test` invocation alone.
  void main() {
    test('kDebugMode is true under flutter test (sanity: proves the harness limitation, not a DebugOverrides property)', () {
      expect(kDebugMode, isTrue);
    });

    test('enabled is exactly flagsOverride.isNotEmpty given kDebugMode is always true here', () {
      expect(DebugOverrides.enabled, equals(DebugOverrides.flagsOverride.isNotEmpty));
    });

    test('flags parses the currently-configured define into a trimmed, non-empty-only set', () {
      final Set<String> expected = DebugOverrides.flagsOverride
          .split(',')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toSet();
      expect(DebugOverrides.flags, equals(expected));
    });

    test('default invocation (no define) yields empty flags and enabled == false', () {
      if (DebugOverrides.flagsOverride.isEmpty) {
        expect(DebugOverrides.flags, isEmpty);
        expect(DebugOverrides.enabled, isFalse);
      }
    });

    test('the M1 integration define decodes to exactly the 4 flag keys used by CI', () {
      const String integrationDefine = 'camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture';
      if (DebugOverrides.flagsOverride == integrationDefine) {
        expect(
          DebugOverrides.flags,
          equals(<String>{'camera-stream', 'adaptive-bitrate', 'rtmp-auth', 'uvc-capture'}),
        );
        expect(DebugOverrides.enabled, isTrue);
      }
    });
  }
  ```
  Run `make mobile-run CMD="flutter test test/config/debug_overrides_test.dart"`.
  Expected: compile error — `Error: Couldn't resolve the package 'gazer' in 'package:gazer/config/debug_overrides.dart'` (file doesn't exist yet).

- [ ] **Step 3: Implement `DebugOverrides`, get Step 2 green.**
  Create `mobile/gazer/lib/config/debug_overrides.dart`:
  ```dart
  import 'package:flutter/foundation.dart';

  /// Debug-only feature-flag override sourced from a `--dart-define` at
  /// build/test time. Exists so integration tests and local development can
  /// force license flags ON without a live license-server round trip.
  /// Ignored entirely in release builds because [kDebugMode] is false there,
  /// regardless of what was passed as `GAZER_FLAGS_OVERRIDE` — see the
  /// release-build guard in `test/config/debug_overrides_test.dart` and the
  /// mandatory code-review check in this task's Step 6.
  class DebugOverrides {
    const DebugOverrides._();

    /// Raw comma-separated flag-key list from
    /// `--dart-define=GAZER_FLAGS_OVERRIDE=...`. Empty when not supplied.
    static const String flagsOverride = String.fromEnvironment('GAZER_FLAGS_OVERRIDE');

    /// True only when running a debug build AND a non-empty override was
    /// supplied. Both conditions are required — kDebugMode is false in
    /// release/profile builds regardless of the define, so this can never
    /// leak into a production build no matter what was passed at build time.
    static bool get enabled => kDebugMode && flagsOverride.isNotEmpty;

    /// Parsed flag keys from [flagsOverride]: comma-split, trimmed, empty
    /// entries dropped.
    static Set<String> get flags => flagsOverride
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toSet();
  }
  ```
  Run `make mobile-run CMD="flutter test test/config/debug_overrides_test.dart"`.
  Expected: `00:01 +5: All tests passed!`
  Commit:
  ```
  git add mobile/gazer/lib/config/debug_overrides.dart mobile/gazer/test/config/debug_overrides_test.dart
  git commit -m "$(cat <<'EOF'
  test(gazer): add DebugOverrides debug-only flag override

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 4: Run the same test file with the integration define, proving the parsing branch.**
  Run:
  ```
  make mobile-run CMD="flutter test test/config/debug_overrides_test.dart --dart-define=GAZER_FLAGS_OVERRIDE=camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture"
  ```
  Expected: `00:01 +5: All tests passed!` — this time the 4th test's `if` body is skipped (define isn't empty) and the 5th test's `if` body runs, asserting the exact 4-key set. No commit (verification only, no file changed).

- [ ] **Step 5: Failing test for the license-provider override wiring.**
  Create `mobile/gazer/test/providers/license_provider_debug_override_test.dart`:
  ```dart
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:mocktail/mocktail.dart';

  import 'package:gazer/config/debug_overrides.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/services/license_client.dart';

  class MockLicenseClient extends Mock implements LicenseClient {}

  void main() {
    test('license() force-enables DebugOverrides.flags, status valid, lastFetched set, only when enabled', () async {
      final MockLicenseClient client = MockLicenseClient();
      final LicenseState base = LicenseState(
        status: LicenseStatus.unknown,
        flags: const <String, bool>{},
        lastFetched: null,
        deviceId: 'test-device-0001',
      );
      when(() => client.validateAndFetchFlags()).thenAnswer((_) async => base);

      final ProviderContainer container = ProviderContainer(
        overrides: <Override>[licenseClientProvider.overrideWith((Ref ref) async => client)],
      );
      addTearDown(container.dispose);

      final LicenseState result = await container.read(licenseProvider.future);

      if (DebugOverrides.enabled) {
        expect(result.status, LicenseStatus.valid);
        expect(result.lastFetched, isNotNull);
        for (final String key in DebugOverrides.flags) {
          expect(result.flags[key], isTrue, reason: 'flag $key must be forced ON');
        }
      } else {
        expect(result.status, base.status);
        expect(result.flags, equals(base.flags));
        expect(result.lastFetched, base.lastFetched);
      }
    });
  }
  ```
  Run `make mobile-run CMD="flutter test test/providers/license_provider_debug_override_test.dart"`.
  Expected: passes trivially (no define → `else` branch, unmodified passthrough — Task 12's baseline `license()` already satisfies this). Now re-run with the integration define to prove the real gap:
  ```
  make mobile-run CMD="flutter test test/providers/license_provider_debug_override_test.dart --dart-define=GAZER_FLAGS_OVERRIDE=camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture"
  ```
  Expected: **FAIL** — `Expected: true, Actual: <null>` on the `result.flags[key]` check, since Task 12's `license()` never applies `DebugOverrides`.

- [ ] **Step 6: Wire `DebugOverrides` into `license()`, get Step 5 green under both invocations.**
  Modify `mobile/gazer/lib/providers/license_provider.dart` — add the import, then find Task 12's
  exact current `license` function (quoted verbatim below — note `licenseClientProvider` is a
  `FutureProvider<LicenseClient>`, read via `ref.watch(licenseClientProvider.future)`, not a plain
  `ref.watch(licenseClientProvider)`):
  ```dart
  @Riverpod(keepAlive: true)
  Future<LicenseState> license(Ref ref) async {
    final client = await ref.watch(licenseClientProvider.future);
    return client.validateAndFetchFlags();
  }
  ```
  and replace it with (leave `licenseClientProvider` and `featureFlags` untouched; add the
  `debug_overrides.dart` import alongside the existing ones):
  ```dart
  import 'package:gazer/config/debug_overrides.dart';
  // ...existing imports (license_client.dart, license_state.dart, riverpod_annotation) stay.

  @Riverpod(keepAlive: true)
  Future<LicenseState> license(Ref ref) async {
    final LicenseClient client = await ref.watch(licenseClientProvider.future);
    final LicenseState fetched = await client.validateAndFetchFlags();

    if (!DebugOverrides.enabled) {
      return fetched;
    }

    // Debug-only: force the M1 flags ON so integration tests and local dev
    // don't depend on a reachable license.penguintech.io. Never runs in a
    // release build — DebugOverrides.enabled requires kDebugMode.
    final Map<String, bool> overridden = <String, bool>{...fetched.flags};
    for (final String key in DebugOverrides.flags) {
      overridden[key] = true;
    }
    return fetched.copyWith(
      status: LicenseStatus.valid,
      flags: overridden,
      lastFetched: DateTime.now(),
    );
  }
  ```
  Run both invocations from Step 5 again.
  Expected: both `00:01 +1: All tests passed!`
  Commit:
  ```
  git add mobile/gazer/lib/providers/license_provider.dart mobile/gazer/test/providers/license_provider_debug_override_test.dart
  git commit -m "$(cat <<'EOF'
  test(gazer): apply DebugOverrides in the license provider

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 7: Verify the l10n keys the integration test needs already exist.**
  Tasks 13–16 already ship every string this test needs — under their own real key names, not
  the ones an isolated writer would have guessed. Verify rather than append:
  ```
  grep -c '"settingsSavedMessage"\|"statusChipConnectingLabel"\|"statusChipIdleLabel"\|"statusChipReconnectingLabel"\|"sourceBackCameraLabel"\|"goLiveButtonLabel"\|"stopButtonLabel"\|"saveButtonLabel"' mobile/gazer/lib/l10n/app_en.arb
  ```
  Expected: `8` (one match per key, all present from Task 13's `app_en.arb`). If any is missing,
  stop — that means Task 13 regressed; fix `app_en.arb` in place (do not invent a differently-named
  duplicate key here). No file changes, no commit — this step is a precondition check only.

- [ ] **Step 8: Verify the widget keys the integration test drives already exist.**
  Tasks 14–16 already attach every `Key(...)` this test taps/enters-text-into, on the real
  widgets (`Semantics`-wrapped `IconButton`/`FilledButton`, the `RadioListTile` in `SourcePicker`,
  the `Semantics` wrapping `StatusChip`'s `InkWell`, and the `TextFormField`/`FilledButton` in
  `SettingsScreen`) — adding a second, differently-shaped copy here would just create two
  definitions of the same widget tree. Verify rather than modify:
  ```
  grep -rc "Key('settingsGearButton')" mobile/gazer/lib/screens/home_screen.dart
  grep -rc "Key('goLiveButton')" mobile/gazer/lib/screens/home_screen.dart
  grep -rc "Key('stopButton')" mobile/gazer/lib/screens/home_screen.dart
  grep -c "Key('backCameraOption')" mobile/gazer/lib/widgets/source_picker.dart
  grep -c "Key('statusChip')" mobile/gazer/lib/widgets/status_chip.dart
  grep -c "Key('targetUrlField')" mobile/gazer/lib/screens/settings_screen.dart
  grep -c "Key('streamKeyField')" mobile/gazer/lib/screens/settings_screen.dart
  grep -c "Key('saveSettingsButton')" mobile/gazer/lib/screens/settings_screen.dart
  ```
  Expected: `home_screen.dart` reports `2` for each of `settingsGearButton`/`goLiveButton`/
  `stopButton` (Task 14's initial layout and Task 16's responsive layout each carry their own
  copy of the AppBar action and the Go Live/Stop buttons); every other grep reports `1`. If any
  is `0`, stop — that means Tasks 14–16 regressed; add the missing `key:` directly to the real
  widget there, never as a redundant rebuild here. No file changes, no commit — this step is a
  precondition check only. `StatusChip`'s tap already opens `showStatusPanel` via the `onTap`
  callback `HomeScreen` passes in (Task 14) — no additional wiring needed.

- [ ] **Step 9: Screenshot decoder — `scripts/decode_screenshots.py`.**
  Create `mobile/gazer/scripts/decode_screenshots.py`:
  ```python
  #!/usr/bin/env python3
  """Decode build/integration_response_data.json's embedded screenshots into
  individual PNG files under build/integration_screenshots/.

  `flutter test integration_test/<file>.dart -d <device>` writes this JSON
  when the test binding is IntegrationTestWidgetsFlutterBinding; each
  `binding.takeScreenshot(name)` call adds one entry under the top-level
  "screenshots" key, with "screenshotName" and a raw (non-base64) "bytes"
  array of PNG byte values. This script is additive: it never clears
  build/integration_screenshots/, so re-running it after a second test run
  (e.g. the tablet pass in Task 26) layers new files in without deleting
  the first run's output.
  """
  import json
  import pathlib
  import sys

  RESPONSE_PATH = pathlib.Path("build/integration_response_data.json")
  OUT_DIR = pathlib.Path("build/integration_screenshots")


  def main() -> int:
      if not RESPONSE_PATH.exists():
          print(f"ERROR: {RESPONSE_PATH} not found - did the integration test run?", file=sys.stderr)
          return 1

      data = json.loads(RESPONSE_PATH.read_text())
      screenshots = data.get("screenshots", [])
      if not screenshots:
          print("ERROR: zero screenshots found in integration_response_data.json", file=sys.stderr)
          return 1

      OUT_DIR.mkdir(parents=True, exist_ok=True)
      for entry in screenshots:
          name = entry["screenshotName"]
          out_path = OUT_DIR / f"{name}.png"
          out_path.write_bytes(bytes(entry["bytes"]))
          print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")

      print(f"decoded {len(screenshots)} screenshot(s)")
      return 0


  if __name__ == "__main__":
      raise SystemExit(main())
  ```
  Verify with a fabricated fixture (proves both the happy path and the zero-denominator failure):
  ```
  make mobile-run CMD="mkdir -p build && python3 -c \"import json,pathlib; pathlib.Path('build/integration_response_data.json').write_text(json.dumps({'screenshots':[{'screenshotName':'smoke','bytes':[137,80,78,71]}]}))\" && python3 scripts/decode_screenshots.py && test -f build/integration_screenshots/smoke.png && rm -rf build/integration_response_data.json build/integration_screenshots"
  ```
  Expected: `wrote build/integration_screenshots/smoke.png (4 bytes)` then `decoded 1 screenshot(s)`, exit 0.
  ```
  make mobile-run CMD="rm -f build/integration_response_data.json && python3 scripts/decode_screenshots.py; echo exit=$?"
  ```
  Expected: `ERROR: build/integration_response_data.json not found - did the integration test run?` and `exit=1`.
  Commit:
  ```
  git add mobile/gazer/scripts/decode_screenshots.py
  git commit -m "$(cat <<'EOF'
  ci(gazer): add integration_test screenshot decoder

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 10: Write the integration test itself.**
  Create `mobile/gazer/integration_test/go_live_unreachable_test.dart`:
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:integration_test/integration_test.dart';

  import 'package:gazer/app.dart';
  import 'package:gazer/l10n/app_localizations.dart';
  import 'package:gazer/models/pipeline_state.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/providers/settings_provider.dart';

  /// End-to-end "go live against an unreachable RTMP host" flow.
  ///
  /// The Android emulator has no RTMP server and no route to a real one, so
  /// this test cannot assert a live stream — it asserts the failure-handling
  /// path: enter a loopback target nothing listens on, tap Go Live, watch the
  /// pipeline reach ConnectingState then ReconnectingState(attempt: 1) within
  /// ReconnectPolicy's first backoff window, then confirm Stop returns to
  /// IdleState. Runs against the real app, the real Riverpod providers, and
  /// the real Pigeon bridge to the on-device Kotlin GazerPipeline/RootEncoder
  /// stack — nothing here is mocked.
  void main() {
    final IntegrationTestWidgetsFlutterBinding binding =
        IntegrationTestWidgetsFlutterBinding.ensureInitialized();

    testWidgets(
      'go live against an unreachable RTMP host reaches Reconnecting(1), Stop returns to Idle',
      (WidgetTester tester) async {
        await tester.pumpWidget(const ProviderScope(child: GazerApp()));
        await tester.pumpAndSettle(const Duration(seconds: 5));

        final Element appElement = tester.element(find.byType(GazerApp));
        final ProviderContainer container = ProviderScope.containerOf(appElement);
        final AppLocalizations l10n = AppLocalizations.of(appElement)!;

        // --- Settings: point at the emulator host loopback, nothing listens there ---
        await tester.tap(find.byKey(const Key('settingsGearButton')));
        await tester.pumpAndSettle();

        await tester.enterText(find.byKey(const Key('targetUrlField')), 'rtmp://10.0.2.2:1935/live');
        await tester.enterText(find.byKey(const Key('streamKeyField')), 'demo-key-0001');
        await tester.pumpAndSettle();

        await tester.tap(find.byKey(const Key('saveSettingsButton')));
        await tester.pumpAndSettle();
        expect(find.text(l10n.settingsSavedMessage), findsOneWidget);

        final saved = await container.read(settingsNotifierProvider.future);
        expect(saved.target.url, 'rtmp://10.0.2.2:1935/live');
        expect(saved.target.streamKey, 'demo-key-0001');

        // --- Home: back camera, Go Live ---
        await tester.pageBack();
        await tester.pumpAndSettle();

        await tester.tap(find.byKey(const Key('backCameraOption')));
        await tester.pumpAndSettle();
        expect(find.text(l10n.sourceBackCameraLabel), findsOneWidget);

        await tester.tap(find.byKey(const Key('goLiveButton')));
        await tester.pump(const Duration(milliseconds: 500));

        // --- Connecting ---
        final bool reachedConnecting = await _pumpUntil(
          tester,
          () => container.read(pipelineStateProvider).valueOrNull is ConnectingState,
          timeout: const Duration(seconds: 5),
        );
        expect(reachedConnecting, isTrue, reason: 'expected ConnectingState shortly after Go Live');
        expect(find.textContaining(l10n.statusChipConnectingLabel), findsOneWidget);

        // --- Reconnecting (attempt 1), within ReconnectPolicy's first backoff window ---
        final bool reachedReconnecting = await _pumpUntil(
          tester,
          () {
            final PipelineState? state = container.read(pipelineStateProvider).valueOrNull;
            return state is ReconnectingState && state.attempt == 1;
          },
          timeout: const Duration(seconds: 15),
        );
        expect(
          reachedReconnecting,
          isTrue,
          reason: 'expected ReconnectingState(attempt: 1) within 15s of a failed '
              'connection to an unreachable RTMP host',
        );
        expect(find.textContaining(l10n.statusChipReconnectingLabel), findsOneWidget);

        await binding.takeScreenshot('go-live-unreachable');

        // --- Stop cancels the reconnect loop and returns to Idle ---
        await tester.tap(find.byKey(const Key('stopButton')));
        final bool backToIdle = await _pumpUntil(
          tester,
          () => container.read(pipelineStateProvider).valueOrNull is IdleState,
          timeout: const Duration(seconds: 5),
        );
        expect(backToIdle, isTrue, reason: 'expected IdleState shortly after Stop');
        await tester.pumpAndSettle();
        expect(find.textContaining(l10n.statusChipIdleLabel), findsOneWidget);
      },
    );
  }

  /// Pumps in short increments until [predicate] is true or [timeout]
  /// elapses. `pumpAndSettle` alone cannot wait for the reconnect transition:
  /// ReconnectPolicy's countdown timer keeps the tree "unsettled" indefinitely,
  /// so a bounded polling pump is used instead.
  Future<bool> _pumpUntil(
    WidgetTester tester,
    bool Function() predicate, {
    required Duration timeout,
    Duration step = const Duration(milliseconds: 250),
  }) async {
    final Stopwatch sw = Stopwatch()..start();
    while (sw.elapsed < timeout) {
      await tester.pump(step);
      if (predicate()) return true;
    }
    return false;
  }
  ```
  This cannot run yet (no emulator/AVD in the container) — proceed to Steps 11–13 before attempting Step 14's run.

- [ ] **Step 11: Add emulator + system-image packages to the toolchain image.**
  Modify `mobile/gazer/Dockerfile` — find Task 1's `sdkmanager` invocation (installing `platforms;android-36`, `build-tools;36.0.0`, `ndk;28.2.13676358`) and append to the SAME invocation:
  ```dockerfile
  RUN sdkmanager --sdk_root="${ANDROID_SDK_ROOT}" \
        "platforms;android-36" \
        "build-tools;36.0.0" \
        "ndk;28.2.13676358" \
        "system-images;android-34;google_apis;x86_64" \
        "emulator" \
        "platform-tools"
  ```
  Also verify `python3` (needed by `scripts/decode_screenshots.py`) — Ubuntu 24.04's base image ships `python3` by default; confirm rather than assume:
  ```dockerfile
  RUN python3 --version
  ```
  If that `RUN` fails during build, add `python3-minimal` to the existing `apt-get install` layer instead.
  Rebuild: `make mobile-toolchain`.
  Expected: build succeeds; `docker run --rm gazer-toolchain:3.47.2 avdmanager list device | grep -i "pixel_6\|pixel_tablet"` prints both device profiles (bundled with the `emulator`/`platform-tools` packages).
  Commit:
  ```
  git add mobile/gazer/Dockerfile
  git commit -m "$(cat <<'EOF'
  ci(gazer): add Android emulator + system image to the toolchain image

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 12: Local emulator-run script.**
  Create `mobile/gazer/scripts/run_integration_test.sh`:
  ```bash
  #!/usr/bin/env bash
  # Runs inside the gazer-toolchain container (the `docker run` invocation
  # needs --device /dev/kvm and --network host). Boots a fresh phone AVD
  # (gazer_ci), pre-builds and installs a debug APK so CAMERA/RECORD_AUDIO
  # can be granted BEFORE the permission_handler dialog would otherwise block
  # the Go Live tap, runs the go-live-unreachable integration_test, decodes
  # its screenshot, then runs Task 20's instrumented StreamServiceTest
  # against the same emulator.
  #
  # Local equivalent of the CI grant step: to drive this by hand against an
  # already-running emulator/device instead, run
  #   adb shell pm grant io.waddlebot.gazer android.permission.CAMERA
  #   adb shell pm grant io.waddlebot.gazer android.permission.RECORD_AUDIO
  set -euo pipefail

  FLAGS_DEFINE="camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture"

  avdmanager --verbose create avd --force -n gazer_ci \
    -k "system-images;android-34;google_apis;x86_64" -d "pixel_6"

  emulator -avd gazer_ci -no-window -gpu swiftshader_indirect -no-audio \
    -no-boot-anim -no-snapshot -accel on \
    -camera-back emulated -camera-front emulated &
  EMULATOR_PID=$!

  adb wait-for-device

  timeout=180
  while [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; do
    timeout=$((timeout - 2))
    if [ "$timeout" -le 0 ]; then
      echo "ERROR: emulator boot timed out" >&2
      exit 1
    fi
    sleep 2
  done

  flutter build apk --debug --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE"
  adb install -r build/app/outputs/flutter-apk/app-debug.apk
  adb shell pm grant io.waddlebot.gazer android.permission.CAMERA
  adb shell pm grant io.waddlebot.gazer android.permission.RECORD_AUDIO

  flutter test integration_test/go_live_unreachable_test.dart -d emulator-5554 \
    --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE" \
    | tee /tmp/integration_test.log

  grep -qE '\+[1-9][0-9]*' /tmp/integration_test.log

  python3 scripts/decode_screenshots.py

  cd android
  ./gradlew connectedDebugAndroidTest | tee /tmp/gradle_connected.log
  grep -q "BUILD SUCCESSFUL" /tmp/gradle_connected.log
  cd ..

  adb emu kill || echo "emulator already exited"
  wait "$EMULATOR_PID" 2>/dev/null || echo "emulator process already reaped"

  echo "integration test + connectedDebugAndroidTest complete"
  ```
  `chmod +x mobile/gazer/scripts/run_integration_test.sh`.
  Commit:
  ```
  git add mobile/gazer/scripts/run_integration_test.sh
  git commit -m "$(cat <<'EOF'
  ci(gazer): add local container-emulator integration test runner

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 13: Wire `make mobile-test-integration`.**
  Modify `Makefile` (repo root) — add near the other `mobile-*` targets:
  ```makefile
  mobile-test-integration: ## Boot the container-hosted Android emulator (needs /dev/kvm) and run integration_test/ + connectedDebugAndroidTest
  	@test -e /dev/kvm || { echo "ERROR: /dev/kvm not present - integration tests require KVM. Check 'ls -l /dev/kvm' and that your user is in the kvm group; GitHub Actions ubuntu-latest runners enable it via udev rules (see the integration CI job)."; exit 1; }
  	docker run --rm \
  		--device /dev/kvm \
  		--network host \
  		--user $(shell id -u):$(shell id -g) \
  		-v $(PWD)/mobile/gazer:/work \
  		-v gazer-pub-cache:/home/appuser/.pub-cache \
  		-v gazer-gradle:/home/appuser/.gradle \
  		-w /work \
  		gazer-toolchain:3.47.2 \
  		bash scripts/run_integration_test.sh
  ```
  Commit:
  ```
  git add Makefile
  git commit -m "$(cat <<'EOF'
  ci(gazer): add mobile-test-integration make target

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 14: Run it — first real pass/fail.**
  Run `make mobile-test-integration`.
  Expected: emulator boots (~60–120s), `00:xx +1: All tests passed!` in `/tmp/integration_test.log`, `build/integration_screenshots/go-live-unreachable.png` exists and is non-empty, `BUILD SUCCESSFUL` from `connectedDebugAndroidTest`. If the emulator fails to reach `sys.boot_completed=1` within 180s, increase the timeout in `run_integration_test.sh` rather than masking the check.
  No commit — Step 10's test file and Step 12/13's runner are already committed; this step is verification.

- [ ] **Step 15: CI job `integration`.**
  Modify `.github/workflows/gazer-mobile.yml` — add after the `security` job:
  ```yaml
    integration:
      name: Integration test (emulator)
      runs-on: ubuntu-latest
      needs: [toolchain, test, android-unit]
      timeout-minutes: 45
      steps:
        - name: Checkout
          uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd

        - name: Enable KVM group perms
          run: |
            echo 'KERNEL=="kvm", GROUP="kvm", MODE="0666", OPTIONS+="static_node=kvm"' | sudo tee /etc/udev/rules.d/99-kvm4all.rules
            sudo udevadm control --reload-rules
            sudo udevadm trigger --name-match=kvm

        - name: Set up Java 17
          uses: actions/setup-java@be666c2fcd27ec809703dec50e508c2fdc7f6654
          with:
            distribution: temurin
            java-version: '17'

        - name: Cache Flutter SDK
          id: flutter-cache
          uses: actions/cache@27d5ce7f107fe9357f9df03efb73ab90386fccae
          with:
            path: ~/flutter-3.47.2
            key: flutter-3.47.2-linux-${{ runner.arch }}

        - name: Install Flutter 3.47.2 (pinned, sha256-verified)
          if: steps.flutter-cache.outputs.cache-hit != 'true'
          run: |
            set -euo pipefail
            curl -fsSL -o /tmp/flutter.tar.xz \
              https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_3.47.2-stable.tar.xz
            echo "447878859d01ca9bfdb99a85f245af07ed8a15fedcd9d189c4749e8e92d1f185  /tmp/flutter.tar.xz" | sha256sum -c -
            mkdir -p ~/flutter-3.47.2
            tar -xJf /tmp/flutter.tar.xz -C ~/flutter-3.47.2 --strip-components=1

        - name: Add Flutter to PATH
          run: echo "$HOME/flutter-3.47.2/bin" >> "$GITHUB_PATH"

        - name: flutter pub get
          working-directory: mobile/gazer
          run: flutter pub get

        - name: Install Android SDK components
          run: |
            set -euo pipefail
            yes | sdkmanager --licenses > /dev/null
            sdkmanager "platforms;android-36" "build-tools;36.0.0" "platform-tools"

        - name: Pre-build debug APK (installed inside the emulator step, after the AVD boots)
          working-directory: mobile/gazer
          run: flutter build apk --debug --dart-define=GAZER_FLAGS_OVERRIDE=camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture

        - name: Run integration_test + connectedDebugAndroidTest on emulator
          uses: reactivecircus/android-emulator-runner@a421e43855164a8197daf9d8d40fe71c6996bb0d # v2.38.0
          with:
            api-level: 34
            target: google_apis
            arch: x86_64
            profile: pixel_6
            emulator-options: -no-window -gpu swiftshader_indirect -no-audio -no-boot-anim -camera-back emulated -camera-front emulated -accel on
            disable-animations: true
            script: |
              set -euo pipefail
              adb install -r mobile/gazer/build/app/outputs/flutter-apk/app-debug.apk
              adb shell pm grant io.waddlebot.gazer android.permission.CAMERA
              adb shell pm grant io.waddlebot.gazer android.permission.RECORD_AUDIO
              cd mobile/gazer
              flutter test integration_test/go_live_unreachable_test.dart -d emulator-5554 \
                --dart-define=GAZER_FLAGS_OVERRIDE=camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture \
                2>&1 | tee /tmp/flutter_integration.log
              grep -qE '\+[1-9][0-9]*' /tmp/flutter_integration.log
              python3 scripts/decode_screenshots.py
              cd android
              ./gradlew connectedDebugAndroidTest 2>&1 | tee /tmp/gradle_connected.log
              grep -q "BUILD SUCCESSFUL" /tmp/gradle_connected.log

        - name: Upload integration screenshots
          if: always()
          uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
          with:
            name: gazer-integration-screenshots
            path: mobile/gazer/build/integration_screenshots/
            if-no-files-found: error

        - name: Upload androidTest reports
          if: always()
          uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
          with:
            name: gazer-android-connected-test-report
            path: mobile/gazer/android/app/build/reports/androidTests/connected/
            if-no-files-found: error

        - name: Clean up runner workspace artifacts
          if: always()
          run: |
            rm -rf mobile/gazer/build/integration_screenshots
            rm -rf mobile/gazer/android/app/build/reports/androidTests/connected
            rm -rf mobile/gazer/build/app/outputs/flutter-apk
  ```
  Note the gate: `grep -qE '\+[1-9][0-9]*' /tmp/flutter_integration.log` fails the step (and therefore the job, `set -euo pipefail`) if zero tests ran — satisfies "job fails if zero tests ran."
  Run `make mobile-lint` isn't applicable to YAML; instead run the workflow's own linter if the repo has one (`zizmor .github/workflows/gazer-mobile.yml` per Task 3's CI hardening step) and confirm 0 findings against the new job.
  Commit:
  ```
  git add .github/workflows/gazer-mobile.yml
  git commit -m "$(cat <<'EOF'
  ci(gazer): add integration emulator job to gazer-mobile.yml

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 15b: Make the `release` job wait for `integration`.**

A tagged release must not ship without the emulator gate. Task 3 wrote `needs: [build, test, android-unit, security]` on the `release` job; extend it. Run from the repo root:

```bash
grep -n 'needs: \[build, test, android-unit, security\]' .github/workflows/gazer-mobile.yml
sed -i 's/needs: \[build, test, android-unit, security\]/needs: [build, test, android-unit, security, integration]/' .github/workflows/gazer-mobile.yml
grep -n 'needs: \[build, test, android-unit, security, integration\]' .github/workflows/gazer-mobile.yml
```

Expected: the first grep prints exactly one line (the `release` job), the last grep prints that same line with `integration` appended. If the first grep prints zero lines, stop: Task 3's workflow text drifted and the anchor must be located by hand (`grep -n 'release:' -A 4 .github/workflows/gazer-mobile.yml`) before editing — never leave `release` without the integration dependency.

Then re-run the workflow linter inside the container and expect no findings:

```bash
make mobile-run CMD="uvx zizmor@1.30.0 .github/workflows/gazer-mobile.yml"
```

Commit:

```bash
git add .github/workflows/gazer-mobile.yml
git commit -m "ci(gazer): gate tagged releases on the emulator integration job

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE"
```

- [ ] **Step 16: Push and confirm CI green.**
  ```
  git push -u origin feature/gazer-mobile-v2
  gh run list --workflow gazer-mobile.yml --branch feature/gazer-mobile-v2 --limit 1
  ```
  Expected: the listed run's `integration` job shows `success`. If it fails, `gh run view <run-id> --log-failed` and fix before proceeding to Task 26 — never carry a red `integration` job forward.

---

# Part F — Tasks 22–24: Permission gate, license keepalive, sanitized logging

Fills three spec requirements the merged plan (Tasks 1–21, Part E) landed without: the
"Permissions" section's runtime CAMERA/RECORD_AUDIO/POST_NOTIFICATIONS gate (MainActivity's own
doc comment in Task 20 already promises this is "handled entirely in Dart via permission_handler
before Go Live is ever called" — this part is what makes that promise true), the "Licensing &
Feature Flags" section's "keepalive every 5 min while foregrounded" behaviour (`LicenseClient.keepalive()`
existed since Task 9 but nothing ever called it), and the "Statistics & Logging" section's
sanitized/debug-gated logging (nothing in Tasks 1–21 ever logs anything — `print` never appears,
which is correct, but so does `dart:developer`'s `log()`).

Runs after Task 21 (Part E) and before Task 26 (final M1 verification) — Task 26's `make
mobile-test`/`make mobile-lint` full-suite gates cover everything this part adds.

Package name: `gazer`, all Dart imports `package:gazer/...`, all file paths below relative to the
repo root (`mobile/gazer/...`) matching Part E's convention.

---

### Task 22: Runtime permission gate

**Files:**
- Create: `mobile/gazer/lib/services/permission_gate.dart`
- Test: `mobile/gazer/test/services/permission_gate_test.dart`
- Modify: `mobile/gazer/lib/providers/pipeline_provider.dart` (add `permissionGateProvider`)
- Modify: `mobile/gazer/lib/screens/home_screen.dart` (Go Live handler gates on permissions first)
- Modify: `mobile/gazer/test/helpers/fakes.dart` (add `FakePermissionGate`)
- Modify: `mobile/gazer/test/screens/home_screen_test.dart` (default-granted override + 3 new tests)
- Modify: `mobile/gazer/lib/l10n/app_en.arb` (4 new keys)

**Interfaces:**
- Consumes: `permission_handler` 13.0.2 (`Permission.camera`, `Permission.microphone`,
  `Permission.notification`, `PermissionStatus.isGranted`/`.isPermanentlyDenied`,
  `List<Permission>.request()`, `openAppSettings()`), `device_info_plus`'s `DeviceInfoPlugin`
  (already a dependency since Task 9's `AndroidDeviceIdProvider`) for `AndroidDeviceInfo.version.sdkInt`,
  `pipelineControllerProvider`/`featureFlagsProvider` (`lib/providers/pipeline_provider.dart` /
  `lib/providers/license_provider.dart`, both already imported by `home_screen.dart`),
  `AppLocalizations` (Task 13).
- Produces: `abstract class PermissionGate { Future<PermissionOutcome> ensureLivePermissions(); }`,
  `enum PermissionOutcome { granted, denied, permanentlyDenied }`,
  `class PermissionHandlerGate implements PermissionGate { PermissionHandlerGate({Future<int> Function() sdkInt}); }`,
  `permissionGateProvider` (`@Riverpod(keepAlive: true)`, `lib/providers/pipeline_provider.dart`),
  `FakePermissionGate` (`test/helpers/fakes.dart`), l10n keys `permissionDeniedMessage`,
  `permissionDeniedRetryLabel`, `permissionPermanentlyDeniedMessage`, `permissionOpenSettingsLabel`.

**Package verification (WebFetch, recorded here per the contract's instruction):** fetched
`https://pub.dev/documentation/permission_handler_platform_interface/latest/` — confirms
`PermissionHandlerPlatform` is the abstract platform-interface class every `permission_handler`
platform implementation extends (import `package:permission_handler_platform_interface/permission_handler_platform_interface.dart`,
latest documented version `4.4.1` at lookup time — same "don't hardcode, let `flutter pub get`
resolve it" caveat Task 7 already established for `shared_preferences_platform_interface`), with
methods `Future<Map<Permission, PermissionStatus>> requestPermissions(List<Permission> permissions)`,
`Future<PermissionStatus> checkPermissionStatus(Permission permission)`,
`Future<bool> openAppSettings()`, `Future<ServiceStatus> checkServiceStatus(Permission permission)`,
`Future<bool> shouldShowRequestPermissionRationale(Permission permission)`. Fetched
`https://pub.dev/documentation/plugin_platform_interface/latest/` — confirms
`MockPlatformInterfaceMixin` exists (import `package:plugin_platform_interface/plugin_platform_interface.dart`),
documented as existing "to disable the `extends` enforcement" so a `Mock`-based test double can
`implement` a `PlatformInterface` subclass without extending it. Together this confirms the test
pattern below: `class MockPermissionHandlerPlatform extends Mock with MockPlatformInterfaceMixin
implements PermissionHandlerPlatform {}`, then `PermissionHandlerPlatform.instance = mock` in
`setUp`, restored in `tearDown`. `permission_handler: 13.0.2` is already pinned (Task 2's
pubspec, verified via `grep -n "permission_handler" mobile/gazer/pubspec.yaml`) — no pubspec
change needed in this task.

- [ ] **Step 1: Write the failing test `test/services/permission_gate_test.dart`**

  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/services/permission_gate.dart';
  import 'package:mocktail/mocktail.dart';
  import 'package:permission_handler/permission_handler.dart';
  import 'package:permission_handler_platform_interface/permission_handler_platform_interface.dart';
  import 'package:plugin_platform_interface/plugin_platform_interface.dart';

  /// Mocktail double for the platform channel `permission_handler` talks to
  /// — `MockPlatformInterfaceMixin` disables `PlatformInterface`'s normal
  /// `extends`-only enforcement so `Mock` can `implement` it directly (see
  /// this task's package-verification note).
  class MockPermissionHandlerPlatform extends Mock
      with MockPlatformInterfaceMixin
      implements PermissionHandlerPlatform {}

  void main() {
    late MockPermissionHandlerPlatform platform;
    late PermissionHandlerPlatform originalPlatform;

    setUpAll(() {
      registerFallbackValue(<Permission>[]);
    });

    setUp(() {
      originalPlatform = PermissionHandlerPlatform.instance;
      platform = MockPermissionHandlerPlatform();
      PermissionHandlerPlatform.instance = platform;
    });

    tearDown(() {
      PermissionHandlerPlatform.instance = originalPlatform;
    });

    PermissionHandlerGate buildGate({required int sdkInt}) =>
        PermissionHandlerGate(sdkInt: () async => sdkInt);

    test('all granted -> PermissionOutcome.granted', () async {
      when(() => platform.requestPermissions(any())).thenAnswer(
        (_) async => <Permission, PermissionStatus>{
          Permission.camera: PermissionStatus.granted,
          Permission.microphone: PermissionStatus.granted,
        },
      );

      final result = await buildGate(sdkInt: 30).ensureLivePermissions();

      expect(result, PermissionOutcome.granted);
      final requested = verify(() => platform.requestPermissions(captureAny())).captured.single
          as List<Permission>;
      expect(requested, containsAll(<Permission>[Permission.camera, Permission.microphone]));
      expect(requested, isNot(contains(Permission.notification)));
    });

    test('any permanentlyDenied -> PermissionOutcome.permanentlyDenied', () async {
      when(() => platform.requestPermissions(any())).thenAnswer(
        (_) async => <Permission, PermissionStatus>{
          Permission.camera: PermissionStatus.permanentlyDenied,
          Permission.microphone: PermissionStatus.granted,
        },
      );

      final result = await buildGate(sdkInt: 33).ensureLivePermissions();

      expect(result, PermissionOutcome.permanentlyDenied);
    });

    test('a plain denial with nothing permanently denied -> PermissionOutcome.denied', () async {
      when(() => platform.requestPermissions(any())).thenAnswer(
        (_) async => <Permission, PermissionStatus>{
          Permission.camera: PermissionStatus.denied,
          Permission.microphone: PermissionStatus.granted,
        },
      );

      final result = await buildGate(sdkInt: 30).ensureLivePermissions();

      expect(result, PermissionOutcome.denied);
    });

    test('sdkInt >= 33 includes Permission.notification in the request', () async {
      when(() => platform.requestPermissions(any())).thenAnswer(
        (_) async => <Permission, PermissionStatus>{
          Permission.camera: PermissionStatus.granted,
          Permission.microphone: PermissionStatus.granted,
          Permission.notification: PermissionStatus.granted,
        },
      );

      await buildGate(sdkInt: 33).ensureLivePermissions();

      final requested = verify(() => platform.requestPermissions(captureAny())).captured.single
          as List<Permission>;
      expect(requested, contains(Permission.notification));
    });

    test('sdkInt < 33 never requests Permission.notification', () async {
      when(() => platform.requestPermissions(any())).thenAnswer(
        (_) async => <Permission, PermissionStatus>{
          Permission.camera: PermissionStatus.granted,
          Permission.microphone: PermissionStatus.granted,
        },
      );

      await buildGate(sdkInt: 32).ensureLivePermissions();

      final requested = verify(() => platform.requestPermissions(captureAny())).captured.single
          as List<Permission>;
      expect(requested, isNot(contains(Permission.notification)));
    });
  }
  ```

- [ ] **Step 2: Run and confirm FAIL**

  `make mobile-run CMD="flutter test test/services/permission_gate_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/permission_gate.dart': No such file or directory`.

- [ ] **Step 3: Implement `lib/services/permission_gate.dart`**

  ```dart
  import 'package:device_info_plus/device_info_plus.dart';
  import 'package:permission_handler/permission_handler.dart';

  /// Outcome of requesting the permissions Gazer needs before streaming.
  enum PermissionOutcome {
    /// Every needed permission was granted.
    granted,

    /// At least one permission was denied, but the user can still be asked
    /// again — no "don't ask again" was recorded.
    denied,

    /// At least one permission was permanently denied; the only way
    /// forward is the system app settings page.
    permanentlyDenied,
  }

  /// Requests the runtime permissions Gazer needs before Go Live can start
  /// the native pipeline.
  ///
  /// Implementations must never throw — a failed permission check degrades
  /// to [PermissionOutcome.denied] rather than crashing the app.
  abstract class PermissionGate {
    /// Requests camera, microphone, and (Android 13+) notification
    /// permission, returning the combined outcome.
    Future<PermissionOutcome> ensureLivePermissions();
  }

  /// [PermissionGate] backed by `permission_handler`.
  ///
  /// `Permission.notification` is only requested on Android 13+ (API 33),
  /// where `POST_NOTIFICATIONS` became a runtime permission — [sdkInt] is
  /// injected so tests can drive both branches without a real device.
  class PermissionHandlerGate implements PermissionGate {
    PermissionHandlerGate({this.sdkInt = _defaultSdkInt});

    /// Returns the Android SDK level; defaults to the real device's via
    /// `device_info_plus`, overridden in tests.
    final Future<int> Function() sdkInt;

    static Future<int> _defaultSdkInt() async {
      final AndroidDeviceInfo info = await DeviceInfoPlugin().androidInfo;
      return info.version.sdkInt;
    }

    @override
    Future<PermissionOutcome> ensureLivePermissions() async {
      try {
        final int sdk = await sdkInt();
        final List<Permission> permissions = <Permission>[
          Permission.camera,
          Permission.microphone,
          if (sdk >= 33) Permission.notification,
        ];
        final Map<Permission, PermissionStatus> statuses = await permissions.request();

        if (statuses.values.every((PermissionStatus s) => s.isGranted)) {
          return PermissionOutcome.granted;
        }
        if (statuses.values.any((PermissionStatus s) => s.isPermanentlyDenied)) {
          return PermissionOutcome.permanentlyDenied;
        }
        return PermissionOutcome.denied;
      } catch (_) {
        return PermissionOutcome.denied;
      }
    }
  }
  ```

- [ ] **Step 4: Run and confirm PASS**

  `make mobile-run CMD="flutter test test/services/permission_gate_test.dart"`
  Expected PASS: `00:0X +5: All tests passed!`

- [ ] **Step 5: Add `permissionGateProvider` — modify `lib/providers/pipeline_provider.dart`**

  Quote the exact existing top-of-file import block (Task 12, unchanged through Task 21):
  ```dart
  import 'package:riverpod_annotation/riverpod_annotation.dart';

  import '../models/pipeline_state.dart';
  import '../models/stream_stats.dart';
  import '../services/native_event_bridge.dart';
  import '../services/pipeline_controller.dart';
  import '../services/reconnect_policy.dart';
  import 'devices_provider.dart';

  part 'pipeline_provider.g.dart';
  ```
  Replace with (one new import, alphabetically placed):
  ```dart
  import 'package:riverpod_annotation/riverpod_annotation.dart';

  import '../models/pipeline_state.dart';
  import '../models/stream_stats.dart';
  import '../services/native_event_bridge.dart';
  import '../services/permission_gate.dart';
  import '../services/pipeline_controller.dart';
  import '../services/reconnect_policy.dart';
  import 'devices_provider.dart';

  part 'pipeline_provider.g.dart';
  ```

  Quote the exact existing last provider in the file (Task 12's final `streamStats`, still the
  last provider after Task 21 — Task 21 only touched `license_provider.dart`):
  ```dart
  /// Live [StreamStats] stream, seeded with the zero snapshot the same way
  /// [pipelineState] is seeded with the controller's current state.
  @riverpod
  Stream<StreamStats> streamStats(Ref ref) async* {
    final controller = ref.watch(pipelineControllerProvider);
    yield StreamStats.zero();
    yield* controller.stats;
  }
  ```
  Replace with the same block plus a new provider appended after it:
  ```dart
  /// Live [StreamStats] stream, seeded with the zero snapshot the same way
  /// [pipelineState] is seeded with the controller's current state.
  @riverpod
  Stream<StreamStats> streamStats(Ref ref) async* {
    final controller = ref.watch(pipelineControllerProvider);
    yield StreamStats.zero();
    yield* controller.stats;
  }

  /// The [PermissionGate] HomeScreen's Go Live handler consults before ever
  /// calling [PipelineController.goLive]; overridden with a fake in widget
  /// tests so no real `permission_handler` platform channel is ever hit.
  @Riverpod(keepAlive: true)
  PermissionGate permissionGate(Ref ref) => PermissionHandlerGate();
  ```

  Run `make mobile-codegen` → succeeds (regenerates `pipeline_provider.g.dart`).
  Run `make mobile-run CMD="flutter test test/providers/pipeline_provider_test.dart"` → PASS
  (unchanged — this task adds a provider, not a behavioural change to an existing one).

- [ ] **Step 6: Add `FakePermissionGate` — modify `test/helpers/fakes.dart`**

  Quote the exact existing import block (Task 13):
  ```dart
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/models/update_info.dart';
  import 'package:gazer/services/license_client.dart';
  import 'package:gazer/services/settings_repository.dart';
  import 'package:gazer/services/update_checker.dart';
  ```
  Replace with (one new import, alphabetically placed):
  ```dart
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/models/update_info.dart';
  import 'package:gazer/services/license_client.dart';
  import 'package:gazer/services/permission_gate.dart';
  import 'package:gazer/services/settings_repository.dart';
  import 'package:gazer/services/update_checker.dart';
  ```

  Append a new class at the end of the file (after `FakeUpdateChecker`, which is the last class
  in Task 13's `fakes.dart` — quote its exact closing lines to anchor the insertion):
  ```dart
  class FakeUpdateChecker implements UpdateChecker {
    FakeUpdateChecker([this.infoToReturn]);

    /// The value every [check] call resolves to; `null` means "up to date".
    final UpdateInfo? infoToReturn;

    @override
    Future<UpdateInfo?> check() async => infoToReturn;
  }
  ```
  Replace with the same block plus a new class appended after it:
  ```dart
  class FakeUpdateChecker implements UpdateChecker {
    FakeUpdateChecker([this.infoToReturn]);

    /// The value every [check] call resolves to; `null` means "up to date".
    final UpdateInfo? infoToReturn;

    @override
    Future<UpdateInfo?> check() async => infoToReturn;
  }

  /// Test double for [PermissionGate] — returns a canned [PermissionOutcome]
  /// instead of touching the real `permission_handler` platform channel.
  class FakePermissionGate implements PermissionGate {
    FakePermissionGate([this.outcome = PermissionOutcome.granted]);

    /// The value every [ensureLivePermissions] call resolves to.
    final PermissionOutcome outcome;

    /// Number of times [ensureLivePermissions] was called.
    int callCount = 0;

    @override
    Future<PermissionOutcome> ensureLivePermissions() async {
      callCount++;
      return outcome;
    }
  }
  ```

- [ ] **Step 7: Add 4 l10n keys — modify `lib/l10n/app_en.arb`**

  Quote the exact existing last two entries (Task 13's `app_en.arb`, never touched by Tasks
  14–21 — confirmed via `grep -n "app_en.arb" docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1.md`,
  the only write is Task 13 Step 5):
  ```json
    "statusPanelForegroundServiceInactiveLabel": "Inactive",
    "statusPanelCloseButtonLabel": "Close"
  }
  ```
  Replace with:
  ```json
    "statusPanelForegroundServiceInactiveLabel": "Inactive",
    "statusPanelCloseButtonLabel": "Close",
    "permissionDeniedMessage": "Camera and microphone permission are needed to go live.",
    "permissionDeniedRetryLabel": "Retry",
    "permissionPermanentlyDeniedMessage": "Camera or microphone permission was permanently denied.",
    "permissionOpenSettingsLabel": "Open settings"
  }
  ```
  Run `make mobile-codegen` → succeeds, regenerates `lib/l10n/app_localizations*.dart` with the 4
  new getters.

- [ ] **Step 8: Gate the Go Live handler — modify `lib/screens/home_screen.dart`**

  Quote the exact existing import block (Task 16's replacement — the final version, since Task 21
  never touched this file):
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:go_router/go_router.dart';

  import '../config/flag_keys.dart';
  import '../l10n/app_localizations.dart';
  import '../l10n/error_text.dart';
  import '../models/gazer_settings.dart';
  import '../models/pipeline_state.dart';
  import '../models/validation_issue.dart';
  import '../pigeon/pipeline.g.dart';
  import '../providers/devices_provider.dart';
  import '../providers/license_provider.dart';
  import '../providers/pipeline_provider.dart';
  import '../providers/settings_provider.dart';
  import '../services/feature_flags.dart';
  import '../services/settings_validation.dart';
  import '../widgets/source_picker.dart';
  import '../widgets/status_chip.dart';
  import 'status_panel.dart';
  ```
  Replace with (new `permission_handler` package import; new `permission_gate.dart` relative
  import — `feature_flags.dart` is already imported above, since Task 16 Step 4 added it, so this
  step only verifies it rather than re-adding it):
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:go_router/go_router.dart';
  import 'package:permission_handler/permission_handler.dart';

  import '../config/flag_keys.dart';
  import '../l10n/app_localizations.dart';
  import '../l10n/error_text.dart';
  import '../models/gazer_settings.dart';
  import '../models/pipeline_state.dart';
  import '../models/validation_issue.dart';
  import '../pigeon/pipeline.g.dart';
  import '../providers/devices_provider.dart';
  import '../providers/license_provider.dart';
  import '../providers/pipeline_provider.dart';
  import '../providers/settings_provider.dart';
  import '../services/feature_flags.dart';
  import '../services/permission_gate.dart';
  import '../services/settings_validation.dart';
  import '../widgets/source_picker.dart';
  import '../widgets/status_chip.dart';
  import 'status_panel.dart';
  ```
  Verify the pre-existing `feature_flags.dart` import (the one this step used to re-add) is
  actually present rather than assuming it:
  ```bash
  grep -n "services/feature_flags.dart" mobile/gazer/lib/screens/home_screen.dart
  ```
  Expected: 1 line.

  Quote the exact existing Go Live `FilledButton` block (Task 16's final `home_screen.dart` —
  identical text also appears, now superseded, in Task 14's version):
  ```dart
            Semantics(
              label: l10n.goLiveButtonSemanticsLabel,
              button: true,
              child: FilledButton(
                key: const Key('goLiveButton'),
                onPressed: canGoLive
                    ? () => controller.goLive(
                          settings!,
                          devices: devices,
                          videoDeviceId: _selectedDeviceId!,
                          flags: flags,
                          orientation: MediaQuery.of(context).orientation == Orientation.portrait
                              ? OutputOrientation.portrait
                              : OutputOrientation.landscape,
                        )
                    : null,
                child: Text(l10n.goLiveButtonLabel),
              ),
            ),
  ```
  Replace with:
  ```dart
            Semantics(
              label: l10n.goLiveButtonSemanticsLabel,
              button: true,
              child: FilledButton(
                key: const Key('goLiveButton'),
                onPressed: canGoLive
                    ? () => _handleGoLive(context, controller, settings!, devices, flags)
                    : null,
                child: Text(l10n.goLiveButtonLabel),
              ),
            ),
  ```

  Quote the exact existing tail of the `build` method / class (Task 16's final `home_screen.dart`
  — the responsive two-pane `body:`, immediately followed by the class's closing brace and the
  `_ErrorBanner` class):
  ```dart
      body: MediaQuery.of(context).size.width >= 600
          ? Row(
              children: <Widget>[
                Expanded(flex: 2, child: controls),
                const VerticalDivider(width: 1),
                const Expanded(flex: 1, child: StatusPanel()),
              ],
            )
          : controls,
    );
  }
  }

  /// Shows the localized message + action text for the current [GazerError].
  class _ErrorBanner extends StatelessWidget {
  ```
  Replace with (inserts `_handleGoLive` between the end of `build` and the end of the class —
  note the corrected brace count: the quoted snippet's `}` then `}` above close `build()` then
  `_HomeScreenState`; the new method goes between them):
  ```dart
      body: MediaQuery.of(context).size.width >= 600
          ? Row(
              children: <Widget>[
                Expanded(flex: 2, child: controls),
                const VerticalDivider(width: 1),
                const Expanded(flex: 1, child: StatusPanel()),
              ],
            )
          : controls,
    );
  }

  /// Requests camera/microphone/notification permission via
  /// [permissionGateProvider] before ever calling [PipelineController.goLive].
  ///
  /// Denied shows a retryable [SnackBar]; permanently denied opens a
  /// dialog linking to the system app settings page; granted proceeds
  /// exactly as the pre-permission-gate Go Live handler did.
  Future<void> _handleGoLive(
    BuildContext context,
    PipelineController controller,
    GazerSettings settings,
    List<VideoDevice> devices,
    FeatureFlags flags,
  ) async {
    final AppLocalizations l10n = AppLocalizations.of(context)!;
    final PermissionGate gate = ref.read(permissionGateProvider);
    final PermissionOutcome outcome = await gate.ensureLivePermissions();
    if (!context.mounted) return;

    switch (outcome) {
      case PermissionOutcome.granted:
        controller.goLive(
          settings,
          devices: devices,
          videoDeviceId: _selectedDeviceId!,
          flags: flags,
          orientation: MediaQuery.of(context).orientation == Orientation.portrait
              ? OutputOrientation.portrait
              : OutputOrientation.landscape,
        );
      case PermissionOutcome.denied:
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(l10n.permissionDeniedMessage),
            action: SnackBarAction(
              label: l10n.permissionDeniedRetryLabel,
              onPressed: () => _handleGoLive(context, controller, settings, devices, flags),
            ),
          ),
        );
      case PermissionOutcome.permanentlyDenied:
        await showDialog<void>(
          context: context,
          builder: (BuildContext dialogContext) => AlertDialog(
            content: Text(l10n.permissionPermanentlyDeniedMessage),
            actions: <Widget>[
              TextButton(
                onPressed: () {
                  Navigator.of(dialogContext).pop();
                  openAppSettings();
                },
                child: Text(l10n.permissionOpenSettingsLabel),
              ),
            ],
          ),
        );
    }
  }
  }

  /// Shows the localized message + action text for the current [GazerError].
  class _ErrorBanner extends StatelessWidget {
  ```

- [ ] **Step 9: Run and confirm FAIL (before the test-file update in Step 10)**

  `make mobile-run CMD="flutter test test/screens/home_screen_test.dart"`
  Expected FAIL: every test that taps "Go Live" now hangs/errors on a real `permission_handler`
  platform-channel call (`MissingPluginException` — no `PermissionHandlerPlatform.instance` mock
  registered in this test binding), since `overrides()` does not yet override
  `permissionGateProvider`:
  ```
  MissingPluginException(No implementation found for method requestPermissions on channel flutter.baseflow.com/permissions/methods)
  ```

- [ ] **Step 10: Fix the shared override + add 3 new tests — modify `test/screens/home_screen_test.dart`**

  Quote the exact existing `overrides()` helper (Task 14's `home_screen_test.dart`, never
  modified since):
  ```dart
    List<Override> overrides({required LicenseState license}) => <Override>[
          settingsRepositoryProvider.overrideWithValue(settingsRepo),
          gazerHostApiProvider.overrideWithValue(hostApi),
          // Wires hostApi.bridge into the controller under test so
          // hostApi.emitState(...) below actually reaches pipelineStateProvider
          // — see Task 11's FakeGazerHostApi doc (overriding gazerHostApiProvider
          // alone does not connect the two).
          pipelineControllerProvider.overrideWithValue(
            PipelineController(host: hostApi, events: hostApi.bridge, policy: ReconnectPolicy()),
          ),
          licenseClientProvider.overrideWith((Ref ref) async => FakeLicenseClient(license)),
          isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
          updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
        ];
  ```
  Replace with (adds an optional `permissionGate` parameter, defaulting to a granted fake so the
  3 pre-existing tap tests need no changes):
  ```dart
    List<Override> overrides({required LicenseState license, PermissionGate? permissionGate}) =>
        <Override>[
          settingsRepositoryProvider.overrideWithValue(settingsRepo),
          gazerHostApiProvider.overrideWithValue(hostApi),
          // Wires hostApi.bridge into the controller under test so
          // hostApi.emitState(...) below actually reaches pipelineStateProvider
          // — see Task 11's FakeGazerHostApi doc (overriding gazerHostApiProvider
          // alone does not connect the two).
          pipelineControllerProvider.overrideWithValue(
            PipelineController(host: hostApi, events: hostApi.bridge, policy: ReconnectPolicy()),
          ),
          licenseClientProvider.overrideWith((Ref ref) async => FakeLicenseClient(license)),
          isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
          updateCheckerProvider.overrideWith((Ref ref) async => FakeUpdateChecker(null)),
          permissionGateProvider.overrideWithValue(permissionGate ?? FakePermissionGate()),
        ];
  ```

  Add one import (`permission_gate.dart` — `PermissionGate`/`PermissionOutcome` are referenced
  directly by the new tests below). Quote the exact existing import block:
  ```dart
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/providers/connectivity_provider.dart';
  import 'package:gazer/providers/devices_provider.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/providers/settings_provider.dart';
  import 'package:gazer/providers/update_provider.dart';
  import 'package:gazer/services/pipeline_controller.dart';
  import 'package:gazer/services/reconnect_policy.dart';

  import '../helpers/fake_host_api.dart';
  import '../helpers/fakes.dart';
  import '../helpers/pump_app.dart';
  ```
  Replace with:
  ```dart
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/providers/connectivity_provider.dart';
  import 'package:gazer/providers/devices_provider.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/providers/settings_provider.dart';
  import 'package:gazer/providers/update_provider.dart';
  import 'package:gazer/services/permission_gate.dart';
  import 'package:gazer/services/pipeline_controller.dart';
  import 'package:gazer/services/reconnect_policy.dart';

  import '../helpers/fake_host_api.dart';
  import '../helpers/fakes.dart';
  import '../helpers/pump_app.dart';
  ```

  Append 3 new tests at the end of `main()` (after the existing `'error state shows the localized
  message and action text'` test — quote its exact closing lines to anchor the insertion):
  ```dart
    testWidgets('error state shows the localized message and action text', (WidgetTester tester) async {
      await pumpGazerApp(tester, overrides: overrides(license: _license(flagsSet: true)));
      await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
      await tester.pumpAndSettle();
      await hostApi.emitState(NativePipelineState.error, error: GazerErrorCode.rtmpConnectFailed);
      await tester.pumpAndSettle();
      expect(find.text('Could not connect to the streaming server.'), findsOneWidget);
      expect(find.text('Check the URL and your network connection, then try again.'), findsOneWidget);
    });
  }
  ```
  Replace with:
  ```dart
    testWidgets('error state shows the localized message and action text', (WidgetTester tester) async {
      await pumpGazerApp(tester, overrides: overrides(license: _license(flagsSet: true)));
      await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
      await tester.pumpAndSettle();
      await hostApi.emitState(NativePipelineState.error, error: GazerErrorCode.rtmpConnectFailed);
      await tester.pumpAndSettle();
      expect(find.text('Could not connect to the streaming server.'), findsOneWidget);
      expect(find.text('Check the URL and your network connection, then try again.'), findsOneWidget);
    });

    testWidgets('denied permission shows a SnackBar with a retry action, and does not prepare',
        (WidgetTester tester) async {
      final gate = FakePermissionGate(PermissionOutcome.denied);
      await pumpGazerApp(
        tester,
        overrides: overrides(license: _license(flagsSet: true), permissionGate: gate),
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
      await tester.pumpAndSettle();
      expect(find.text('Camera and microphone permission are needed to go live.'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      expect(hostApi.prepareCalls, isEmpty);
    });

    testWidgets('permanentlyDenied permission shows a dialog with an Open settings button, and does not prepare',
        (WidgetTester tester) async {
      final gate = FakePermissionGate(PermissionOutcome.permanentlyDenied);
      await pumpGazerApp(
        tester,
        overrides: overrides(license: _license(flagsSet: true), permissionGate: gate),
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
      await tester.pumpAndSettle();
      expect(find.text('Camera or microphone permission was permanently denied.'), findsOneWidget);
      expect(find.text('Open settings'), findsOneWidget);
      expect(hostApi.prepareCalls, isEmpty);
    });

    testWidgets('granted permission proceeds to call prepare', (WidgetTester tester) async {
      final gate = FakePermissionGate(PermissionOutcome.granted);
      await pumpGazerApp(
        tester,
        overrides: overrides(license: _license(flagsSet: true), permissionGate: gate),
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
      await tester.pumpAndSettle();
      expect(gate.callCount, 1);
      expect(hostApi.prepareCalls, hasLength(1));
    });
  }
  ```

- [ ] **Step 11: Run and confirm PASS**

  `make mobile-run CMD="flutter test test/screens/home_screen_test.dart"`
  Expected PASS: `00:0X +9: All tests passed!` (6 pre-existing + 3 new).

- [ ] **Step 12: Regression-check Tasks 13–16's suites**

  `make mobile-run CMD="flutter test test/app_test.dart test/screens test/widgets test/goldens"`
  Expected PASS: `00:0X +N: All tests passed!` — no regression from the shared `overrides()`
  signature change (every other call site still passes only `license:`, and `permissionGate`
  defaults to a granted fake).

- [ ] **Step 13: Lint**

  `make mobile-lint` → `No issues found!`

- [ ] **Step 14: Commit**

  ```bash
  git add mobile/gazer/lib/services/permission_gate.dart mobile/gazer/test/services/permission_gate_test.dart \
          mobile/gazer/lib/providers/pipeline_provider.dart mobile/gazer/lib/screens/home_screen.dart \
          mobile/gazer/lib/l10n/app_en.arb mobile/gazer/lib/l10n/app_localizations.dart \
          mobile/gazer/lib/l10n/app_localizations_en.dart mobile/gazer/test/helpers/fakes.dart \
          mobile/gazer/test/screens/home_screen_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): gate Go Live on camera/mic/notification permission

  PermissionHandlerGate requests CAMERA/RECORD_AUDIO always and
  POST_NOTIFICATIONS on Android 13+ before HomeScreen's Go Live handler
  ever calls PipelineController.goLive — denied shows a retryable
  SnackBar, permanently denied opens a dialog to the app settings page.
  Matches MainActivity's existing doc comment that permissions are
  "handled entirely in Dart via permission_handler before Go Live is
  ever called."

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 23: License keepalive scheduler

**Files:**
- Create: `mobile/gazer/lib/services/keepalive_scheduler.dart`
- Test: `mobile/gazer/test/services/keepalive_scheduler_test.dart`
- Modify: `mobile/gazer/lib/providers/license_provider.dart` (add `keepaliveSchedulerProvider`)
- Modify: `mobile/gazer/lib/app.dart` (`GazerApp` becomes a `ConsumerStatefulWidget` +
  `WidgetsBindingObserver`, starts/stops the scheduler)
- Modify: `mobile/gazer/test/app_test.dart` (1 new test)

**Interfaces:**
- Consumes: `licenseProvider`/`licenseClientProvider` (`lib/providers/license_provider.dart`,
  Task 12/21), `LicenseClient.keepalive()` (Task 9 — already implemented, never called before
  this task), `kLicenseKeepaliveInterval` (`lib/config/constants.dart`, Task 9, `Duration(minutes: 5)`),
  `AppLocalizations`/`GazerApp` (Task 13), `FakeLicenseClient` (Task 13's `test/helpers/fakes.dart`
  — already tracks `keepaliveCalls`, no fakes.dart change needed).
- Produces: `class KeepaliveScheduler { KeepaliveScheduler({required Future<void> Function() ping,
  required Duration interval, Timer Function(Duration, void Function(Timer)) periodic =
  Timer.periodic}); void start(); void stop(); bool get isRunning; int failures; void
  onLifecycle(AppLifecycleState state); }`, `keepaliveSchedulerProvider` (`@Riverpod(keepAlive:
  true)`, `lib/providers/license_provider.dart`).

- [ ] **Step 1: Write the failing test `test/services/keepalive_scheduler_test.dart`**

  ```dart
  import 'dart:async';

  import 'package:flutter/widgets.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/services/keepalive_scheduler.dart';

  /// [Timer]-compatible fake that never runs on a real clock: the test
  /// calls [tick] to invoke the scheduled callback manually.
  class _ManualTimer implements Timer {
    _ManualTimer(this._onCancel);

    final void Function() _onCancel;
    bool _active = true;

    @override
    void cancel() {
      _active = false;
      _onCancel();
    }

    @override
    bool get isActive => _active;

    @override
    int get tick => 0;
  }

  /// Fake `Timer.periodic`-shaped factory: records the scheduled callback
  /// instead of starting a real timer, and lets the test fire it via [tick].
  class _ManualPeriodic {
    void Function(Timer)? _callback;
    _ManualTimer? _lastTimer;
    int cancelCount = 0;

    Timer call(Duration duration, void Function(Timer) callback) {
      _callback = callback;
      _lastTimer = _ManualTimer(() => cancelCount++);
      return _lastTimer!;
    }

    /// Manually fires the scheduled callback, as if [duration] had elapsed.
    void tick() {
      final cb = _callback;
      final timer = _lastTimer;
      if (cb != null && timer != null) cb(timer);
    }
  }

  void main() {
    late _ManualPeriodic periodic;
    late int pingCalls;
    late bool shouldFail;

    Future<void> ping() async {
      pingCalls++;
      if (shouldFail) throw StateError('ping failed');
    }

    setUp(() {
      periodic = _ManualPeriodic();
      pingCalls = 0;
      shouldFail = false;
    });

    KeepaliveScheduler buildScheduler() => KeepaliveScheduler(
          ping: ping,
          interval: const Duration(minutes: 5),
          periodic: periodic.call,
        );

    test('does not ping before start', () {
      buildScheduler();
      periodic.tick();
      expect(pingCalls, 0);
    });

    test('start begins ticking; stop cancels the timer', () {
      final scheduler = buildScheduler();
      scheduler.start();
      expect(scheduler.isRunning, isTrue);

      periodic.tick();
      expect(pingCalls, 1);

      scheduler.stop();
      expect(scheduler.isRunning, isFalse);
      expect(periodic.cancelCount, 1);
    });

    test('start is idempotent — a second call does not create a new timer', () {
      final scheduler = buildScheduler();
      scheduler.start();
      scheduler.start();
      periodic.tick();
      expect(pingCalls, 1);
    });

    test('stop is idempotent — a second call is a no-op', () {
      final scheduler = buildScheduler();
      scheduler.start();
      scheduler.stop();
      scheduler.stop();
      expect(periodic.cancelCount, 1);
    });

    test('onLifecycle starts on resumed and stops on paused/inactive/detached/hidden', () {
      final scheduler = buildScheduler();

      for (final state in <AppLifecycleState>[
        AppLifecycleState.paused,
        AppLifecycleState.inactive,
        AppLifecycleState.detached,
        AppLifecycleState.hidden,
      ]) {
        scheduler.onLifecycle(AppLifecycleState.resumed);
        expect(scheduler.isRunning, isTrue);
        scheduler.onLifecycle(state);
        expect(scheduler.isRunning, isFalse, reason: '$state must stop the scheduler');
      }
    });

    test('ping failures are swallowed and counted; the scheduler keeps running', () async {
      final scheduler = buildScheduler();
      shouldFail = true;
      scheduler.start();

      periodic.tick();
      await Future<void>.delayed(Duration.zero);

      expect(scheduler.failures, 1);
      expect(scheduler.isRunning, isTrue);
    });
  }
  ```

- [ ] **Step 2: Run and confirm FAIL**

  `make mobile-run CMD="flutter test test/services/keepalive_scheduler_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/keepalive_scheduler.dart': No such file or directory`.

- [ ] **Step 3: Implement `lib/services/keepalive_scheduler.dart`**

  ```dart
  import 'dart:async';

  import 'package:flutter/widgets.dart';

  /// Periodically pings the license server while the app is foregrounded.
  ///
  /// Owns exactly one [Timer]: [start] is idempotent (a second call while
  /// already running is a no-op), [stop] cancels it, and [onLifecycle]
  /// wires both to `WidgetsBindingObserver.didChangeAppLifecycleState` —
  /// [AppLifecycleState.resumed] starts it, every backgrounded state stops
  /// it. [ping] failures are swallowed (never crash the app) and counted
  /// in [failures] for diagnostics.
  class KeepaliveScheduler {
    KeepaliveScheduler({
      required Future<void> Function() ping,
      required Duration interval,
      Timer Function(Duration, void Function(Timer)) periodic = Timer.periodic,
    })  : _ping = ping,
          _interval = interval,
          _periodic = periodic;

    final Future<void> Function() _ping;
    final Duration _interval;
    final Timer Function(Duration, void Function(Timer)) _periodic;

    Timer? _timer;

    /// Number of [ping] calls that threw since this scheduler was created.
    int failures = 0;

    /// Whether the periodic timer is currently active.
    bool get isRunning => _timer != null;

    /// Starts the periodic ping if not already running.
    void start() {
      if (_timer != null) return;
      _timer = _periodic(_interval, (_) => _tick());
    }

    /// Cancels the periodic ping if running; safe to call when already
    /// stopped.
    void stop() {
      _timer?.cancel();
      _timer = null;
    }

    /// Starts on [AppLifecycleState.resumed]; stops on every backgrounded
    /// state (paused/inactive/detached/hidden).
    void onLifecycle(AppLifecycleState state) {
      switch (state) {
        case AppLifecycleState.resumed:
          start();
        case AppLifecycleState.paused:
        case AppLifecycleState.inactive:
        case AppLifecycleState.detached:
        case AppLifecycleState.hidden:
          stop();
      }
    }

    Future<void> _tick() async {
      try {
        await _ping();
      } catch (_) {
        failures++;
      }
    }
  }
  ```

- [ ] **Step 4: Run and confirm PASS**

  `make mobile-run CMD="flutter test test/services/keepalive_scheduler_test.dart"`
  Expected PASS: `00:0X +6: All tests passed!`

- [ ] **Step 5: Add `keepaliveSchedulerProvider` — modify `lib/providers/license_provider.dart`**

  Quote the exact existing top-of-file import block (Task 12's original; Task 21 added the
  `debug_overrides.dart` import inside the file body per its own Step 6, not here at the top —
  reconfirm with `grep -n "^import" mobile/gazer/lib/providers/license_provider.dart` before
  editing, in case a future formatter moved it):
  ```dart
  import 'package:device_info_plus/device_info_plus.dart';
  import 'package:dio/dio.dart';
  import 'package:package_info_plus/package_info_plus.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../models/license_state.dart';
  import '../services/device_id.dart';
  import '../services/feature_flags.dart';
  import '../services/license_client.dart';

  part 'license_provider.g.dart';
  ```
  Replace with (two new relative imports, alphabetically placed):
  ```dart
  import 'package:device_info_plus/device_info_plus.dart';
  import 'package:dio/dio.dart';
  import 'package:package_info_plus/package_info_plus.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../config/constants.dart';
  import '../models/license_state.dart';
  import '../services/device_id.dart';
  import '../services/feature_flags.dart';
  import '../services/keepalive_scheduler.dart';
  import '../services/license_client.dart';

  part 'license_provider.g.dart';
  ```

  Quote the exact existing last function in the file (`featureFlags` — unchanged by Task 21,
  which only modified `license()` above it):
  ```dart
    /// Read-only view over [license] for flag checks; never throws — while
    /// [license] is loading or has errored, flags default to all-OFF via
    /// [LicenseState.initial]'s empty flag map, since [FeatureFlags.isEnabled]
    /// treats an absent key as OFF.
    @riverpod
    FeatureFlags featureFlags(Ref ref) {
      final asyncState = ref.watch(licenseProvider);
      final state = asyncState.valueOrNull ?? LicenseState.initial('');
      return FeatureFlags(state);
    }
  ```
  Replace with the same block plus a new provider appended after it:
  ```dart
    /// Read-only view over [license] for flag checks; never throws — while
    /// [license] is loading or has errored, flags default to all-OFF via
    /// [LicenseState.initial]'s empty flag map, since [FeatureFlags.isEnabled]
    /// treats an absent key as OFF.
    @riverpod
    FeatureFlags featureFlags(Ref ref) {
      final asyncState = ref.watch(licenseProvider);
      final state = asyncState.valueOrNull ?? LicenseState.initial('');
      return FeatureFlags(state);
    }

    /// The app-wide [KeepaliveScheduler], pinging the license server every
    /// [kLicenseKeepaliveInterval] while foregrounded — [GazerApp] starts it
    /// once the first [license] fetch resolves and drives it thereafter via
    /// `WidgetsBindingObserver.didChangeAppLifecycleState`.
    ///
    /// `ref.onDispose(scheduler.stop)` guarantees the underlying [Timer] is
    /// always cancelled when the provider container is disposed — including
    /// in widget tests, where every `pumpGazerApp` call creates a fresh
    /// `ProviderScope` that must never leak a pending [Timer] into the next
    /// test.
    @Riverpod(keepAlive: true)
    KeepaliveScheduler keepaliveScheduler(Ref ref) {
      final scheduler = KeepaliveScheduler(
        ping: () async {
          final LicenseClient client = await ref.read(licenseClientProvider.future);
          await client.keepalive();
        },
        interval: kLicenseKeepaliveInterval,
      );
      ref.onDispose(scheduler.stop);
      return scheduler;
    }
  ```

  Run `make mobile-codegen` → succeeds. Run `make mobile-run CMD="flutter test
  test/providers/license_provider_test.dart test/providers/license_provider_debug_override_test.dart"`
  → PASS (unchanged — this task only adds a new provider).

- [ ] **Step 6: Wire the scheduler into the app shell — modify `lib/app.dart`**

  Quote the exact existing import block (Task 13):
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_libs/flutter_libs.dart';
  import 'package:go_router/go_router.dart';

  import 'l10n/app_localizations.dart';
  import 'screens/home_screen.dart';
  import 'screens/settings_screen.dart';
  ```
  Replace with:
  ```dart
  import 'dart:async';

  import 'package:flutter/material.dart';
  import 'package:flutter_libs/flutter_libs.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:go_router/go_router.dart';

  import 'l10n/app_localizations.dart';
  import 'providers/license_provider.dart';
  import 'screens/home_screen.dart';
  import 'screens/settings_screen.dart';
  ```

  Quote the exact existing `GazerApp` class (the `gazerRouter` declaration above it is unchanged
  and not reproduced here):
  ```dart
  class GazerApp extends StatelessWidget {
    const GazerApp({super.key});

    static ThemeData get _elderDarkTheme => ThemeData.dark().copyWith(
          scaffoldBackgroundColor: ElderThemeData.dark.pageBackground,
          colorScheme: ThemeData.dark().colorScheme.copyWith(
                primary: ElderThemeData.dark.primaryButton,
                onPrimary: ElderThemeData.dark.primaryButtonText,
                error: ElderThemeData.dark.errorText,
              ),
          extensions: <ThemeExtension<dynamic>>[ElderThemeData.dark],
        );

    @override
    Widget build(BuildContext context) {
      return MaterialApp.router(
        onGenerateTitle: (BuildContext context) => AppLocalizations.of(context)!.appTitle,
        theme: _elderDarkTheme,
        darkTheme: _elderDarkTheme,
        themeMode: ThemeMode.system,
        routerConfig: gazerRouter,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
      );
    }
  }
  ```
  Replace with:
  ```dart
  class GazerApp extends ConsumerStatefulWidget {
    const GazerApp({super.key});

    static ThemeData get _elderDarkTheme => ThemeData.dark().copyWith(
          scaffoldBackgroundColor: ElderThemeData.dark.pageBackground,
          colorScheme: ThemeData.dark().colorScheme.copyWith(
                primary: ElderThemeData.dark.primaryButton,
                onPrimary: ElderThemeData.dark.primaryButtonText,
                error: ElderThemeData.dark.errorText,
              ),
          extensions: <ThemeExtension<dynamic>>[ElderThemeData.dark],
        );

    @override
    ConsumerState<GazerApp> createState() => _GazerAppState();
  }

  /// Owns the app-wide [KeepaliveScheduler] lifecycle: starts it once the
  /// first [licenseProvider] fetch resolves (success or degraded/offline —
  /// [LicenseClient] never throws), then starts/stops it on every
  /// subsequent foreground/background transition via
  /// [WidgetsBindingObserver].
  class _GazerAppState extends ConsumerState<GazerApp> with WidgetsBindingObserver {
    @override
    void initState() {
      super.initState();
      WidgetsBinding.instance.addObserver(this);
      unawaited(_startKeepaliveAfterFirstFetch());
    }

    Future<void> _startKeepaliveAfterFirstFetch() async {
      try {
        await ref.read(licenseProvider.future);
      } catch (_) {
        // LicenseClient never throws by contract; if this ever fires we
        // still want the keepalive loop foregrounded rather than silently
        // never starting.
      }
      if (!mounted) return;
      ref.read(keepaliveSchedulerProvider).start();
    }

    @override
    void didChangeAppLifecycleState(AppLifecycleState state) {
      ref.read(keepaliveSchedulerProvider).onLifecycle(state);
    }

    @override
    void dispose() {
      WidgetsBinding.instance.removeObserver(this);
      super.dispose();
    }

    @override
    Widget build(BuildContext context) {
      return MaterialApp.router(
        onGenerateTitle: (BuildContext context) => AppLocalizations.of(context)!.appTitle,
        theme: GazerApp._elderDarkTheme,
        darkTheme: GazerApp._elderDarkTheme,
        themeMode: ThemeMode.system,
        routerConfig: gazerRouter,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
      );
    }
  }
  ```

  `main.dart`'s `runApp(const ProviderScope(child: GazerApp()));` (Task 13) needs no change —
  `GazerApp` keeps a `const` constructor as a `ConsumerStatefulWidget`.

- [ ] **Step 7: Run and confirm FAIL (before the test-file update in Step 8)**

  `make mobile-run CMD="flutter test test/app_test.dart"`
  Expected: still PASS for the 2 existing tests (this step's change is additive/behavioural, not
  a widget-tree change) — run once now to confirm no regression before adding the new test in
  Step 8: `00:0X +2: All tests passed!`

- [ ] **Step 8: Add 1 new test — modify `test/app_test.dart`**

  Add one import (`keepalive_scheduler.dart`) — quote the exact existing import block:
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/providers/connectivity_provider.dart';
  import 'package:gazer/providers/devices_provider.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/providers/settings_provider.dart';
  import 'package:gazer/providers/update_provider.dart';
  import 'package:gazer/screens/home_screen.dart';
  import 'package:gazer/screens/settings_screen.dart';

  import 'helpers/fake_host_api.dart';
  import 'helpers/fakes.dart';
  import 'helpers/pump_app.dart';
  ```
  Replace with:
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/providers/connectivity_provider.dart';
  import 'package:gazer/providers/devices_provider.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/providers/settings_provider.dart';
  import 'package:gazer/providers/update_provider.dart';
  import 'package:gazer/screens/home_screen.dart';
  import 'package:gazer/screens/settings_screen.dart';
  import 'package:gazer/services/keepalive_scheduler.dart';

  import 'helpers/fake_host_api.dart';
  import 'helpers/fakes.dart';
  import 'helpers/pump_app.dart';
  ```

  Quote the exact existing 2nd (final) test to anchor the insertion:
  ```dart
    testWidgets('navigating to /settings shows SettingsScreen', (WidgetTester tester) async {
      await pumpGazerApp(tester, overrides: overrides());
      await tester.tap(find.byIcon(Icons.settings));
      await tester.pumpAndSettle();
      expect(find.byType(SettingsScreen), findsOneWidget);
    });
  }
  ```
  Replace with:
  ```dart
    testWidgets('navigating to /settings shows SettingsScreen', (WidgetTester tester) async {
      await pumpGazerApp(tester, overrides: overrides());
      await tester.tap(find.byIcon(Icons.settings));
      await tester.pumpAndSettle();
      expect(find.byType(SettingsScreen), findsOneWidget);
    });

    testWidgets('keepalive scheduler starts after the first license fetch and stops on paused',
        (WidgetTester tester) async {
      late KeepaliveScheduler scheduler;
      await pumpGazerApp(
        tester,
        overrides: <Override>[
          ...overrides(),
          keepaliveSchedulerProvider.overrideWith((Ref ref) {
            scheduler = KeepaliveScheduler(ping: () async {}, interval: const Duration(minutes: 5));
            ref.onDispose(scheduler.stop);
            return scheduler;
          }),
        ],
      );

      expect(scheduler.isRunning, isTrue);

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      expect(scheduler.isRunning, isFalse);
    });
  }
  ```

- [ ] **Step 9: Run and confirm PASS**

  `make mobile-run CMD="flutter test test/app_test.dart"`
  Expected PASS: `00:0X +3: All tests passed!`

- [ ] **Step 10: Regression-check the whole Dart suite**

  `make mobile-test` → PASS: every suite from Tasks 4–23 green together, coverage gate ≥90% (the
  `scripts/coverage_gate.sh` from Task 1 asserts a non-zero denominator of files examined) — this
  specifically confirms no test file anywhere is left with a dangling `Timer` from an
  un-disposed `keepaliveSchedulerProvider` override.

- [ ] **Step 11: Lint**

  `make mobile-lint` → `No issues found!`

- [ ] **Step 12: Commit**

  ```bash
  git add mobile/gazer/lib/services/keepalive_scheduler.dart mobile/gazer/test/services/keepalive_scheduler_test.dart \
          mobile/gazer/lib/providers/license_provider.dart mobile/gazer/lib/app.dart \
          mobile/gazer/test/app_test.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): ping the license server every 5 minutes while foregrounded

  KeepaliveScheduler wraps LicenseClient.keepalive() (implemented since
  Task 9, never called before now) behind a lifecycle-aware Timer.
  GazerApp becomes a ConsumerStatefulWidget + WidgetsBindingObserver:
  starts the scheduler once the first license fetch resolves, then
  starts/stops it on every foreground/background transition.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

### Task 24: Sanitized logging and debug-log toggle

**Files:**
- Create: `mobile/gazer/lib/services/gazer_log.dart`
- Test: `mobile/gazer/test/services/gazer_log_test.dart`
- Modify: `mobile/gazer/lib/models/gazer_settings.dart` (Task 4 — add `debugLogs` field)
- Modify: `mobile/gazer/test/models/gazer_settings_test.dart` (Task 4 test — 1 constructor site + 1 assertion)
- Modify: `mobile/gazer/lib/services/settings_repository.dart` (Task 7 — persist `debugLogs`)
- Modify: `mobile/gazer/test/services/settings_repository_test.dart` (Task 7 test — 2 constructor sites)
- Modify: `mobile/gazer/test/services/pipeline_controller_test.dart` (Task 11 test — 1 constructor site)
- Modify: `mobile/gazer/lib/providers/settings_provider.dart` (Task 12 — wire `GazerLog.verbose`)
- Modify: `mobile/gazer/lib/screens/settings_screen.dart` (Task 15 — 2nd Developer switch)
- Modify: `mobile/gazer/test/screens/settings_screen_test.dart` (Task 15 test — 1 new test)
- Modify: `mobile/gazer/lib/l10n/app_en.arb` (1 new key)
- Modify: `mobile/gazer/lib/services/license_client.dart` (Task 9 — log fetch outcome)
- Modify: `mobile/gazer/lib/services/pipeline_controller.dart` (Task 11 — log state/reconnect/goLive)

**Interfaces:**
- Consumes: `dart:developer`'s `log()`, `dart:convert`'s `jsonEncode`, `GazerSettings` (Task 4),
  `SecureSettingsRepository`/`SettingsNotifier` (Task 7/12), `LicenseClient`/`LicenseState` (Task
  9), `PipelineController`/`PipelineState`/`ErrorState`/`GazerError` (Task 11).
- Produces: `class GazerLog { static bool verbose; static void Function(String line) sink; static
  void info(String event, [Map<String, Object?> fields]); static void warn(...); static void
  error(...); static void debug(...); static String maskSecret(String? value); static
  Map<String, Object?> sanitize(Map<String, Object?> fields); }`, l10n key
  `settingsDebugLogsLabel`.

- [ ] **Step 1: Write the failing test `test/services/gazer_log_test.dart`**

  ```dart
  import 'dart:convert';

  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/services/gazer_log.dart';

  void main() {
    late void Function(String line) originalSink;
    late bool originalVerbose;

    setUpAll(() {
      originalSink = GazerLog.sink;
      originalVerbose = GazerLog.verbose;
    });

    setUp(() {
      GazerLog.verbose = false;
    });

    tearDown(() {
      GazerLog.sink = originalSink;
      GazerLog.verbose = originalVerbose;
    });

    group('maskSecret', () {
      final cases = <String?, String>{
        null: '',
        '': '',
        'abc': '****',
        'demo-key-0001': '****0001',
      };

      for (final entry in cases.entries) {
        test('${entry.key} -> "${entry.value}"', () {
          expect(GazerLog.maskSecret(entry.key), entry.value);
        });
      }
    });

    group('sanitize', () {
      test('masks password/streamKey/username and only the url last segment', () {
        final result = GazerLog.sanitize(<String, Object?>{
          'password': 's3cretpass',
          'streamKey': 'demo-key-0001',
          'username': 'demo-user',
          'url': 'rtmp://ingest.example.com/live/mystream',
          'host': 'ingest.example.com',
        });

        expect(result['password'], '****pass');
        expect(result['streamKey'], '****0001');
        expect(result['username'], '****user');
        expect(result['host'], 'ingest.example.com');

        final maskedUrl = result['url'] as String;
        expect(maskedUrl, startsWith('rtmp://ingest.example.com/live/'));
        expect(maskedUrl, isNot(contains('mystream')));
        expect(maskedUrl, contains('****ream'));
      });
    });

    group('emission', () {
      test('info emits one JSON line with ts/level/event/fields', () {
        final lines = <String>[];
        GazerLog.sink = lines.add;

        GazerLog.info('license.fetch', <String, Object?>{'status': 'valid', 'flagCount': 4});

        expect(lines, hasLength(1));
        final decoded = jsonDecode(lines.single) as Map<String, dynamic>;
        expect(decoded['level'], 'info');
        expect(decoded['event'], 'license.fetch');
        expect(decoded['status'], 'valid');
        expect(decoded['flagCount'], 4);
        expect(decoded['ts'], isNotNull);
      });

      test('debug emits only when verbose is enabled', () {
        final lines = <String>[];
        GazerLog.sink = lines.add;

        GazerLog.verbose = false;
        GazerLog.debug('pipeline.state', <String, Object?>{'from': 'idle', 'to': 'preparing'});
        expect(lines, isEmpty);

        GazerLog.verbose = true;
        GazerLog.debug('pipeline.state', <String, Object?>{'from': 'idle', 'to': 'preparing'});
        expect(lines, hasLength(1));
        final decoded = jsonDecode(lines.single) as Map<String, dynamic>;
        expect(decoded['level'], 'debug');
      });
    });
  }
  ```

- [ ] **Step 2: Run and confirm FAIL**

  `make mobile-run CMD="flutter test test/services/gazer_log_test.dart"`
  Expected FAIL: `Error: Error when reading 'lib/services/gazer_log.dart': No such file or directory`.

- [ ] **Step 3: Implement `lib/services/gazer_log.dart`**

  ```dart
  import 'dart:convert';
  import 'dart:developer' as developer;

  /// Structured, sanitized logging for Gazer.
  ///
  /// Emits one JSON line per call via `dart:developer`'s `log()` — never
  /// `print` — masking secrets so tokens/credentials never reach device
  /// logs. [debug] only emits when [verbose] is on, wired from the user's
  /// Settings > Developer > Debug logs toggle (`GazerSettings.debugLogs`).
  class GazerLog {
    GazerLog._();

    /// Whether [debug] calls actually emit.
    static bool verbose = false;

    /// Where every JSON line is written; overridable in tests to capture
    /// output instead of going through `dart:developer`'s `log()`, which
    /// cannot be intercepted directly.
    static void Function(String line) sink = _developerSink;

    static void _developerSink(String line) => developer.log(line, name: 'gazer');

    static void info(String event, [Map<String, Object?> fields = const {}]) =>
        _emit('info', event, fields);

    static void warn(String event, [Map<String, Object?> fields = const {}]) =>
        _emit('warn', event, fields);

    static void error(String event, [Map<String, Object?> fields = const {}]) =>
        _emit('error', event, fields);

    /// Only emits when [verbose] is enabled.
    static void debug(String event, [Map<String, Object?> fields = const {}]) {
      if (!verbose) return;
      _emit('debug', event, fields);
    }

    static void _emit(String level, String event, Map<String, Object?> fields) {
      final record = <String, Object?>{
        'ts': DateTime.now().toIso8601String(),
        'level': level,
        'event': event,
        ...sanitize(fields),
      };
      sink(jsonEncode(record));
    }

    /// Masks [value]: `null`/empty -> `''`; otherwise `'****'` + the last 4
    /// characters, or just `'****'` when shorter than 4 characters.
    static String maskSecret(String? value) {
      if (value == null || value.isEmpty) return '';
      if (value.length < 4) return '****';
      return '****${value.substring(value.length - 4)}';
    }

    /// Masks any field named `password`/`streamKey`/`username` wholesale via
    /// [maskSecret]; a field named `url` keeps its scheme/host but masks
    /// only its last path segment, since the full path/query may embed the
    /// stream key.
    static Map<String, Object?> sanitize(Map<String, Object?> fields) {
      return fields.map((String key, Object? value) {
        if (value is! String) return MapEntry(key, value);
        switch (key) {
          case 'password':
          case 'streamKey':
          case 'username':
            return MapEntry(key, maskSecret(value));
          case 'url':
            return MapEntry(key, _maskUrlLastSegment(value));
          default:
            return MapEntry(key, value);
        }
      });
    }

    static String _maskUrlLastSegment(String url) {
      final uri = Uri.tryParse(url);
      if (uri == null || uri.pathSegments.isEmpty) return url;
      final segments = List<String>.from(uri.pathSegments);
      segments[segments.length - 1] = maskSecret(segments.last);
      return uri.replace(pathSegments: segments).toString();
    }
  }
  ```

- [ ] **Step 4: Run and confirm PASS**

  `make mobile-run CMD="flutter test test/services/gazer_log_test.dart"`
  Expected PASS: `00:0X +7: All tests passed!` (4 `maskSecret` cases + 1 `sanitize` + 2 `emission`).

- [ ] **Step 5: Add `debugLogs` to `GazerSettings` — modify `lib/models/gazer_settings.dart`**

  Quote the exact existing class (Task 4):
  ```dart
  @freezed
  abstract class GazerSettings with _$GazerSettings {
    const factory GazerSettings({
      required StreamTargetSettings target,
      required QualitySettings quality,
      required AudioSourceChoice audio,
      required bool forceLibuvc,
    }) = _GazerSettings;

    /// Deserializes a [GazerSettings] from JSON (round-trip tests only —
    /// [SecureSettingsRepository] persists fields individually, not as one blob).
    factory GazerSettings.fromJson(Map<String, dynamic> json) =>
        _$GazerSettingsFromJson(json);

    /// First-launch defaults: empty target, default quality, auto audio,
    /// developer toggle off.
    factory GazerSettings.defaults() => GazerSettings(
          target: StreamTargetSettings.empty(),
          quality: QualitySettings.defaults(),
          audio: AudioSourceChoice.auto,
          forceLibuvc: false,
        );
  }
  ```
  Replace with:
  ```dart
  @freezed
  abstract class GazerSettings with _$GazerSettings {
    const factory GazerSettings({
      required StreamTargetSettings target,
      required QualitySettings quality,
      required AudioSourceChoice audio,
      required bool forceLibuvc,
      required bool debugLogs,
    }) = _GazerSettings;

    /// Deserializes a [GazerSettings] from JSON (round-trip tests only —
    /// [SecureSettingsRepository] persists fields individually, not as one blob).
    factory GazerSettings.fromJson(Map<String, dynamic> json) =>
        _$GazerSettingsFromJson(json);

    /// First-launch defaults: empty target, default quality, auto audio,
    /// developer toggles (force libuvc, debug logs) off.
    factory GazerSettings.defaults() => GazerSettings(
          target: StreamTargetSettings.empty(),
          quality: QualitySettings.defaults(),
          audio: AudioSourceChoice.auto,
          forceLibuvc: false,
          debugLogs: false,
        );
  }
  ```
  Run `make mobile-run CMD="dart run build_runner build --delete-conflicting-outputs"` →
  succeeds (regenerates `gazer_settings.freezed.dart`/`.g.dart` with the new field; the JSON key
  is `debugLogs`, matching the field name — no `@JsonKey` needed, same convention as every other
  field).

- [ ] **Step 6: Fix the one direct constructor call — modify `test/models/gazer_settings_test.dart`**

  Quote the exact existing test (Task 4 Step 9):
  ```dart
    group('GazerSettings.defaults', () {
      test('is an empty target, default quality, auto audio, libuvc off', () {
        final defaults = GazerSettings.defaults();
        expect(defaults.target, StreamTargetSettings.empty());
        expect(defaults.quality, QualitySettings.defaults());
        expect(defaults.audio, AudioSourceChoice.auto);
        expect(defaults.forceLibuvc, isFalse);
      });
    });

    group('GazerSettings JSON round-trip', () {
      test('toJson/fromJson preserves nested target and quality', () {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            streamKey: 'demo-key-0001',
          ),
          quality: const QualitySettings(
            resolution: Resolution.p720,
            frameRate: FrameRate.fps60,
            videoBitrateKbps: 3000,
            adaptiveBitrate: false,
          ),
          audio: AudioSourceChoice.usbAudio,
          forceLibuvc: true,
        );
        final restored = GazerSettings.fromJson(original.toJson());
        expect(restored, original);
      });
    });
  ```
  Replace with:
  ```dart
    group('GazerSettings.defaults', () {
      test('is an empty target, default quality, auto audio, both dev toggles off', () {
        final defaults = GazerSettings.defaults();
        expect(defaults.target, StreamTargetSettings.empty());
        expect(defaults.quality, QualitySettings.defaults());
        expect(defaults.audio, AudioSourceChoice.auto);
        expect(defaults.forceLibuvc, isFalse);
        expect(defaults.debugLogs, isFalse);
      });
    });

    group('GazerSettings JSON round-trip', () {
      test('toJson/fromJson preserves nested target and quality', () {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            streamKey: 'demo-key-0001',
          ),
          quality: const QualitySettings(
            resolution: Resolution.p720,
            frameRate: FrameRate.fps60,
            videoBitrateKbps: 3000,
            adaptiveBitrate: false,
          ),
          audio: AudioSourceChoice.usbAudio,
          forceLibuvc: true,
          debugLogs: true,
        );
        final restored = GazerSettings.fromJson(original.toJson());
        expect(restored, original);
      });
    });
  ```
  Run `make mobile-run CMD="flutter test test/models/gazer_settings_test.dart"` → PASS
  (`00:0X +5: All tests passed!` — unchanged count, existing 5 tests from Task 4 Step 9).

- [ ] **Step 7: Persist `debugLogs` — modify `lib/services/settings_repository.dart`**

  Quote the exact existing constant (Task 7, last of the 10 keys):
  ```dart
      static const String _kDeveloperForceLibuvc = 'gazer.developer.forceLibuvc';
  ```
  Replace with:
  ```dart
      static const String _kDeveloperForceLibuvc = 'gazer.developer.forceLibuvc';
      static const String _kDeveloperDebugLogs = 'gazer.developer.debugLogs';
  ```

  Quote the exact existing tail of `load()`:
  ```dart
        final forceLibuvc = await _prefs.getBool(_kDeveloperForceLibuvc) ?? defaults.forceLibuvc;

        return GazerSettings(
          target: StreamTargetSettings(url: url, streamKey: streamKey, username: username, password: password),
          quality: QualitySettings(
            resolution: resolution,
            frameRate: frameRate,
            videoBitrateKbps: bitrate,
            adaptiveBitrate: adaptive,
          ),
          audio: audio,
          forceLibuvc: forceLibuvc,
        );
      }
  ```
  Replace with:
  ```dart
        final forceLibuvc = await _prefs.getBool(_kDeveloperForceLibuvc) ?? defaults.forceLibuvc;
        final debugLogs = await _prefs.getBool(_kDeveloperDebugLogs) ?? defaults.debugLogs;

        return GazerSettings(
          target: StreamTargetSettings(url: url, streamKey: streamKey, username: username, password: password),
          quality: QualitySettings(
            resolution: resolution,
            frameRate: frameRate,
            videoBitrateKbps: bitrate,
            adaptiveBitrate: adaptive,
          ),
          audio: audio,
          forceLibuvc: forceLibuvc,
          debugLogs: debugLogs,
        );
      }
  ```

  Quote the exact existing tail of `save()`:
  ```dart
        await _prefs.setString(_kAudioSource, s.audio.name);
        await _prefs.setBool(_kDeveloperForceLibuvc, s.forceLibuvc);
      }
  ```
  Replace with:
  ```dart
        await _prefs.setString(_kAudioSource, s.audio.name);
        await _prefs.setBool(_kDeveloperForceLibuvc, s.forceLibuvc);
        await _prefs.setBool(_kDeveloperDebugLogs, s.debugLogs);
      }
  ```

- [ ] **Step 8: Fix the two direct constructor calls — modify `test/services/settings_repository_test.dart`**

  Quote the exact existing round-trip and secrets tests (Task 7 Step 2):
  ```dart
    group('SecureSettingsRepository save/load round trip', () {
      test('preserves target, quality, audio and developer settings', () async {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmps://ingest-b.example.com/app',
            streamKey: 'demo-key-0002',
            username: 'demo',
            password: 's3cret',
          ),
          quality: const QualitySettings(
            resolution: Resolution.p1080,
            frameRate: FrameRate.fps60,
            videoBitrateKbps: 4500,
            adaptiveBitrate: false,
          ),
          audio: AudioSourceChoice.usbAudio,
          forceLibuvc: true,
        );

        await repository.save(original);
        final loaded = await repository.load();

        expect(loaded, original);
      });
    });

    group('secrets never written to prefs', () {
      test('no shared_preferences key contains "target"', () async {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            streamKey: 'demo-key-0001',
            username: 'demo',
            password: 's3cret',
          ),
          quality: QualitySettings.defaults(),
          audio: AudioSourceChoice.auto,
          forceLibuvc: false,
        );
  ```
  Replace with:
  ```dart
    group('SecureSettingsRepository save/load round trip', () {
      test('preserves target, quality, audio and developer settings', () async {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmps://ingest-b.example.com/app',
            streamKey: 'demo-key-0002',
            username: 'demo',
            password: 's3cret',
          ),
          quality: const QualitySettings(
            resolution: Resolution.p1080,
            frameRate: FrameRate.fps60,
            videoBitrateKbps: 4500,
            adaptiveBitrate: false,
          ),
          audio: AudioSourceChoice.usbAudio,
          forceLibuvc: true,
          debugLogs: true,
        );

        await repository.save(original);
        final loaded = await repository.load();

        expect(loaded, original);
      });
    });

    group('secrets never written to prefs', () {
      test('no shared_preferences key contains "target"', () async {
        final original = GazerSettings(
          target: const StreamTargetSettings(
            url: 'rtmp://ingest-a.example.com/live',
            streamKey: 'demo-key-0001',
            username: 'demo',
            password: 's3cret',
          ),
          quality: QualitySettings.defaults(),
          audio: AudioSourceChoice.auto,
          forceLibuvc: false,
          debugLogs: false,
        );
  ```
  Run `make mobile-run CMD="flutter test test/services/settings_repository_test.dart"` → PASS
  (`00:0X +3: All tests passed!` — unchanged count).

- [ ] **Step 9: Fix the one direct constructor call — modify `test/services/pipeline_controller_test.dart`**

  Quote the exact existing helper (Task 11 Step 1):
  ```dart
      GazerSettings settingsWith({String? username, String? password}) => GazerSettings(
            target: StreamTargetSettings(
              url: 'rtmp://ingest-a.example.com/live',
              streamKey: 'demo-key-0001',
              username: username,
              password: password,
            ),
            quality: QualitySettings.defaults(),
            audio: AudioSourceChoice.auto,
            forceLibuvc: false,
          );
  ```
  Replace with:
  ```dart
      GazerSettings settingsWith({String? username, String? password}) => GazerSettings(
            target: StreamTargetSettings(
              url: 'rtmp://ingest-a.example.com/live',
              streamKey: 'demo-key-0001',
              username: username,
              password: password,
            ),
            quality: QualitySettings.defaults(),
            audio: AudioSourceChoice.auto,
            forceLibuvc: false,
            debugLogs: false,
          );
  ```
  Run `make mobile-run CMD="flutter test test/services/pipeline_controller_test.dart"` → PASS
  (`00:0X +10: All tests passed!` — unchanged count, Task 11 Step 9's baseline).

- [ ] **Step 10: Wire `GazerLog.verbose` — modify `lib/providers/settings_provider.dart`**

  Quote the exact existing `SettingsNotifier` (Task 12 Step 3):
  ```dart
    @Riverpod(keepAlive: true)
    class SettingsNotifier extends _$SettingsNotifier {
      @override
      Future<GazerSettings> build() => ref.watch(settingsRepositoryProvider).load();

      /// Persists [s] via the repository and updates provider state so every
      /// listener (HomeScreen enablement, StatusPanel) sees the new settings.
      Future<void> update(GazerSettings s) async {
        await ref.read(settingsRepositoryProvider).save(s);
        state = AsyncData(s);
      }
    }
  ```
  Replace with:
  ```dart
    @Riverpod(keepAlive: true)
    class SettingsNotifier extends _$SettingsNotifier {
      @override
      Future<GazerSettings> build() async {
        final GazerSettings settings = await ref.watch(settingsRepositoryProvider).load();
        GazerLog.verbose = settings.debugLogs;
        return settings;
      }

      /// Persists [s] via the repository and updates provider state so every
      /// listener (HomeScreen enablement, StatusPanel) sees the new settings.
      /// Also re-applies [GazerLog.verbose] so toggling Settings > Developer
      /// > Debug logs takes effect immediately, without an app restart.
      Future<void> update(GazerSettings s) async {
        await ref.read(settingsRepositoryProvider).save(s);
        GazerLog.verbose = s.debugLogs;
        state = AsyncData(s);
      }
    }
  ```

  Add the `gazer_log.dart` import — quote the exact existing import block:
  ```dart
  import 'package:flutter_secure_storage/flutter_secure_storage.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../models/gazer_settings.dart';
  import '../services/settings_repository.dart';

  part 'settings_provider.g.dart';
  ```
  Replace with:
  ```dart
  import 'package:flutter_secure_storage/flutter_secure_storage.dart';
  import 'package:riverpod_annotation/riverpod_annotation.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import '../models/gazer_settings.dart';
  import '../services/gazer_log.dart';
  import '../services/settings_repository.dart';

  part 'settings_provider.g.dart';
  ```

  Run `make mobile-run CMD="flutter test test/providers/settings_provider_test.dart"` → PASS
  (unchanged — existing tests assert on `GazerSettings`/persistence, not on `GazerLog.verbose`).

- [ ] **Step 11: Add the 2nd Developer switch — modify `lib/screens/settings_screen.dart`**

  Quote the exact existing Developer section (Task 15 Step 7):
  ```dart
              if (_devUnlocked) ...<Widget>[
                Text(l10n.developerSectionTitle, style: Theme.of(context).textTheme.titleMedium),
                SwitchListTile(
                  title: Text(l10n.forceLibuvcLabel),
                  value: draft.forceLibuvc,
                  onChanged: (bool v) => _update((GazerSettings s) => s.copyWith(forceLibuvc: v)),
                ),
              ],
  ```
  Replace with:
  ```dart
              if (_devUnlocked) ...<Widget>[
                Text(l10n.developerSectionTitle, style: Theme.of(context).textTheme.titleMedium),
                SwitchListTile(
                  title: Text(l10n.forceLibuvcLabel),
                  value: draft.forceLibuvc,
                  onChanged: (bool v) => _update((GazerSettings s) => s.copyWith(forceLibuvc: v)),
                ),
                SwitchListTile(
                  key: const Key('debugLogsSwitch'),
                  title: Text(l10n.settingsDebugLogsLabel),
                  value: draft.debugLogs,
                  onChanged: (bool v) => _update((GazerSettings s) => s.copyWith(debugLogs: v)),
                ),
              ],
  ```

- [ ] **Step 12: Add 1 l10n key — modify `lib/l10n/app_en.arb`**

  Quote the exact existing tail (as left by this part's Task 22 Step 7 — the file already gained
  4 permission keys before this task runs):
  ```json
    "permissionPermanentlyDeniedMessage": "Camera or microphone permission was permanently denied.",
    "permissionOpenSettingsLabel": "Open settings"
  }
  ```
  Replace with:
  ```json
    "permissionPermanentlyDeniedMessage": "Camera or microphone permission was permanently denied.",
    "permissionOpenSettingsLabel": "Open settings",
    "settingsDebugLogsLabel": "Debug logs"
  }
  ```
  Run `make mobile-codegen` → succeeds.

- [ ] **Step 13: Add 1 widget test — modify `test/screens/settings_screen_test.dart`**

  Quote the exact existing last test to anchor the insertion:
  ```dart
    testWidgets('secrets are obscured by default', (WidgetTester tester) async {
      await pumpSettings(tester);
      final TextFormField keyField = tester.widget<TextFormField>(find.widgetWithText(TextFormField, 'Stream Key'));
      final TextFormField pwField = tester.widget<TextFormField>(find.widgetWithText(TextFormField, 'Password'));
      expect(keyField.obscureText, isTrue);
      expect(pwField.obscureText, isTrue);
    });
  }
  ```
  Replace with:
  ```dart
    testWidgets('secrets are obscured by default', (WidgetTester tester) async {
      await pumpSettings(tester);
      final TextFormField keyField = tester.widget<TextFormField>(find.widgetWithText(TextFormField, 'Stream Key'));
      final TextFormField pwField = tester.widget<TextFormField>(find.widgetWithText(TextFormField, 'Password'));
      expect(keyField.obscureText, isTrue);
      expect(pwField.obscureText, isTrue);
    });

    testWidgets('debug logs switch is hidden until the version footer is long-pressed, then saves',
        (WidgetTester tester) async {
      await pumpSettings(tester);
      expect(find.byKey(const Key('debugLogsSwitch')), findsNothing);

      await tester.longPress(find.byType(FutureBuilder<PackageInfo>));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('debugLogsSwitch')), findsOneWidget);

      await tester.tap(find.byKey(const Key('debugLogsSwitch')));
      await tester.enterText(find.widgetWithText(TextFormField, 'RTMP URL'), 'rtmp://example.com/live/mystream');
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(settingsRepo.saved, isNotEmpty);
      expect(settingsRepo.saved.last.debugLogs, isTrue);
    });
  }
  ```

  Add the `package_info_plus` import needed for `FutureBuilder<PackageInfo>` — quote the exact
  existing import block:
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/providers/connectivity_provider.dart';
  import 'package:gazer/providers/devices_provider.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/providers/settings_provider.dart';
  import 'package:gazer/providers/update_provider.dart';

  import '../helpers/fake_host_api.dart';
  import '../helpers/fakes.dart';
  import '../helpers/pump_app.dart';
  ```
  Replace with:
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/license_state.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/providers/connectivity_provider.dart';
  import 'package:gazer/providers/devices_provider.dart';
  import 'package:gazer/providers/license_provider.dart';
  import 'package:gazer/providers/pipeline_provider.dart';
  import 'package:gazer/providers/settings_provider.dart';
  import 'package:gazer/providers/update_provider.dart';
  import 'package:package_info_plus/package_info_plus.dart';

  import '../helpers/fake_host_api.dart';
  import '../helpers/fakes.dart';
  import '../helpers/pump_app.dart';
  ```

- [ ] **Step 14: Run and confirm PASS**

  `make mobile-run CMD="flutter test test/screens/settings_screen_test.dart"`
  Expected PASS: `00:0X +6: All tests passed!` (5 pre-existing + 1 new).

- [ ] **Step 15: Log the license fetch outcome (masked) — modify `lib/services/license_client.dart`**

  Quote the exact existing `validateAndFetchFlags()`:
  ```dart
      Future<LicenseState> validateAndFetchFlags() async {
        final deviceId = await _deviceIdProvider.deviceId();
        final cached = await _cache.read();
        try {
          await _dio.post('$baseUrl/validate', data: _payload(deviceId));
          final response = await _dio.post('$baseUrl/features', data: _payload(deviceId));
          final rawFlags = Map<String, dynamic>.from(
            (response.data as Map<String, dynamic>)['features'] as Map,
          );
          final flags = rawFlags.map((key, value) => MapEntry(key, value as bool));
          final state = LicenseState(
            status: LicenseStatus.valid,
            flags: flags,
            lastFetched: _now(),
            deviceId: deviceId,
          );
          await _cache.write(state);
          return state;
        } on DioException catch (e) {
          final statusCode = e.response?.statusCode;
          if (statusCode != null && statusCode >= 400 && statusCode < 500) {
            final invalid = LicenseState(
              status: LicenseStatus.invalid,
              flags: cached?.flags ?? const {},
              lastFetched: cached?.lastFetched,
              deviceId: deviceId,
            );
            await _cache.write(invalid);
            return invalid;
          }
          return _offlineFallback(cached, deviceId);
        } catch (_) {
          return _offlineFallback(cached, deviceId);
        }
      }
  ```
  Replace with:
  ```dart
      Future<LicenseState> validateAndFetchFlags() async {
        final deviceId = await _deviceIdProvider.deviceId();
        final cached = await _cache.read();
        try {
          await _dio.post('$baseUrl/validate', data: _payload(deviceId));
          final response = await _dio.post('$baseUrl/features', data: _payload(deviceId));
          final rawFlags = Map<String, dynamic>.from(
            (response.data as Map<String, dynamic>)['features'] as Map,
          );
          final flags = rawFlags.map((key, value) => MapEntry(key, value as bool));
          final state = LicenseState(
            status: LicenseStatus.valid,
            flags: flags,
            lastFetched: _now(),
            deviceId: deviceId,
          );
          await _cache.write(state);
          _logFetchOutcome(state, deviceId);
          return state;
        } on DioException catch (e) {
          final statusCode = e.response?.statusCode;
          if (statusCode != null && statusCode >= 400 && statusCode < 500) {
            final invalid = LicenseState(
              status: LicenseStatus.invalid,
              flags: cached?.flags ?? const {},
              lastFetched: cached?.lastFetched,
              deviceId: deviceId,
            );
            await _cache.write(invalid);
            _logFetchOutcome(invalid, deviceId);
            return invalid;
          }
          return _offlineFallback(cached, deviceId);
        } catch (_) {
          return _offlineFallback(cached, deviceId);
        }
      }

      /// Logs the fetch outcome (status, flag count) — never the device id
      /// in full; [GazerLog.maskSecret] shows only its last 4 characters.
      void _logFetchOutcome(LicenseState state, String deviceId) {
        GazerLog.info('license.fetch', <String, Object?>{
          'status': state.status.name,
          'flagCount': state.flags.length,
          'deviceId': GazerLog.maskSecret(deviceId),
        });
      }
  ```

  Quote the exact existing `_offlineFallback`:
  ```dart
      LicenseState _offlineFallback(LicenseState? cached, String deviceId) {
        if (cached?.lastFetched != null && _now().difference(cached!.lastFetched!) <= kLicenseGracePeriod) {
          return cached.copyWith(status: LicenseStatus.gracePeriod);
        }
        return LicenseState(
          status: LicenseStatus.unknown,
          flags: cached?.flags ?? const {},
          lastFetched: cached?.lastFetched,
          deviceId: deviceId,
        );
      }
  ```
  Replace with:
  ```dart
      LicenseState _offlineFallback(LicenseState? cached, String deviceId) {
        final LicenseState state;
        if (cached?.lastFetched != null && _now().difference(cached!.lastFetched!) <= kLicenseGracePeriod) {
          state = cached.copyWith(status: LicenseStatus.gracePeriod);
        } else {
          state = LicenseState(
            status: LicenseStatus.unknown,
            flags: cached?.flags ?? const {},
            lastFetched: cached?.lastFetched,
            deviceId: deviceId,
          );
        }
        _logFetchOutcome(state, deviceId);
        return state;
      }
  ```

  Add the `gazer_log.dart` import — quote the exact existing import block:
  ```dart
    import 'package:dio/dio.dart';
    import 'package:shared_preferences/shared_preferences.dart';

    import '../config/constants.dart';
    import '../models/license_state.dart';
    import 'device_id.dart';
  ```
  Replace with:
  ```dart
    import 'package:dio/dio.dart';
    import 'package:shared_preferences/shared_preferences.dart';

    import '../config/constants.dart';
    import '../models/license_state.dart';
    import 'device_id.dart';
    import 'gazer_log.dart';
  ```

  Run `make mobile-run CMD="flutter test test/services/license_client_test.dart"` → PASS
  (unchanged — existing tests assert on the returned `LicenseState`, not on log output).

- [ ] **Step 16: Log pipeline state/reconnect/goLive — modify `lib/services/pipeline_controller.dart`**

  Quote the exact existing import block (Task 11):
  ```dart
    import 'dart:async';

    import '../config/flag_keys.dart';
    import '../models/gazer_settings.dart';
    import '../models/pipeline_state.dart';
    import '../models/stream_stats.dart';
    import '../models/validation_issue.dart';
    import '../pigeon/pipeline.g.dart';
    import 'feature_flags.dart';
    import 'native_event_bridge.dart';
    import 'reconnect_policy.dart';
    import 'target_validator.dart';
  ```
  Replace with:
  ```dart
    import 'dart:async';

    import '../config/flag_keys.dart';
    import '../models/gazer_settings.dart';
    import '../models/pipeline_state.dart';
    import '../models/stream_stats.dart';
    import '../models/validation_issue.dart';
    import '../pigeon/pipeline.g.dart';
    import 'feature_flags.dart';
    import 'gazer_log.dart';
    import 'native_event_bridge.dart';
    import 'reconnect_policy.dart';
    import 'target_validator.dart';
  ```

  Quote the exact existing tail of `goLive`:
  ```dart
        final sendCredentials = flags.isEnabled(FlagKeys.rtmpAuth);
        _pendingTarget = StreamTarget()
          ..url = TargetValidator.effectiveUrl(settings.target)
          ..username = sendCredentials ? settings.target.username : null
          ..password = sendCredentials ? settings.target.password : null;

        _emit(const PreparingState());
        await _host.prepare(config);
        _emit(const ReadyState());
        _emit(const ConnectingState());
        await _host.start(_pendingTarget!);
      }
  ```
  Replace with:
  ```dart
        final sendCredentials = flags.isEnabled(FlagKeys.rtmpAuth);
        _pendingTarget = StreamTarget()
          ..url = TargetValidator.effectiveUrl(settings.target)
          ..username = sendCredentials ? settings.target.username : null
          ..password = sendCredentials ? settings.target.password : null;

        GazerLog.info('pipeline.goLive', <String, Object?>{
          'host': Uri.tryParse(_pendingTarget!.url)?.host ?? '',
        });

        _emit(const PreparingState());
        await _host.prepare(config);
        _emit(const ReadyState());
        _emit(const ConnectingState());
        await _host.start(_pendingTarget!);
      }
  ```

  Quote the exact existing `_handleError`:
  ```dart
      void _handleError(GazerErrorCode code, String? detail) {
        if (_cancelled) {
          _emit(const IdleState());
          return;
        }
        if (_policy.shouldRetry(code)) {
          _reconnectAttempt += 1;
          final delay = _policy.delayFor(_reconnectAttempt);
          if (delay == null) {
            _emit(ErrorState(GazerError(code: code, detail: detail)));
            return;
          }
          _statsSnapshot = _statsSnapshot.copyWith(reconnectCount: _statsSnapshot.reconnectCount + 1);
          _statsController.add(_statsSnapshot);
          _emit(ReconnectingState(_reconnectAttempt, delay));
          unawaited(_retryAfter(delay));
        } else {
          _emit(ErrorState(GazerError(code: code, detail: detail)));
        }
      }
  ```
  Replace with:
  ```dart
      void _handleError(GazerErrorCode code, String? detail) {
        if (_cancelled) {
          _emit(const IdleState());
          return;
        }
        if (_policy.shouldRetry(code)) {
          _reconnectAttempt += 1;
          final delay = _policy.delayFor(_reconnectAttempt);
          if (delay == null) {
            _emit(ErrorState(GazerError(code: code, detail: detail)));
            return;
          }
          _statsSnapshot = _statsSnapshot.copyWith(reconnectCount: _statsSnapshot.reconnectCount + 1);
          _statsController.add(_statsSnapshot);
          GazerLog.info('pipeline.reconnect', <String, Object?>{
            'attempt': _reconnectAttempt,
            'delayMs': delay.inMilliseconds,
          });
          _emit(ReconnectingState(_reconnectAttempt, delay));
          unawaited(_retryAfter(delay));
        } else {
          _emit(ErrorState(GazerError(code: code, detail: detail)));
        }
      }
  ```

  Quote the exact existing `_emit`:
  ```dart
      void _emit(PipelineState next) {
        _current = next;
        _stateController.add(next);
      }
  ```
  Replace with:
  ```dart
      void _emit(PipelineState next) {
        GazerLog.debug('pipeline.state', <String, Object?>{
          'from': _current.runtimeType.toString(),
          'to': next.runtimeType.toString(),
          if (next is ErrorState) 'errorCode': next.error.code.name,
        });
        _current = next;
        _stateController.add(next);
      }
  ```

  Run `make mobile-run CMD="flutter test test/services/pipeline_controller_test.dart"` → PASS
  (`00:0X +10: All tests passed!` — same count as Step 9 above; existing tests assert on emitted
  `PipelineState`/`StreamStats`, not on log output).

- [ ] **Step 17: Regression-check the whole Dart suite**

  `make mobile-test` → PASS: every suite from Tasks 4–24 green together, coverage gate ≥90%.

- [ ] **Step 18: Lint**

  `make mobile-lint` → `No issues found!`

- [ ] **Step 19: Commit**

  ```bash
  git add mobile/gazer/lib/services/gazer_log.dart mobile/gazer/test/services/gazer_log_test.dart \
          mobile/gazer/lib/models/gazer_settings.dart mobile/gazer/test/models/gazer_settings_test.dart \
          mobile/gazer/lib/services/settings_repository.dart mobile/gazer/test/services/settings_repository_test.dart \
          mobile/gazer/test/services/pipeline_controller_test.dart mobile/gazer/lib/providers/settings_provider.dart \
          mobile/gazer/lib/screens/settings_screen.dart mobile/gazer/test/screens/settings_screen_test.dart \
          mobile/gazer/lib/l10n/app_en.arb mobile/gazer/lib/l10n/app_localizations.dart \
          mobile/gazer/lib/l10n/app_localizations_en.dart mobile/gazer/lib/services/license_client.dart \
          mobile/gazer/lib/services/pipeline_controller.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): sanitized structured logging + debug-log toggle

  GazerLog emits one JSON line per call via dart:developer's log(),
  masking password/streamKey/username wholesale and a url's last path
  segment. debug() only emits when GazerSettings.debugLogs is on (new
  Settings > Developer > Debug logs switch). PipelineController logs
  state transitions and reconnect attempts at debug/info; LicenseClient
  logs fetch outcome (status, flag count, masked device id); goLive
  logs the target host only — never the full URL, key, or credentials.

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

---

Continues into Task 26 (final M1 verification), unchanged by this part except that its full-suite
`make mobile-test`/`make mobile-lint` gates now also cover Tasks 22–24.


### Task 25: Release signing

**Files:**
- Modify: `mobile/gazer/android/app/build.gradle.kts` (signing configs; Task 2 Step 10 `android {}` / `buildTypes {}`)
- Modify: `.gitignore` (repo root; Task 2 Step 12 addition)
- Modify: `.github/workflows/gazer-mobile.yml` (`build` and `release` jobs; Task 3 Step 2)
- Modify: `Makefile` (repo root; adds `mobile-build-signed`, Task 1 Step 8 `.PHONY` + `mobile-build`)
- Modify: `docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1.md` (Task 26 Step 13 checklist — one line)
- Test: none new (Gradle unit test not appropriate for signing config — verified via the shell-level checks in Step 8 below)
- Human procedure (one-time, run once): generate the upload keystore, upload 4 secrets to `penguintechinc/waddlebot`

**Interfaces:**
- Consumes: `mobile/gazer/android/app/build.gradle.kts` and `mobile/gazer/android/gradle.properties` (Task 2), `.github/workflows/gazer-mobile.yml` `build`/`release` jobs (Task 3), `Makefile` `mobile-build` target (Task 1). Runs after Task 21 (integration test / CI emulator job) and before Task 26 (M1 verification) — Task 26 Step 13's `make mobile-build` gate now additionally implies the signing warning/require-signing behavior below, and its checklist gains one line confirming release APKs are upload-key-signed, not debug-signed.
- Produces: `signingConfigs.create("upload")` read from a gitignored `mobile/gazer/android/key.properties`; `GAZER_REQUIRE_SIGNING` env var enforced in `buildTypes.release`; four new CI secrets (`ANDROID_UPLOAD_KEY_STORE_B64`, `ANDROID_UPLOAD_KEY_STORE_PASSWORD`, `ANDROID_UPLOAD_KEY_ALIAS`, `ANDROID_UPLOAD_KEY_ALIAS_PASSWORD`); `make mobile-build-signed`; an `apksigner`-based signature-verification step in both the `build` and `release` CI jobs.

**Deviation from the spec's literal secret name, noted here (same pattern as the GazerErrorCode forward-reference note in Part B):** the spec's Signing section names the secret `ANDROID_UPLOAD_KEY_STORE`. That value is a binary `.jks` file and GitHub Actions secrets are text — this task stores it base64-encoded as `ANDROID_UPLOAD_KEY_STORE_B64` and decodes it in CI (Step 5 below). The other three secret names match the spec exactly.

- [ ] **Step 1: Confirm no signing config exists yet (failing check)**

Run: `grep -c 'signingConfigs.create' mobile/gazer/android/app/build.gradle.kts`
Expected: `0` (Task 2's `buildTypes { release { signingConfig = signingConfigs.getByName("debug") } }` is still in place, unconditionally debug-signed).

- [ ] **Step 2: Modify `android/app/build.gradle.kts` — load `key.properties`, add the `upload` signing config, gate on `GAZER_REQUIRE_SIGNING`**

Anchor (Task 2 Step 10's exact current `android {` header through `buildTypes {}`, to be replaced):
```kotlin
android {
    namespace = "io.waddlebot.gazer"
    compileSdk = 36
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "io.waddlebot.gazer"
        minSdk = 29
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
        debug {
            enableUnitTestCoverage = true
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}
```

Replace with (new `import` line goes above the existing `plugins { ... }` block at the top of the file; `keyPropsFile`/`keyProps` go directly above `android {`):

```kotlin
import java.util.Properties

// Release signing. mobile/gazer/android/key.properties is never committed (see .gitignore) --
// it is either written by a developer for a local signed build (Step 8c below) or by CI from
// the ANDROID_UPLOAD_KEY_STORE_B64/ANDROID_UPLOAD_KEY_STORE_PASSWORD/ANDROID_UPLOAD_KEY_ALIAS/
// ANDROID_UPLOAD_KEY_ALIAS_PASSWORD secrets (see .github/workflows/gazer-mobile.yml `build` job)
// and deleted again in an `if: always()` step immediately after the build. storeFile is
// resolved with rootProject.file(...) because key.properties lives at android/key.properties
// (the Gradle root project for this module), not android/app/.
val keyPropsFile = rootProject.file("key.properties")
val keyProps = Properties()
if (keyPropsFile.exists()) {
    keyPropsFile.inputStream().use { keyProps.load(it) }
}

android {
    namespace = "io.waddlebot.gazer"
    compileSdk = 36
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "io.waddlebot.gazer"
        minSdk = 29
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (keyPropsFile.exists()) {
            create("upload") {
                storeFile = rootProject.file(keyProps.getProperty("storeFile"))
                storePassword = keyProps.getProperty("storePassword")
                keyAlias = keyProps.getProperty("keyAlias")
                keyPassword = keyProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Tag builds (gazer-v*) must never ship debug-signed -- fail closed before any
            // signingConfig decision below. See .github/workflows/gazer-mobile.yml `build` job,
            // which sets GAZER_REQUIRE_SIGNING=1 only when github.ref starts with refs/tags/gazer-v.
            if (System.getenv("GAZER_REQUIRE_SIGNING") == "1" && !keyPropsFile.exists()) {
                throw GradleException("GAZER_REQUIRE_SIGNING=1 but key.properties is missing")
            }
            if (keyPropsFile.exists()) {
                signingConfig = signingConfigs.getByName("upload")
            } else {
                signingConfig = signingConfigs.getByName("debug")
                // Single, unmistakable line -- Step 8a below asserts this appears exactly once.
                println("WARNING: release build is debug-signed (no key.properties)")
            }
        }
        debug {
            enableUnitTestCoverage = true
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}
```

Full resulting `mobile/gazer/android/app/build.gradle.kts` (everything below the anchor — `flutter {}` through the end — is untouched, verbatim from Task 2 Step 10):

```kotlin
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
    id("org.jlleitschuh.gradle.ktlint")
    jacoco
}

// If AGP 9.1.0 / Kotlin 2.4.0 rejects the `kotlinOptions {}` block below
// (renamed/removed in that exact combination), replace it with whatever
// DSL that release's migration notes specify (e.g.
// `kotlin { compilerOptions { jvmTarget.set(...) } }`) and record the
// change in this comment -- do not downgrade AGP/Kotlin to dodge it.

// Release signing. mobile/gazer/android/key.properties is never committed (see .gitignore) --
// it is either written by a developer for a local signed build (Task 25 Step 8c) or by CI from
// the ANDROID_UPLOAD_KEY_STORE_B64/ANDROID_UPLOAD_KEY_STORE_PASSWORD/ANDROID_UPLOAD_KEY_ALIAS/
// ANDROID_UPLOAD_KEY_ALIAS_PASSWORD secrets (see .github/workflows/gazer-mobile.yml `build` job)
// and deleted again in an `if: always()` step immediately after the build. storeFile is
// resolved with rootProject.file(...) because key.properties lives at android/key.properties
// (the Gradle root project for this module), not android/app/.
val keyPropsFile = rootProject.file("key.properties")
val keyProps = Properties()
if (keyPropsFile.exists()) {
    keyPropsFile.inputStream().use { keyProps.load(it) }
}

android {
    namespace = "io.waddlebot.gazer"
    compileSdk = 36
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "io.waddlebot.gazer"
        minSdk = 29
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (keyPropsFile.exists()) {
            create("upload") {
                storeFile = rootProject.file(keyProps.getProperty("storeFile"))
                storePassword = keyProps.getProperty("storePassword")
                keyAlias = keyProps.getProperty("keyAlias")
                keyPassword = keyProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Tag builds (gazer-v*) must never ship debug-signed -- fail closed before any
            // signingConfig decision below. See .github/workflows/gazer-mobile.yml `build` job,
            // which sets GAZER_REQUIRE_SIGNING=1 only when github.ref starts with refs/tags/gazer-v.
            if (System.getenv("GAZER_REQUIRE_SIGNING") == "1" && !keyPropsFile.exists()) {
                throw GradleException("GAZER_REQUIRE_SIGNING=1 but key.properties is missing")
            }
            if (keyPropsFile.exists()) {
                signingConfig = signingConfigs.getByName("upload")
            } else {
                signingConfig = signingConfigs.getByName("debug")
                // Single, unmistakable line -- Step 8a below asserts this appears exactly once.
                println("WARNING: release build is debug-signed (no key.properties)")
            }
        }
        debug {
            enableUnitTestCoverage = true
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}

flutter {
    source = "../.."
}

jacoco {
    toolVersion = libs.versions.jacoco.get()
}

dependencies {
    implementation(libs.rootencoder.library)
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
    testImplementation(libs.mockk)

    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.junit4)
}

tasks.withType<Test> {
    useJUnitPlatform()
}

// NOTE: android/build.gradle.kts (Step 9 above) redirects the *root* buildDir to
// mobile/gazer/build, so this module's normal Gradle outputs (compiled classes, .exec/.ec
// coverage data) land under mobile/gazer/build/app, not android/app/build. The JaCoCo XML/HTML
// *report* output below is deliberately pinned to `layout.projectDirectory` (NOT
// `layout.buildDirectory`, which is the redirected one) so it lands at the fixed, predictable
// path `android/app/build/reports/jacoco/jacocoTestReport/...` that `make mobile-test-android`
// (repo-root Makefile), `scripts/coverage_gate.sh`'s jacoco-mode default, the CI `android-unit`
// job (Task 3), and Task 17 Step 7's existence check all read from -- every one of those must
// keep agreeing with this exact path if it is ever changed here.
tasks.register<JacocoReport>("jacocoTestReport") {
    dependsOn("testDebugUnitTest")
    reports {
        xml.required.set(true)
        xml.outputLocation.set(layout.projectDirectory.file("build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml"))
        html.required.set(true)
        html.outputLocation.set(layout.projectDirectory.dir("build/reports/jacoco/jacocoTestReport/html"))
    }
    val fileFilter = listOf(
        "**/R.class", "**/R\$*.class", "**/BuildConfig.*", "**/Manifest*.*",
        "**/*Test*.*", "**/pigeon/**",
    )
    val debugTree = fileTree("${layout.buildDirectory.get()}/tmp/kotlin-classes/debug") {
        exclude(fileFilter)
    }
    val mainSrc = "${project.projectDir}/src/main/kotlin"
    sourceDirectories.setFrom(files(mainSrc))
    classDirectories.setFrom(files(debugTree))
    executionData.setFrom(fileTree(layout.buildDirectory.get()) {
        include("**/*.exec", "**/*.ec")
    })
}
```

Run: `grep -c 'signingConfigs.create("upload")' mobile/gazer/android/app/build.gradle.kts`
Expected: `1`

- [ ] **Step 3: Modify `.gitignore` (repo root) — never commit the keystore or key.properties**

Anchor (Task 2 Step 12's exact addition):
```gitignore

# Gazer Mobile 2.0 (mobile/gazer) -- build/ and **/.gradle/ above already
# cover this app's build output and Gradle caches at any depth.
mobile/gazer/.dart_tool/
mobile/gazer/coverage/
mobile/gazer/android/local.properties
```
Append immediately after it:
```gitignore
mobile/gazer/android/key.properties
mobile/gazer/android/*.jks
```
Run: `grep -c 'mobile/gazer/android/key.properties' .gitignore && grep -c 'mobile/gazer/android/\*.jks' .gitignore`
Expected: `1` and `1`.

- [ ] **Step 4: One-time human-in-the-loop procedure — generate the upload keystore and upload CI secrets**

**Human-in-the-loop, run once. Do this with the user present; never run `keytool -genkeypair` unattended with a scripted password.**

Explain first: this generates the **upload key** only. Google Play App Signing means Google holds
the real **app signing key** and re-signs the app for distribution; the upload key here is only
what this pipeline uses to prove uploads come from PenguinTech to Google Play's ingestion — it is
never the key end users' devices verify against. Losing or rotating the upload key is recoverable
(Play Console upload-key-reset flow); losing the app signing key would not be, but that key never
exists on disk here at all.

```bash
set -euo pipefail
SCRATCH=$(mktemp -d)
cd "${SCRATCH}"

# Password entered interactively at the two keytool prompts -- never pass -storepass/-keypass
# on the command line (shell history + process list exposure).
keytool -genkeypair -v \
  -keystore upload-keystore.jks \
  -alias upload \
  -keyalg RSA -keysize 4096 -validity 10000

base64 -w0 upload-keystore.jks > upload-keystore.b64
printf '%s' "<store password entered above>" > pw.txt   # human types the real value into the file with an editor, not this placeholder
printf '%s' "upload" > alias.txt
printf '%s' "<key password entered above>" > pw2.txt

gh secret set ANDROID_UPLOAD_KEY_STORE_B64 --repo penguintechinc/waddlebot < upload-keystore.b64
gh secret set ANDROID_UPLOAD_KEY_STORE_PASSWORD --repo penguintechinc/waddlebot < pw.txt
gh secret set ANDROID_UPLOAD_KEY_ALIAS --repo penguintechinc/waddlebot < alias.txt
gh secret set ANDROID_UPLOAD_KEY_ALIAS_PASSWORD --repo penguintechinc/waddlebot < pw2.txt

# Record only the fingerprint (not secret) for the release notes.
keytool -list -v -keystore upload-keystore.jks -alias upload | tee fingerprint.txt

shred -u upload-keystore.jks upload-keystore.b64 pw.txt pw2.txt alias.txt
cd -
FINGERPRINT_LINE=$(grep 'SHA256:' "${SCRATCH}/fingerprint.txt" || :)   # grep exits 1 on no match; emptiness is rejected on the next line
echo "Record this line in docs/superpowers/plans/ release notes (not secret): ${FINGERPRINT_LINE}"
rm -rf "${SCRATCH}"
```
Expected: four `gh secret set` commands each print `Set secret ANDROID_UPLOAD_KEY_...` for
`penguintechinc/waddlebot`; the scratch dir no longer exists after the final `rm -rf`; only the
`SHA256:` fingerprint line (never the passwords, never the keystore) gets recorded in the plan's
release notes.

- [ ] **Step 5: Modify `.github/workflows/gazer-mobile.yml` `build` job — decode the keystore, gate signing, verify, then clean up**

Anchor (Task 3 Step 2's exact `build` job steps, to be replaced):
```yaml
  build:
    name: Build APK + AAB
    needs: toolchain
    runs-on: ubuntu-latest
    permissions:
      contents: read
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: flutter pub get
        working-directory: mobile/gazer
        run: flutter pub get

      - name: flutter build apk --split-per-abi
        working-directory: mobile/gazer
        run: flutter build apk --split-per-abi --obfuscate --split-debug-info=build/symbols

      - name: flutter build appbundle
        working-directory: mobile/gazer
        run: flutter build appbundle --obfuscate --split-debug-info=build/symbols

      - name: Upload APKs
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-apk
          path: mobile/gazer/build/app/outputs/apk/**/*.apk
          retention-days: 30

      - name: Upload AAB
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-aab
          path: mobile/gazer/build/app/outputs/bundle/**/*.aab
          retention-days: 30
```

Replace with:
```yaml
  build:
    name: Build APK + AAB
    needs: toolchain
    runs-on: ubuntu-latest
    permissions:
      contents: read
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: flutter pub get
        working-directory: mobile/gazer
        run: flutter pub get

      # Never inline ${{ secrets.* }} inside `run:` (zizmor template-injection rule) -- every
      # secret value crosses into the shell only via `env:`.
      - name: Decode upload keystore and write key.properties
        if: ${{ secrets.ANDROID_UPLOAD_KEY_STORE_B64 != '' }}
        working-directory: mobile/gazer/android
        env:
          KEYSTORE_B64: ${{ secrets.ANDROID_UPLOAD_KEY_STORE_B64 }}
          KEY_STORE_PASSWORD: ${{ secrets.ANDROID_UPLOAD_KEY_STORE_PASSWORD }}
          KEY_ALIAS: ${{ secrets.ANDROID_UPLOAD_KEY_ALIAS }}
          KEY_ALIAS_PASSWORD: ${{ secrets.ANDROID_UPLOAD_KEY_ALIAS_PASSWORD }}
        run: |
          set -euo pipefail
          echo "${KEYSTORE_B64}" | base64 -d > upload-keystore.jks
          cat > key.properties <<KEYPROPS_EOF
          storeFile=upload-keystore.jks
          storePassword=${KEY_STORE_PASSWORD}
          keyAlias=${KEY_ALIAS}
          keyPassword=${KEY_ALIAS_PASSWORD}
          KEYPROPS_EOF

      - name: flutter build apk --split-per-abi
        working-directory: mobile/gazer
        env:
          GAZER_REQUIRE_SIGNING: ${{ startsWith(github.ref, 'refs/tags/gazer-v') && '1' || '0' }}
        run: flutter build apk --split-per-abi --obfuscate --split-debug-info=build/symbols

      - name: flutter build appbundle
        working-directory: mobile/gazer
        env:
          GAZER_REQUIRE_SIGNING: ${{ startsWith(github.ref, 'refs/tags/gazer-v') && '1' || '0' }}
        run: flutter build appbundle --obfuscate --split-debug-info=build/symbols

      # apksigner ships in the pinned build-tools;36.0.0 package (Task 1 Dockerfile) at
      # $ANDROID_SDK_ROOT/build-tools/36.0.0/apksigner (= /opt/android-sdk/build-tools/36.0.0/
      # apksigner in this image; also already on PATH per Task 1's ENV PATH line).
      - name: Verify APK is signed with exactly one certificate
        working-directory: mobile/gazer
        run: |
          set -euo pipefail
          APKSIGNER="${ANDROID_SDK_ROOT}/build-tools/36.0.0/apksigner"
          COUNT=$("${APKSIGNER}" verify --print-certs build/app/outputs/flutter-apk/app-arm64-v8a-release.apk | grep -c 'Signer #1 certificate SHA-256')
          echo "signer count: ${COUNT}"
          test "${COUNT}" -eq 1

      - name: Upload APKs
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-apk
          path: mobile/gazer/build/app/outputs/apk/**/*.apk
          retention-days: 30

      - name: Upload AAB
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a  # v7
        with:
          name: gazer-aab
          path: mobile/gazer/build/app/outputs/bundle/**/*.aab
          retention-days: 30

      - name: Remove keystore and key.properties
        if: always()
        working-directory: mobile/gazer/android
        run: |
          set -euo pipefail
          rm -f upload-keystore.jks key.properties
```
Note: `GAZER_REQUIRE_SIGNING` is set on both `flutter build` steps, not one — each is a separate
`flutter`/Gradle process, and the env var must be visible to whichever one evaluates
`buildTypes.release` in `android/app/build.gradle.kts`.

Run: `grep -c 'ANDROID_UPLOAD_KEY_STORE_B64' .github/workflows/gazer-mobile.yml`
Expected: `1` (appears once, inside `env:`, never inside a `run:` string).

- [ ] **Step 6: Modify `.github/workflows/gazer-mobile.yml` `release` job — reject debug-signed artifacts**

Anchor (the `release` job header as Task 21 Step 15b already left it — that step appended
`integration` to Task 3 Step 2's original `needs:` list before this task runs; only the
`needs:`/missing `container:` lines change here, and steps after `Checkout code` gain one new
step):
```yaml
  release:
    name: GitHub Release
    needs: [build, test, android-unit, security, integration]
    if: startsWith(github.ref, 'refs/tags/gazer-v')
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: Download APK artifact
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8
        with:
          name: gazer-apk
          path: release-artifacts

      - name: Download AAB artifact
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8
        with:
          name: gazer-aab
          path: release-artifacts

      - name: Create GitHub Release
```
Replace with:
```yaml
  release:
    name: GitHub Release
    needs: [toolchain, build, test, android-unit, security, integration]
    if: startsWith(github.ref, 'refs/tags/gazer-v')
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: read  # added so this job's new container: step below can pull the toolchain image
    container:
      image: ${{ needs.toolchain.outputs.image }}
      options: --user 1000:1000
    steps:
      - name: Checkout code
        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6

      - name: Download APK artifact
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8
        with:
          name: gazer-apk
          path: release-artifacts

      - name: Download AAB artifact
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c  # v8
        with:
          name: gazer-aab
          path: release-artifacts

      - name: Verify no downloaded APK is debug-signed
        run: |
          set -euo pipefail
          APKSIGNER="${ANDROID_SDK_ROOT}/build-tools/36.0.0/apksigner"
          FOUND=0
          while IFS= read -r -d '' apk; do
            echo "checking: ${apk}"
            OUTPUT=$("${APKSIGNER}" verify --print-certs "${apk}")
            echo "${OUTPUT}"
            if echo "${OUTPUT}" | grep -q 'CN=Android Debug'; then
              echo "FAIL: ${apk} is signed with the well-known Android debug key" >&2
              FOUND=1
            fi
          done < <(find release-artifacts -name '*.apk' -print0)
          test "${FOUND}" -eq 0

      - name: Create GitHub Release
        uses: softprops/action-gh-release@b4309332981a82ec1c5618f44dd2e27cc8bfbfda  # v3
        with:
          files: release-artifacts/**/*
          generate_release_notes: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```
(`GITHUB_TOKEN` masking is automatic for all workflow secrets — no extra step needed.)

**Note:** Task 3's own `release` job comment told Task 21 to extend `needs:` to
`[build, test, android-unit, security, integration]`, and Task 21 Step 15b already applied that
sed before this task runs — the anchor above reflects that post-Task-21 state. This task's
replacement adds `toolchain` for the container pull while preserving `integration`, producing
the final `needs: [toolchain, build, test, android-unit, security, integration]`.

Run: `grep -c 'CN=Android Debug' .github/workflows/gazer-mobile.yml`
Expected: `1`

- [ ] **Step 7: Modify `Makefile` — add `mobile-build-signed`**

Anchor (Task 1 Step 8's exact `.PHONY` line and `mobile-build` target):
```makefile
.PHONY: mobile-toolchain mobile-run mobile-lint mobile-test mobile-test-android mobile-build mobile-security mobile-codegen mobile-clean mobile-test-integration mobile-screenshots seed-mock-data-mobile
```
```makefile
mobile-build:
	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter build apk --split-per-abi --obfuscate --split-debug-info=build/symbols; flutter build appbundle --obfuscate --split-debug-info=build/symbols"
```
Replace the `.PHONY` line with (adds `mobile-build-signed` only):
```makefile
.PHONY: mobile-toolchain mobile-run mobile-lint mobile-test mobile-test-android mobile-build mobile-build-signed mobile-security mobile-codegen mobile-clean mobile-test-integration mobile-screenshots seed-mock-data-mobile
```
Append immediately after the `mobile-build:` target:
```makefile

mobile-build-signed:
	@test -f mobile/gazer/android/key.properties || { echo "mobile-build-signed requires mobile/gazer/android/key.properties -- see docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1.md Task 25 Step 4 (one-time keystore procedure) or Step 8c (throwaway local keystore for testing)" >&2; exit 1; }
	$(MOBILE_RUN) -e GAZER_REQUIRE_SIGNING=1 bash -lc "set -euo pipefail; flutter build apk --split-per-abi --obfuscate --split-debug-info=build/symbols; flutter build appbundle --obfuscate --split-debug-info=build/symbols"
```
Run: `grep -c '^mobile-build-signed:' Makefile`
Expected: `1`

- [ ] **Step 8: Verification — the four shell-level checks in place of a Gradle unit test**

**(a) Warning fires exactly once, unsigned build still produces APKs:**
```bash
rm -f mobile/gazer/android/key.properties
make mobile-build 2>&1 | tee /tmp/mobile-build-unsigned.log
grep -c '^WARNING: release build is debug-signed (no key.properties)$' /tmp/mobile-build-unsigned.log
ls mobile/gazer/build/app/outputs/flutter-apk/*.apk
```
Expected: the `grep -c` prints `1`; the `ls` lists the per-ABI APKs.

**(b) Tag-mode requirement fails closed without a keystore:**
```bash
GAZER_REQUIRE_SIGNING=1 make mobile-run CMD="flutter build apk --release" 2>&1 | tee /tmp/mobile-build-required.log
grep -c 'GAZER_REQUIRE_SIGNING=1 but key.properties is missing' /tmp/mobile-build-required.log
```
Expected: the build fails (non-zero from the underlying gradle/flutter invocation) and the
`grep -c` prints `1`.

**(c) Throwaway local keystore signs successfully:**
```bash
set -euo pipefail
keytool -genkeypair -v -keystore /tmp/throwaway-upload.jks -alias throwaway \
  -keyalg RSA -keysize 4096 -validity 1 -dname "CN=Gazer Throwaway Test, OU=QA, O=PenguinTech, C=US" \
  -storepass throwaway123 -keypass throwaway123
cp /tmp/throwaway-upload.jks mobile/gazer/android/throwaway-upload.jks
cat > mobile/gazer/android/key.properties <<'KEYPROPS_EOF'
storeFile=throwaway-upload.jks
storePassword=throwaway123
keyAlias=throwaway
keyPassword=throwaway123
KEYPROPS_EOF
make mobile-build-signed
apksigner verify --print-certs mobile/gazer/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk
rm -f mobile/gazer/android/key.properties mobile/gazer/android/throwaway-upload.jks /tmp/throwaway-upload.jks
```
Expected: `make mobile-build-signed` exits 0; `apksigner verify --print-certs` output shows
`CN=Gazer Throwaway Test` (or whichever `-dname` was used), never `CN=Android Debug`.
(This step used the host's own `keytool`/`apksigner` if `mobile-build-signed`'s container doesn't
expose a host keystore path directly — if the container's mounted `/work` doesn't see files placed
outside `mobile/gazer/`, generate `throwaway-upload.jks` directly under `mobile/gazer/android/`
instead of `/tmp` and adjust the `cp`/`rm` above accordingly.)

**(d) zizmor:**
```bash
uvx zizmor==1.30.0 .github/workflows/gazer-mobile.yml
```
Expected: no `error`-level findings (same bar as Task 3 Step 3). Pay particular attention to the
new `env:`-only secret usage in Step 5/6 above — zizmor's template-injection check is exactly what
that pattern exists to satisfy.

**(e) Push and confirm; throwaway tag proves the tag gate is real:**
```bash
git push -u origin HEAD
gh run watch "$(gh run list --workflow gazer-mobile.yml --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
gh run list --workflow gazer-mobile.yml --limit 1
```
Expected: `build` job green (including the new "Verify APK is signed with exactly one
certificate" step) — this exercises the "secrets are absent" branch of Step 5 (the `if:`-gated
decode step is skipped, `GAZER_REQUIRE_SIGNING` is `0` on a non-tag push, so the debug-signing
fallback and its `WARNING` line are expected here, not a failure).

Then prove the tag gate itself fails until the secrets actually exist by testing on a throwaway
tag (skip this specific sub-step if the Step 4 secrets are already set in the repo — in that case
the tag build is expected to succeed, and this sub-step is not applicable):
```bash
git tag gazer-v0.0.1-test
git push origin gazer-v0.0.1-test
RUN_ID=$(gh run list --workflow gazer-mobile.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" --exit-status; echo "watch exit=$? (non-zero is the expected outcome while secrets are absent)"
test "$(gh run view "$RUN_ID" --json conclusion --jq .conclusion)" = failure && echo "tag gate holds: run concluded failure"
```
Expected (secrets not yet set): the last line prints `tag gate holds: run concluded failure`; the `build` job's `flutter build apk`/`appbundle` steps fail with
`GAZER_REQUIRE_SIGNING=1 but key.properties is missing` (tag ref matches `refs/tags/gazer-v*`).
Clean up afterward regardless of outcome — this tag/release must not remain:
```bash
gh release delete gazer-v0.0.1-test --yes 2>/dev/null || true
git push --delete origin gazer-v0.0.1-test
git tag -d gazer-v0.0.1-test
```
Expected: both the tag and any release created from it are gone; `gh run list --workflow
gazer-mobile.yml` no longer needs to reference this throwaway run for anything going forward.

- [ ] **Step 9: Add the signing-verification line to Task 26's checklist**

Modify `docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1.md` — in Task 26 Step 13, insert one
line after this exact existing line:
```
  Each must be < 100 MB.
```
New text to insert immediately after it (before the next fenced `make mobile-test-integration`
block):
```
  Record: `apksigner verify --print-certs` on the release APK shows the upload cert, not `CN=Android Debug`.
```
Run: `grep -n 'apksigner verify --print-certs. on the release APK shows the upload cert' docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1.md`
Expected: one matching line, immediately following the `Each must be < 100 MB.` line.

- [ ] **Step 10: Commit**

```bash
git add mobile/gazer/android/app/build.gradle.kts .gitignore \
  .github/workflows/gazer-mobile.yml Makefile \
  docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1.md
git commit -m "$(cat <<'COMMIT_EOF'
feat(gazer): add release signing -- upload keystore, CI decode/verify, fail-closed on tags

android/app/build.gradle.kts now loads a gitignored key.properties into a
signingConfigs.create("upload"); falls back to debug-signing with a single
unmistakable WARNING when key.properties is absent; and throws when
GAZER_REQUIRE_SIGNING=1 (set on tag builds only) with no key.properties.
CI's build job decodes ANDROID_UPLOAD_KEY_STORE_B64 + 3 password/alias
secrets via env: (never inline in run:, per zizmor), verifies the built
APK has exactly one signer, and deletes the keystore/key.properties
afterward with if: always(). CI's release job now rejects any downloaded
APK signed with the well-known Android debug certificate. Added
mobile-build-signed make target and one Task 26 checklist line.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
COMMIT_EOF
)"
```


### Task 26: Mock data, seeding, README, screenshots, M1 verification

**Files:**
- Create: `mobile/gazer/test/fixtures/mock_targets.dart`
- Create: `mobile/gazer/lib/config/seed.dart`
- Create: `mobile/gazer/README.md`
- Create: `mobile/gazer/integration_test/screenshots_test.dart`
- Create: `mobile/gazer/scripts/mobile_screenshots_entrypoint.sh`
- Create: `mobile/gazer/scripts/collect_screenshots.sh`
- Test: `mobile/gazer/test/fixtures/mock_targets_test.dart`
- Test: `mobile/gazer/test/config/seed_test.dart`
- Modify: `mobile/gazer/lib/main.dart` (call `applySeedIfRequested` before `runApp`)
- Modify: `Makefile` (repo root) — add `seed-mock-data-mobile`, `mobile-screenshots`; amend `mobile-test`'s `flutter test --coverage` invocation to always pass `--dart-define=GAZER_SEED=true` (rationale in Step 3)
- Create: `docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1-verification.md` (dated the day verification is actually run)

**Interfaces:**
- Consumes: `StreamTargetSettings`, `QualitySettings`/`QualitySettings.defaults()`, `SettingsRepository`, `GazerSettings`/`GazerSettings.defaults()`, `SecureSettingsRepository`, `GazerApp`.
- Produces: `List<StreamTargetSettings> mockTargets` (4 entries), `List<QualitySettings> mockQualityPresets` (2 entries), `Future<void> applySeedIfRequested(SettingsRepository repo)`; `make seed-mock-data-mobile`, `make mobile-screenshots`; `mobile/gazer/README.md`; `docs/screenshots/gazer/{home-idle-phone,settings-phone,status-panel-phone,home-tablet,status-panel-tablet}.png`.

- [ ] **Step 1: Failing test for the mock fixtures.**
  Create `mobile/gazer/test/fixtures/mock_targets_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';
  import 'package:gazer/models/quality.dart';

  import 'mock_targets.dart';

  void main() {
    test('mockTargets has exactly the 4 spec presets in spec order', () {
      expect(mockTargets, hasLength(4));
      expect(mockTargets[0].url, 'rtmp://ingest-a.example.com/live');
      expect(mockTargets[0].streamKey, 'demo-key-0001');
      expect(mockTargets[0].username, isNull);

      expect(mockTargets[1].url, 'rtmps://ingest-b.example.com/app');
      expect(mockTargets[1].streamKey, 'demo-key-0002');
      expect(mockTargets[1].username, 'demo');
      expect(mockTargets[1].password, isNotNull);

      expect(mockTargets[2].url, 'rtmp://10.0.2.2:1935/live');
      expect(mockTargets[2].streamKey, isNull);

      expect(mockTargets[3].url, 'http://bad.example.com');
    });

    test('mockQualityPresets has exactly 2 presets: default and low-bandwidth', () {
      expect(mockQualityPresets, hasLength(2));
      expect(mockQualityPresets[0], QualitySettings.defaults());
      expect(mockQualityPresets[1].resolution, Resolution.p360);
      expect(mockQualityPresets[1].frameRate, FrameRate.fps15);
      expect(mockQualityPresets[1].videoBitrateKbps, 800);
      expect(mockQualityPresets[1].adaptiveBitrate, isFalse);
    });
  }
  ```
  Run `make mobile-run CMD="flutter test test/fixtures/mock_targets_test.dart"`.
  Expected: compile error — `mock_targets.dart` doesn't exist.

- [ ] **Step 2: Implement the fixtures, get Step 1 green.**
  Create `mobile/gazer/test/fixtures/mock_targets.dart`:
  ```dart
  /// The 4 seeded stream-target presets and 2 quality presets used across
  /// widget tests, the integration tests, and `make mobile-screenshots`
  /// capture runs. Mirrors the spec's Mock Data section verbatim — do not
  /// add or remove entries without updating that section too.
  library;

  import 'package:gazer/models/quality.dart';
  import 'package:gazer/models/stream_target_settings.dart';

  /// Target 1: plain RTMP, key auto-appended, no auth.
  final StreamTargetSettings mockTargetPlainRtmp = StreamTargetSettings(
    url: 'rtmp://ingest-a.example.com/live',
    streamKey: 'demo-key-0001',
  );

  /// Target 2: RTMPS with username/password auth.
  final StreamTargetSettings mockTargetRtmpsAuth = StreamTargetSettings(
    url: 'rtmps://ingest-b.example.com/app',
    streamKey: 'demo-key-0002',
    username: 'demo',
    password: 'demo-password-0002',
  );

  /// Target 3: emulator host loopback — nothing listens here. Used by the
  /// go-live-unreachable integration test and offline-behaviour widget tests.
  final StreamTargetSettings mockTargetEmulatorLoopback = StreamTargetSettings(
    url: 'rtmp://10.0.2.2:1935/live',
  );

  /// Target 4: invalid scheme (`http`, not `rtmp`/`rtmps`) — used by
  /// TargetValidator tests asserting the scheme-validation issue fires.
  final StreamTargetSettings mockTargetInvalidScheme = StreamTargetSettings(
    url: 'http://bad.example.com',
  );

  /// All 4 mock targets, in spec order.
  final List<StreamTargetSettings> mockTargets = <StreamTargetSettings>[
    mockTargetPlainRtmp,
    mockTargetRtmpsAuth,
    mockTargetEmulatorLoopback,
    mockTargetInvalidScheme,
  ];

  /// Preset A: default quality — the seeded default and the "happy path"
  /// widget/screenshot fixture.
  final QualitySettings mockQualityDefault = QualitySettings.defaults();

  /// Preset B: low-bandwidth — exercises the resolution/fps/bitrate pickers
  /// away from their defaults in widget tests and goldens.
  final QualitySettings mockQualityLowBandwidth = QualitySettings(
    resolution: Resolution.p360,
    frameRate: FrameRate.fps15,
    videoBitrateKbps: 800,
    adaptiveBitrate: false,
  );

  /// Both quality presets, in spec order.
  final List<QualitySettings> mockQualityPresets = <QualitySettings>[
    mockQualityDefault,
    mockQualityLowBandwidth,
  ];
  ```
  Run `make mobile-run CMD="flutter test test/fixtures/mock_targets_test.dart"`.
  Expected: `00:01 +2: All tests passed!`
  Commit:
  ```
  git add mobile/gazer/test/fixtures/mock_targets.dart mobile/gazer/test/fixtures/mock_targets_test.dart
  git commit -m "$(cat <<'EOF'
  test(gazer): add the 4 mock targets and 2 quality presets

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 3: Failing test for `applySeedIfRequested`, and the coverage-gate fix.**
  Create `mobile/gazer/test/config/seed_test.dart`:
  ```dart
  import 'package:flutter_test/flutter_test.dart';

  import 'package:gazer/config/seed.dart';
  import 'package:gazer/models/gazer_settings.dart';
  import 'package:gazer/models/quality.dart';
  import 'package:gazer/models/stream_target_settings.dart';
  import 'package:gazer/services/settings_repository.dart';

  import '../fixtures/mock_targets.dart' as fixtures;

  class _InMemorySettingsRepository implements SettingsRepository {
    _InMemorySettingsRepository(this._stored);
    GazerSettings _stored;
    int saveCount = 0;

    @override
    Future<GazerSettings> load() async => _stored;

    @override
    Future<void> save(GazerSettings s) async {
      _stored = s;
      saveCount++;
    }
  }

  void main() {
    group('applySeedIfRequested', () {
      test('is a no-op without --dart-define=GAZER_SEED=true', () async {
        final repo = _InMemorySettingsRepository(GazerSettings.defaults());
        await applySeedIfRequested(repo);
        if (!const bool.fromEnvironment('GAZER_SEED')) {
          expect(repo.saveCount, 0);
          expect(await repo.load(), GazerSettings.defaults());
        }
      });

      test('seeds an empty (defaults) repository when GAZER_SEED=true', () async {
        final repo = _InMemorySettingsRepository(GazerSettings.defaults());
        await applySeedIfRequested(repo);
        if (const bool.fromEnvironment('GAZER_SEED')) {
          expect(repo.saveCount, 1);
          final GazerSettings result = await repo.load();
          expect(result.target, fixtures.mockTargets.first);
          expect(result.quality, QualitySettings.defaults());
        }
      });

      test('never overwrites a repository with non-default settings, even when GAZER_SEED=true', () async {
        final GazerSettings customized = GazerSettings.defaults().copyWith(
          target: StreamTargetSettings(url: 'rtmp://real-user-endpoint.example.com/live'),
        );
        final repo = _InMemorySettingsRepository(customized);
        await applySeedIfRequested(repo);
        expect(repo.saveCount, 0, reason: 'never clobber real saved settings');
        expect(await repo.load(), customized);
      });
    });
  }
  ```
  Run `make mobile-run CMD="flutter test test/config/seed_test.dart"`.
  Expected: compile error — `lib/config/seed.dart` doesn't exist.

  **Coverage-gate note (apply now, before Step 4):** `applySeedIfRequested`'s exact contracted signature is `Future<void> applySeedIfRequested(SettingsRepository repo)` — no injectable clock/flag parameter, so its seeding branch can only be reached by actually running with `--dart-define=GAZER_SEED=true`. Task 1's `mobile-test` target runs plain `flutter test --coverage` (no such define), so the seeding lines in `lib/config/seed.dart` would be permanently uncovered by the CI-gated lcov report even though `make mobile-run CMD="flutter test test/config/seed_test.dart --dart-define=GAZER_SEED=true"` proves them correct. Fix this at the source: modify `Makefile`'s `mobile-test` target to always pass `--dart-define=GAZER_SEED=true`. This is safe — nothing else in the suite reads `GAZER_SEED`, and `main.dart` (which does) is never exercised by `flutter test`, only by `flutter run`/`flutter build`/`flutter test integration_test/`.

  Task 1's exact current target (`Makefile`, repo root):
  ```makefile
  mobile-test:
  	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter test --coverage; bash scripts/coverage_gate.sh 90 coverage/lcov.info lcov"
  ```
  Modify it — inside the `bash -lc "..."` string only, the `flutter test --coverage;` clause gains the define — to:
  ```makefile
  mobile-test:
  	$(MOBILE_RUN) bash -lc "set -euo pipefail; flutter test --coverage --dart-define=GAZER_SEED=true; bash scripts/coverage_gate.sh 90 coverage/lcov.info lcov"
  ```
  Apply with:
  ```
  sed -i 's/flutter test --coverage; bash scripts\/coverage_gate.sh/flutter test --coverage --dart-define=GAZER_SEED=true; bash scripts\/coverage_gate.sh/' Makefile
  grep -n 'flutter test --coverage --dart-define=GAZER_SEED=true' Makefile
  ```
  Expected: the grep prints the modified `mobile-test` line exactly once. Commit this Makefile
  change together with the seed implementation in Step 4 (one coherent change).

- [ ] **Step 4: Implement `applySeedIfRequested`, get Step 3 green.**
  Create `mobile/gazer/lib/config/seed.dart`:
  ```dart
  /// Debug-only mock-data seeding for a fresh install.
  ///
  /// Applies a mock stream target + default quality preset when the app is
  /// launched with `--dart-define=GAZER_SEED=true` in a debug build. Exists
  /// for local development and `make mobile-screenshots` capture runs —
  /// never active in a release build (kDebugMode gates it) and never
  /// overwrites settings a real user already saved.
  library;

  import 'package:flutter/foundation.dart';

  import '../models/gazer_settings.dart';
  import '../models/quality.dart';
  import '../services/settings_repository.dart';
  import '../../test/fixtures/mock_targets.dart' as fixtures;

  bool get _seedRequested => kDebugMode && const bool.fromEnvironment('GAZER_SEED');

  /// Seeds [repo] with a mock target + default quality preset when
  /// `--dart-define=GAZER_SEED=true` was passed to a debug build AND the
  /// repository has no previously-saved settings (its `load()` still
  /// returns [GazerSettings.defaults] — the empty-state sentinel). Never
  /// overwrites a real user's saved settings; safe to call on every launch.
  Future<void> applySeedIfRequested(SettingsRepository repo) async {
    if (!_seedRequested) return;

    final GazerSettings current = await repo.load();
    if (current != GazerSettings.defaults()) {
      return; // real settings already saved - never clobber them
    }

    final GazerSettings seeded = current.copyWith(
      target: fixtures.mockTargets.first,
      quality: QualitySettings.defaults(),
    );
    await repo.save(seeded);
  }
  ```
  Note the deliberate `lib/` → `test/` relative import: `mock_targets.dart` has no `flutter_test`/`test` package dependency (it's pure data), this is a private-app relative import (not a `package:` import, so pub's publish-time boundary doesn't apply), and it's the one and only way to honor the exact requested seed formula (`mockTargets.first + QualitySettings.defaults()`) without duplicating the fixture data. It is unreachable in any release build regardless — `_seedRequested` short-circuits on `kDebugMode` first.

  Run `make mobile-run CMD="flutter test test/config/seed_test.dart"` (no define).
  Expected: `00:01 +3: All tests passed!` (branches gated by `if (!const bool.fromEnvironment('GAZER_SEED'))` execute; the other two tests' `if` bodies are skipped, not failed).
  Run `make mobile-run CMD="flutter test test/config/seed_test.dart --dart-define=GAZER_SEED=true"`.
  Expected: `00:01 +3: All tests passed!` (this time the seeding branch executes and is asserted).
  Commit:
  ```
  git add mobile/gazer/lib/config/seed.dart mobile/gazer/test/config/seed_test.dart Makefile
  git commit -m "$(cat <<'EOF'
  test(gazer): add debug-only mock-data seeding, always cover it in mobile-test

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 5: Wire the seed call into `main.dart`.**
  Modify `mobile/gazer/lib/main.dart`:
  ```dart
  import 'package:flutter/material.dart';
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_secure_storage/flutter_secure_storage.dart';
  import 'package:shared_preferences/shared_preferences.dart';

  import 'app.dart';
  import 'config/seed.dart';
  import 'services/settings_repository.dart';

  Future<void> main() async {
    WidgetsFlutterBinding.ensureInitialized();

    final SecureSettingsRepository settingsRepo = SecureSettingsRepository(
      secure: const FlutterSecureStorage(),
      prefs: SharedPreferencesAsync(),
    );
    await applySeedIfRequested(settingsRepo);

    runApp(const ProviderScope(child: GazerApp()));
  }
  ```
  (This constructs a second `SecureSettingsRepository` instance purely to seed before the provider tree reads settings — both instances read/write the same underlying platform storage, so they stay consistent.)
  Run `make mobile-test` — must still pass (widget tests construct `GazerApp` directly, bypassing `main()`, so this change is invisible to them).
  Manually verify main.dart still compiles for a real run:
  ```
  make mobile-run CMD="flutter build apk --debug --dart-define=GAZER_SEED=true"
  ```
  Expected: `✓ Built build/app/outputs/flutter-apk/app-debug.apk`.
  Commit:
  ```
  git add mobile/gazer/lib/main.dart
  git commit -m "$(cat <<'EOF'
  feat(gazer): apply GAZER_SEED mock data before runApp

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 6: `make seed-mock-data-mobile`.**
  Modify `Makefile` (repo root):
  ```makefile
  seed-mock-data-mobile: ## Launch Gazer with the mock target/quality preset seeded (debug only; needs an already-running emulator/device - interactive, not CI-safe/headless)
  	@echo "NOTE: attaches to whatever device/emulator is already running - start one first (e.g. run mobile/gazer/scripts/run_integration_test.sh's boot steps by hand, or launch an AVD from Android Studio). This cannot run headless or in CI; make mobile-test-integration already covers automated seeded coverage via --dart-define."
  	docker run --rm -it \
  		--network host \
  		--user $(shell id -u):$(shell id -g) \
  		-v $(PWD)/mobile/gazer:/work \
  		-v gazer-pub-cache:/home/appuser/.pub-cache \
  		-v gazer-gradle:/home/appuser/.gradle \
  		-w /work \
  		gazer-toolchain:3.47.2 \
  		flutter run --dart-define=GAZER_SEED=true
  ```
  Verify without a device attached (documents the expected, non-crashing failure mode):
  ```
  make -n seed-mock-data-mobile
  ```
  Expected: prints the `docker run ... flutter run --dart-define=GAZER_SEED=true` command line (dry-run — `make -n` never executes it, matching "cannot run headless").
  Commit:
  ```
  git add Makefile
  git commit -m "$(cat <<'EOF'
  chore(gazer): add seed-mock-data-mobile make target

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 7: README.**
  Create `mobile/gazer/README.md`:
  ```markdown
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
  ```
  Verify the banned word never appears:
  ```
  if grep -qi restream mobile/gazer/README.md; then echo "banned word present" >&2; exit 1; else echo "banned word absent"; fi
  ```
  Expected: `grep` finds nothing (exit 1), confirming zero occurrences.
  Commit:
  ```
  git add mobile/gazer/README.md
  git commit -m "$(cat <<'EOF'
  docs(gazer): add mobile/gazer/README.md

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 8: Screenshot test.**
  Create `mobile/gazer/integration_test/screenshots_test.dart`:
  ```dart
  import 'package:flutter_riverpod/flutter_riverpod.dart';
  import 'package:flutter_test/flutter_test.dart';
  import 'package:integration_test/integration_test.dart';

  import 'package:gazer/app.dart';

  /// Which physical form factor this capture run targets, set at build time
  /// via `--dart-define=GAZER_SCREENSHOT_FORM_FACTOR=phone|tablet`. Controls
  /// only which named screenshots this run captures — both runs execute the
  /// same widget flow; the emulator/AVD chosen for each run (gazer_ci vs.
  /// gazer_tablet, see scripts/mobile_screenshots_entrypoint.sh) supplies the
  /// actual phone-vs-tablet screen size that drives StatusPanel's responsive
  /// layout.
  const String _formFactor = String.fromEnvironment(
    'GAZER_SCREENSHOT_FORM_FACTOR',
    defaultValue: 'phone',
  );

  void main() {
    final IntegrationTestWidgetsFlutterBinding binding =
        IntegrationTestWidgetsFlutterBinding.ensureInitialized();

    testWidgets('capture docs/screenshots/gazer marketing set ($_formFactor)', (WidgetTester tester) async {
      await tester.pumpWidget(const ProviderScope(child: GazerApp()));
      await tester.pumpAndSettle(const Duration(seconds: 5));

      // Home, idle, mock target/quality already seeded by --dart-define=GAZER_SEED=true at launch.
      // Phone keeps the historical "home-idle-phone" name; tablet uses "home-tablet" to match
      // the fixed 5-file marketing set (see the Produces line and collect_screenshots.sh NAMES).
      await binding.takeScreenshot(_formFactor == 'phone' ? 'home-idle-phone' : 'home-tablet');

      if (_formFactor == 'phone') {
        await tester.tap(find.byKey(const Key('settingsGearButton')));
        await tester.pumpAndSettle();
        await binding.takeScreenshot('settings-$_formFactor');
        await tester.pageBack();
        await tester.pumpAndSettle();
      }

      await tester.tap(find.byKey(const Key('statusChip')));
      await tester.pumpAndSettle();
      await binding.takeScreenshot('status-panel-$_formFactor');
    });
  }
  ```
  This produces exactly 3 files on the phone run (`home-idle-phone`, `settings-phone`, `status-panel-phone`) and 2 on the tablet run (`home-tablet`, `status-panel-tablet`) — 5 total, matching the fixed-name set below. Cannot run standalone yet — Step 9's entrypoint drives both AVDs.
  Commit:
  ```
  git add mobile/gazer/integration_test/screenshots_test.dart
  git commit -m "$(cat <<'EOF'
  test(gazer): add screenshot capture integration test

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 9: Container entrypoint driving both AVDs.**
  Create `mobile/gazer/scripts/mobile_screenshots_entrypoint.sh`:
  ```bash
  #!/usr/bin/env bash
  # Runs inside the gazer-toolchain container (needs --device /dev/kvm and
  # --network host). Boots the phone AVD (gazer_ci), runs
  # integration_test/screenshots_test.dart for the phone shots, tears it
  # down, then boots the tablet AVD (gazer_tablet, Pixel Tablet profile,
  # 2560x1600 skin passed to the emulator binary - avdmanager's device
  # profile "pixel_tablet" supplies the base hardware definition; the skin
  # override is an emulator launch flag, not an avdmanager create-time one),
  # runs the same test for the tablet shots, tears it down.
  # decode_screenshots.py (Task 21) is additive across both runs.
  set -euo pipefail

  FLAGS_DEFINE="camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture"

  wait_for_boot() {
    local timeout=180
    while [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; do
      timeout=$((timeout - 2))
      if [ "$timeout" -le 0 ]; then
        echo "ERROR: emulator boot timed out" >&2
        return 1
      fi
      sleep 2
    done
  }

  run_form_factor() {
    local avd_name="$1"
    local emulator_flags="$2"
    local form_factor="$3"

    # shellcheck disable=SC2086
    emulator -avd "$avd_name" -no-window -gpu swiftshader_indirect -no-audio \
      -no-boot-anim -no-snapshot -accel on $emulator_flags &
    local emulator_pid=$!

    adb wait-for-device
    wait_for_boot

    flutter test integration_test/screenshots_test.dart -d emulator-5554 \
      --dart-define=GAZER_SEED=true \
      --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE" \
      --dart-define=GAZER_SCREENSHOT_FORM_FACTOR="$form_factor" \
      | tee "/tmp/screenshots_${form_factor}.log"

    grep -qE '\+[1-9][0-9]*' "/tmp/screenshots_${form_factor}.log"

    python3 scripts/decode_screenshots.py

    adb emu kill || echo "emulator for $form_factor already exited"
    wait "$emulator_pid" 2>/dev/null || echo "emulator process for $form_factor already reaped"
  }

  avdmanager --verbose create avd --force -n gazer_ci \
    -k "system-images;android-34;google_apis;x86_64" -d "pixel_6"
  run_form_factor "gazer_ci" "-camera-back emulated -camera-front emulated" "phone"

  avdmanager --verbose create avd --force -n gazer_tablet \
    -k "system-images;android-34;google_apis;x86_64" -d "pixel_tablet"
  run_form_factor "gazer_tablet" "-camera-back emulated -camera-front emulated -skin 2560x1600" "tablet"

  echo "screenshot capture complete for both form factors"
  ```
  `chmod +x mobile/gazer/scripts/mobile_screenshots_entrypoint.sh`.

- [ ] **Step 10: Host-side collector.**
  Create `mobile/gazer/scripts/collect_screenshots.sh`:
  ```bash
  #!/usr/bin/env bash
  # Runs on the HOST (not in the container - the toolchain container only
  # mounts mobile/gazer/, not the repo root, so it cannot write into
  # docs/screenshots/ itself). Copies the fixed-name marketing screenshot
  # set from mobile/gazer/build/integration_screenshots/ into
  # docs/screenshots/gazer/ at the repo root.
  set -euo pipefail

  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
  SRC_DIR="$REPO_ROOT/mobile/gazer/build/integration_screenshots"
  DEST_DIR="$REPO_ROOT/docs/screenshots/gazer"

  NAMES=(
    "home-idle-phone"
    "settings-phone"
    "status-panel-phone"
    "home-tablet"
    "status-panel-tablet"
  )

  mkdir -p "$DEST_DIR"

  copied=0
  for name in "${NAMES[@]}"; do
    src="$SRC_DIR/$name.png"
    if [ ! -f "$src" ]; then
      echo "ERROR: expected screenshot missing: $src" >&2
      exit 1
    fi
    cp "$src" "$DEST_DIR/$name.png"
    copied=$((copied + 1))
  done

  if [ "$copied" -ne "${#NAMES[@]}" ]; then
    echo "ERROR: copied $copied of ${#NAMES[@]} expected screenshots" >&2
    exit 1
  fi

  echo "copied $copied/${#NAMES[@]} screenshots into $DEST_DIR"
  ```
  `chmod +x mobile/gazer/scripts/collect_screenshots.sh`.
  Commit Steps 9–10 together:
  ```
  git add mobile/gazer/scripts/mobile_screenshots_entrypoint.sh mobile/gazer/scripts/collect_screenshots.sh
  git commit -m "$(cat <<'EOF'
  ci(gazer): add phone+tablet screenshot capture scripts

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 11: `make mobile-screenshots`.**
  Modify `Makefile` (repo root):
  ```makefile
  mobile-screenshots: ## Capture the docs/screenshots/gazer/ marketing set from seeded phone + tablet emulators (needs /dev/kvm)
  	@test -e /dev/kvm || { echo "ERROR: /dev/kvm not present - screenshot capture requires KVM"; exit 1; }
  	docker run --rm \
  		--device /dev/kvm \
  		--network host \
  		--user $(shell id -u):$(shell id -g) \
  		-v $(PWD)/mobile/gazer:/work \
  		-v gazer-pub-cache:/home/appuser/.pub-cache \
  		-v gazer-gradle:/home/appuser/.gradle \
  		-w /work \
  		gazer-toolchain:3.47.2 \
  		bash scripts/mobile_screenshots_entrypoint.sh
  	bash mobile/gazer/scripts/collect_screenshots.sh
  ```
  Commit:
  ```
  git add Makefile
  git commit -m "$(cat <<'EOF'
  ci(gazer): add mobile-screenshots make target

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 12: Run it, verify the exact 5 files, visual review.**
  Run `make mobile-screenshots`.
  Expected: two emulator boot cycles (~2–4 min each), `+2: All tests passed!` for the phone run, `+1: All tests passed!` for the tablet run, then `copied 5/5 screenshots into <repo>/docs/screenshots/gazer`.
  Verify:
  ```
  ls docs/screenshots/gazer/
  ```
  Expected exactly: `home-idle-phone.png settings-phone.png status-panel-phone.png home-tablet.png status-panel-tablet.png` (5 files, no more, no fewer).
  **Visual review checklist** (open each PNG):
  - No error banners or red `ErrorState` chips visible
  - No lorem-ipsum or unfilled template text — all copy is real seeded mock data
  - Dark theme rendered (ElderThemeData default)
  - Stream key/username/password masked (last-4-visible only) in `settings-phone.png`
  If any check fails, fix the underlying widget/state and re-run this step — do not hand-edit the PNGs.
  No commit for the PNGs themselves yet — the images are committed by the standard `capturing-marketing-screenshots` skill flow once reviewed; if this task is expected to commit them directly:
  ```
  git add docs/screenshots/gazer/*.png
  git commit -m "$(cat <<'EOF'
  docs(gazer): capture M1 marketing screenshots (phone + tablet)

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```

- [ ] **Step 13 (M1 verification checklist — final steps of Task 26): run every gate, record results.**
  Run each in order, recording the number requested (do not proceed past a failing gate):
  ```
  make mobile-lint
  ```
  Record: exit code (must be 0).
  ```
  make mobile-test
  ```
  Record: Dart lcov coverage % from `coverage/lcov.info` (`lcov --summary coverage/lcov.info` or the `scripts/coverage_gate.sh` output) — must be >=90%, and record the file count the gate examined (non-zero denominator).
  ```
  make mobile-test-android
  ```
  Record: Kotlin JaCoCo coverage % from `android/app/build/reports/jacoco/testDebugUnitTestCoverage/html/index.html` (or the CI-parsed summary) — must be >=90%.
  ```
  make mobile-security
  ```
  Record: osv-scanner packages scanned (count from its summary against `pubspec.lock` + the gradle dependency lock), semgrep files scanned (its `X files` summary line), gitleaks findings (must be 0).
  ```
  make mobile-build
  ```
  Record: APK size per ABI —
  ```
  ls -la mobile/gazer/build/app/outputs/flutter-apk/*.apk
  ```
  Each must be < 100 MB.
  ```
  make mobile-test-integration
  ```
  Record: test count from the `+N: All tests passed!` line (N includes both `go_live_unreachable_test.dart` and any Dart integration tests collected) plus the `connectedDebugAndroidTest` `BUILD SUCCESSFUL`.
  ```
  gh run list --workflow gazer-mobile.yml --branch feature/gazer-mobile-v2 --limit 1
  ```
  Record: conclusion must be `success` across every job (toolchain, analyze, test, android-unit, build, security, integration). If not, `gh run view <run-id> --log-failed` and fix — never carry a red CI run into the manual step below.

  **Manual physical-device step (cannot be scripted — needs a real RTMP endpoint and a real phone):**
  1. `adb install -r mobile/gazer/build/app/outputs/flutter-apk/app-arm64-v8a-release.apk` onto a physical phone (Pixel 8/9 or Galaxy S24 from the device matrix).
  2. In the app's Settings screen, enter the real RTMP endpoint the user supplies at runtime — **never commit this URL/key anywhere**, type it directly on-device.
  3. Select back camera, 540p/30fps/2000kbps (defaults), Go Live.
  4. Stream 5 minutes continuously. In the StatusPanel confirm: state = streaming, bitrate within ±20% of 2000kbps (1600–2400kbps observed), dropped frames < 1% of total sent.
  5. Disable Wi-Fi (or pull the cable / switch networks) mid-stream; confirm the chip walks Streaming → Reconnecting → back to Streaming once connectivity returns, without a manual Stop/Go-Live cycle.
  6. Record the results — device model, Android version, timestamp, observed bitrate range, dropped-frame %, and reconnect recovery time — in a dated note:
  ```
  git add docs/superpowers/plans/2026-09-07-gazer-mobile-v2-m1-verification.md
  git commit -m "$(cat <<'EOF'
  docs(gazer): record M1 verification results

  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01N2rQgkHY872RubwXoBZxtE
  EOF
  )"
  ```
  (Use the actual date the manual test is run for both the filename and the note's contents, not necessarily 2026-09-07 if verification happens later.)

  **Merge gate:** Merge to `release/v3.0.X` happens via PR per the `merging-to-release` skill, and only once every gate above — `make mobile-lint`, `make mobile-test` (>=90%), `make mobile-test-android` (>=90%), `make mobile-security` (0 findings, non-zero denominator recorded), `make mobile-build` (all ABIs < 100MB), `make mobile-test-integration` (non-zero test count), CI green on every job, and the manual physical-device recovery test — is green. No direct merge, no `--admin`, no exceptions.
