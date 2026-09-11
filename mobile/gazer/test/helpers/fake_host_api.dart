import 'dart:async';

import 'package:flutter/services.dart';
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
///
/// `GazerHostApi` is a concrete Pigeon-generated class (its methods talk to
/// a real platform channel), not an abstract interface, so `implements`
/// here must re-declare its two instance fields
/// (`pigeonVar_binaryMessenger`, `pigeonVar_messageChannelSuffix`) in
/// addition to its methods — every method on the real class is also
/// `Future<...>`-returning, which this fake mirrors even where the native
/// side would reply synchronously in spirit (e.g. `getState`).
class FakeGazerHostApi implements GazerHostApi {
  // Names below are dictated by the Pigeon-generated GazerHostApi base class
  // this fake overrides.
  @override
  // ignore: non_constant_identifier_names
  final BinaryMessenger? pigeonVar_binaryMessenger = null;

  @override
  // ignore: non_constant_identifier_names
  final String pigeonVar_messageChannelSuffix = '';

  /// Every method name invoked, in call order (e.g. `'prepare'`, `'start'`).
  final List<String> calls = [];

  /// Every [StreamConfig] passed to [prepare], in call order.
  final List<StreamConfig> prepareCalls = [];

  /// Every [StreamTarget] passed to [start], in call order.
  final List<StreamTarget> startCalls = [];

  /// Number of times [stop] has been called.
  int stopCallCount = 0;

  /// Value [prepare] resolves to; tests can override to simulate failure.
  PrepareResult prepareResult = PrepareResult(ok: true);

  /// When set, [prepare] awaits this before resolving. Lets a test hold a
  /// `prepare()` call in flight -- e.g. to inject native `preparing`/`ready`
  /// events via [bridge] while the real Pigeon round trip is still
  /// outstanding, deterministically instead of relying on microtask
  /// scheduling order between the fake's own (unawaited) return and however
  /// many bridge events a test fires around it.
  Completer<void>? prepareGate;

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
  Future<void> emitState(
    NativePipelineState state, {
    GazerErrorCode? error,
    String? detail,
  }) async {
    bridge.onStateChanged(
      StateEvent(state: state, error: error, detail: detail),
    );
    await Future<void>.delayed(Duration.zero);
  }

  /// Pushes a [StatsSample] into [bridge], then yields one microtask so
  /// listeners observe it before the caller continues.
  Future<void> emitStats(StatsSample sample) async {
    bridge.onStats(sample);
    await Future<void>.delayed(Duration.zero);
  }

  @override
  Future<List<VideoDevice>> listVideoDevices() async {
    calls.add('listVideoDevices');
    return videoDevices;
  }

  @override
  Future<List<AudioDevice>> listAudioDevices() async {
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
    final gate = prepareGate;
    if (gate != null) await gate.future;
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
  Future<void> setVideoBitrate(int kbps) async {
    calls.add('setVideoBitrate($kbps)');
  }

  @override
  Future<NativePipelineState> getState() async {
    calls.add('getState');
    return NativePipelineState.idle;
  }
}
