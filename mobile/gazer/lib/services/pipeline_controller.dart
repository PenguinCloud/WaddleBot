import 'dart:async';

import '../config/flag_keys.dart';
import '../models/gazer_settings.dart';
import '../models/pipeline_state.dart';
import '../models/quality.dart';
import '../models/stream_stats.dart';
import '../models/validation_issue.dart';
import '../pigeon/pipeline.g.dart';
import '../telemetry/gazer_telemetry.dart';
import 'feature_flags.dart';
import 'gazer_log.dart';
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
  })
    // ignore: prefer_initializing_formals
    : _host = host,
       // ignore: prefer_initializing_formals
       _events = events,
       // ignore: prefer_initializing_formals
       _policy = policy,
       // ignore: prefer_initializing_formals
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

  /// The [StreamConfig] the current Go Live was prepared with, retained so a
  /// reconnect can re-prepare: a failed connection releases the native engine
  /// (`GazerPipeline.onConnectionFailed`), so `start()` alone on the next
  /// attempt is rejected from a non-READY state and the retry never happens.
  StreamConfig? _pendingConfig;
  int _reconnectAttempt = 0;
  bool _cancelled = false;
  bool _isDisposed = false;
  bool _goingLive = false;

  /// True from the moment a reconnect retry is scheduled until its re-prepare
  /// either reaches [ConnectingState] or terminates in [ErrorState]. While
  /// true, [_onNativeStateEvent] suppresses the native `preparing`/`ready`
  /// events `GazerPipeline.prepare` fires unconditionally (GazerPipeline.kt:74,
  /// :133) — applying them would replace the visible [ReconnectingState] with
  /// Preparing/Ready for the retry's camera-open + codec-configure window.
  /// `home_screen.dart` renders the Stop button only for
  /// Connecting/Streaming/Reconnecting, so that window would otherwise hide
  /// Stop and briefly enable Go Live during the Ready instant — tapping it
  /// would reset [_reconnectAttempt] and defeat the retry budget.
  bool _reconnecting = false;

  /// Monotonic counter incremented by every [goLive] and [stop] call,
  /// identifying the current streaming session. [_retryAfter] captures the
  /// epoch active when its retry was scheduled and re-checks it after the
  /// backoff sleep and after its re-prepare call, so a retry left over from a
  /// session the user already stopped and restarted (Stop during backoff,
  /// then Go Live again before the old sleeper resolves) becomes a no-op
  /// instead of issuing a duplicate `prepare()` into the fresh session and
  /// orphaning an engine.
  int _sessionEpoch = 0;
  DateTime? _streamStartedAt;
  DateTime? _connectingStartedAt;

  // Running sum/count instead of a growing sample list: the rolling
  // average is O(1) per sample in both time and memory, however long a
  // stream session runs.
  int _bitrateSampleSum = 0;
  int _bitrateSampleCount = 0;

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
  ///
  /// Throws [StateError] if a previous call to [goLive] is still in
  /// flight, or if [current] is not [IdleState], [ReadyState], or
  /// [ErrorState] — the UI (Task 14) disables "Go Live" outside those
  /// states, but the controller defends itself against a stale/overlapping
  /// call regardless. If the native `prepare()` call reports failure
  /// (`PrepareResult.ok == false`), emits [ErrorState] with the reported
  /// `error`/`detail` and never calls `start()`.
  Future<void> goLive(
    GazerSettings settings, {
    required List<VideoDevice> devices,
    required String videoDeviceId,
    required FeatureFlags flags,
    OutputOrientation orientation = OutputOrientation.landscape,
  }) async {
    if (_goingLive) {
      throw StateError('goLive() is already in progress');
    }
    if (current is! IdleState &&
        current is! ReadyState &&
        current is! ErrorState) {
      throw StateError(
        'goLive() can only be called from Idle, Ready, or Error states (current: $_current)',
      );
    }
    _goingLive = true;
    try {
      final issues = const TargetValidator().validate(settings.target);
      final hasCredentials =
          (settings.target.username ?? '').isNotEmpty ||
          (settings.target.password ?? '').isNotEmpty;
      if (hasCredentials && !flags.isEnabled(FlagKeys.rtmpAuth)) {
        issues.add(
          const ValidationIssue(field: 'auth', messageKey: 'rtmpAuthDisabled'),
        );
      }
      if (!devices.any((d) => d.id == videoDeviceId)) {
        issues.add(
          const ValidationIssue(
            field: 'videoDeviceId',
            messageKey: 'errorDeviceNotFound',
          ),
        );
      }
      if (issues.isNotEmpty) {
        throw ArgumentError(
          issues.map((i) => '${i.field}:${i.messageKey}').join(', '),
        );
      }

      _cancelled = false;
      _reconnecting = false;
      _sessionEpoch += 1;
      _reconnectAttempt = 0;
      _streamStartedAt = null;
      _bitrateSampleSum = 0;
      _bitrateSampleCount = 0;
      _statsSnapshot = StreamStats.zero();
      _statsController.add(_statsSnapshot);

      final adaptive =
          settings.quality.adaptiveBitrate &&
          flags.isEnabled(FlagKeys.adaptiveBitrate);
      final config = StreamConfig(
        videoDeviceId: videoDeviceId,
        audioDeviceId: _audioDeviceIdFor(settings.audio),
        width: settings.quality.resolution.width,
        height: settings.quality.resolution.height,
        fps: settings.quality.frameRate.value,
        videoBitrateKbps: settings.quality.videoBitrateKbps,
        adaptiveBitrate: adaptive,
        audioBitrateKbps: kAudioBitrateKbps,
        orientation: orientation,
      );

      final sendCredentials = flags.isEnabled(FlagKeys.rtmpAuth);
      _pendingTarget = StreamTarget(
        url: TargetValidator.effectiveUrl(settings.target),
        username: sendCredentials ? settings.target.username : null,
        password: sendCredentials ? settings.target.password : null,
      );

      GazerLog.info('pipeline.goLive', <String, Object?>{
        'host': Uri.tryParse(_pendingTarget!.url)?.host ?? '',
      });

      _emit(const PreparingState());
      _pendingConfig = config;
      final prepareSpan = GazerTelemetry.startSpan('gazer.pipeline.prepare');
      final result = await _host.prepare(config);
      prepareSpan.end();
      if (!result.ok) {
        _emit(
          ErrorState(
            GazerError(
              code: result.error ?? GazerErrorCode.encoderFailed,
              detail: result.detail,
            ),
          ),
        );
        return;
      }
      _emit(const ReadyState());
      _emit(const ConnectingState());
      _connectingStartedAt = DateTime.now();
      final startSpan = GazerTelemetry.startSpan('gazer.pipeline.start');
      await _host.start(_pendingTarget!);
      startSpan.end();
    } finally {
      _goingLive = false;
    }
  }

  /// Requests a clean stop and cancels any pending reconnect retry.
  Future<void> stop() async {
    _cancelled = true;
    _reconnecting = false;
    _sessionEpoch += 1;
    _emit(const StoppingState());
    final stopSpan = GazerTelemetry.startSpan('gazer.pipeline.stop');
    await _host.stop();
    stopSpan.end();
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
        _emit(const IdleState());
      case NativePipelineState.preparing:
        if (!_reconnecting) _emit(const PreparingState());
      case NativePipelineState.ready:
        if (!_reconnecting) _emit(const ReadyState());
      case NativePipelineState.connecting:
        _emit(const ConnectingState());
      case NativePipelineState.streaming:
        _streamStartedAt ??= DateTime.now();
        // Recovery resets the reconnect budget: each new outage gets its
        // own 10-attempt window and restarts backoff from attempt 1.
        _reconnectAttempt = 0;
        _emit(const StreamingState());
      case NativePipelineState.stopping:
        // A user-requested Stop owns its own Stopping -> Idle sequence: [stop]
        // emits Stopping, awaits the native stop() round trip, then emits Idle.
        // GazerPipeline.stop() also publishes STOPPING and IDLE, and those
        // events are queued behind the method's own reply -- so the trailing
        // STOPPING lands *after* Idle and would drag the status chip back to
        // "Stopping" permanently, with Go Live still disabled (canGoLive
        // requires Idle/Ready/Error). Ignore it while cancelled; the IDLE that
        // follows it is applied unconditionally above, so a native-initiated
        // stop still converges on Idle either way.
        if (!_cancelled) _emit(const StoppingState());
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
      _statsSnapshot = _statsSnapshot.copyWith(
        reconnectCount: _statsSnapshot.reconnectCount + 1,
      );
      _statsController.add(_statsSnapshot);
      GazerLog.info('pipeline.reconnect', <String, Object?>{
        'attempt': _reconnectAttempt,
        'delayMs': delay.inMilliseconds,
      });
      _emit(ReconnectingState(_reconnectAttempt, delay));
      _reconnecting = true;
      final epoch = _sessionEpoch;
      unawaited(_retryAfter(delay, epoch));
    } else {
      _emit(ErrorState(GazerError(code: code, detail: detail)));
    }
  }

  /// Waits out [delay], then re-prepares the native pipeline and reconnects.
  ///
  /// The re-prepare is required, not defensive: a terminal RootEncoder failure
  /// releases the engine natively and leaves the pipeline outside READY, so
  /// `start()` on its own is rejected with `GazerErrorCode.unknown`
  /// ("start() called from state=ERROR") -- which [ReconnectPolicy] classifies
  /// as non-retryable, so the very first retry would end the whole reconnect
  /// loop in [ErrorState]. A prepare failure here is terminal for the same
  /// reason it is in [goLive]: nothing about waiting longer fixes an encoder
  /// or camera that will not open.
  ///
  /// [epoch] is the [_sessionEpoch] snapshot taken when this retry was
  /// scheduled. It is re-checked after the backoff sleep and again after the
  /// re-prepare call: either await can outlast a `stop()` followed by a fresh
  /// `goLive()` (both bump [_sessionEpoch]), and without this guard a stale
  /// retry would call `prepare()` into the new session, orphaning an engine
  /// the new session already owns (native `prepare()` has no state guard of
  /// its own -- it unconditionally builds a second engine and overwrites
  /// `engine` without releasing the first).
  Future<void> _retryAfter(Duration delay, int epoch) async {
    await _sleeper(delay);
    if (_isDisposed ||
        _cancelled ||
        epoch != _sessionEpoch ||
        _pendingTarget == null ||
        _pendingConfig == null) {
      return;
    }
    final prepareSpan = GazerTelemetry.startSpan('gazer.pipeline.prepare');
    final result = await _host.prepare(_pendingConfig!);
    prepareSpan.end();
    if (_isDisposed || _cancelled || epoch != _sessionEpoch) return;
    _reconnecting = false;
    if (!result.ok) {
      _emit(
        ErrorState(
          GazerError(
            code: result.error ?? GazerErrorCode.encoderFailed,
            detail: result.detail,
          ),
        ),
      );
      return;
    }
    _connectingStartedAt = DateTime.now();
    _emit(const ConnectingState());
    final retrySpan = GazerTelemetry.startSpan('gazer.pipeline.start');
    await _host.start(_pendingTarget!);
    retrySpan.end();
  }

  void _onNativeStats(StatsSample sample) {
    _bitrateSampleSum += sample.bitrateKbps;
    _bitrateSampleCount += 1;
    final average = _bitrateSampleSum / _bitrateSampleCount;
    final uptime = _streamStartedAt == null
        ? Duration.zero
        : DateTime.now().difference(_streamStartedAt!);
    _statsSnapshot = _statsSnapshot.copyWith(
      currentBitrateKbps: sample.bitrateKbps,
      averageBitrateKbps: average.round(),
      fps: sample.fps,
      droppedFrames: sample.droppedVideoFrames,
      sentBytes: sample.sentBytes,
      uptime: uptime,
      congestionPercent: sample.congestionPercent,
    );
    GazerTelemetry.histogram(
      'gazer.stream.bitrate_kbps',
      sample.bitrateKbps.toDouble(),
    );
    _statsController.add(_statsSnapshot);
  }

  /// Updates [_current], notifies [state] subscribers, and logs the
  /// transition (`from`/`to` runtime type names, plus `errorCode` when
  /// [next] is an [ErrorState]) at [GazerLog.debug] level — a no-op once
  /// [dispose] has run.
  void _emit(PipelineState next) {
    if (_isDisposed) return;
    GazerLog.debug('pipeline.state', <String, Object?>{
      'from': _current.runtimeType.toString(),
      'to': next.runtimeType.toString(),
      if (next is ErrorState) 'errorCode': next.error.code.name,
    });
    GazerTelemetry.counter('gazer.pipeline.state_change', <String, Object?>{
      'from': _current.runtimeType.toString(),
      'to': next.runtimeType.toString(),
    });
    if (next is StreamingState && _connectingStartedAt != null) {
      final latencyMs = DateTime.now()
          .difference(_connectingStartedAt!)
          .inMilliseconds;
      GazerTelemetry.histogram(
        'gazer.rtmp.connect_latency_ms',
        latencyMs.toDouble(),
      );
      _connectingStartedAt = null;
    }
    _current = next;
    _stateController.add(next);
  }

  /// Cancels native-event subscriptions and closes both broadcast streams.
  ///
  /// Sets [_isDisposed] before tearing anything down, so a reconnect retry
  /// already in flight (waiting on the injected sleeper) becomes a no-op
  /// when it resumes instead of emitting on a closed [StreamController] or
  /// issuing a stray `start()` — see [_emit] and [_retryAfter]. Idempotent:
  /// a second call is a no-op.
  void dispose() {
    if (_isDisposed) return;
    _isDisposed = true;
    _stateSub.cancel();
    _statsSub.cancel();
    _stateController.close();
    _statsController.close();
  }
}
