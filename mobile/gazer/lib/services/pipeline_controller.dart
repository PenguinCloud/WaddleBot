import 'dart:async';

import '../config/flag_keys.dart';
import '../models/gazer_settings.dart';
import '../models/pipeline_state.dart';
import '../models/quality.dart';
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
  int _reconnectAttempt = 0;
  bool _cancelled = false;
  bool _isDisposed = false;
  bool _goingLive = false;
  DateTime? _streamStartedAt;

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

      _emit(const PreparingState());
      final result = await _host.prepare(config);
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
      await _host.start(_pendingTarget!);
    } finally {
      _goingLive = false;
    }
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
        // Recovery resets the reconnect budget: each new outage gets its
        // own 10-attempt window and restarts backoff from attempt 1.
        _reconnectAttempt = 0;
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
      _statsSnapshot = _statsSnapshot.copyWith(
        reconnectCount: _statsSnapshot.reconnectCount + 1,
      );
      _statsController.add(_statsSnapshot);
      _emit(ReconnectingState(_reconnectAttempt, delay));
      unawaited(_retryAfter(delay));
    } else {
      _emit(ErrorState(GazerError(code: code, detail: detail)));
    }
  }

  Future<void> _retryAfter(Duration delay) async {
    await _sleeper(delay);
    if (_isDisposed || _cancelled || _pendingTarget == null) return;
    _emit(const ConnectingState());
    await _host.start(_pendingTarget!);
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
    _statsController.add(_statsSnapshot);
  }

  void _emit(PipelineState next) {
    if (_isDisposed) return;
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
