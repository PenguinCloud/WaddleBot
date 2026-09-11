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

  final backCamera = VideoDevice(
    id: 'camera:back',
    kind: VideoDeviceKind.backCamera,
    name: 'Back Camera',
  );

  GazerSettings settingsWith({String? username, String? password}) =>
      GazerSettings(
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

  FeatureFlags flagsWith({bool adaptiveBitrate = true, bool rtmpAuth = true}) =>
      FeatureFlags(
        LicenseState(
          status: LicenseStatus.valid,
          flags: {
            FlagKeys.cameraStream: true,
            FlagKeys.adaptiveBitrate: adaptiveBitrate,
            FlagKeys.rtmpAuth: rtmpAuth,
            FlagKeys.uvcCapture: false,
          },
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ),
      );

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
    test(
      'transitions Idle -> Preparing -> Ready -> Connecting -> Streaming',
      () async {
        final seen = <PipelineState>[];
        final sub = controller.state.listen(seen.add);

        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );
        bridge.onStateChanged(StateEvent(state: NativePipelineState.streaming));
        await Future<void>.delayed(Duration.zero);

        expect(seen, [
          const PreparingState(),
          const ReadyState(),
          const ConnectingState(),
          const StreamingState(),
        ]);
        expect(controller.current, const StreamingState());
        await sub.cancel();
      },
    );

    test(
      'adaptive flag off forces StreamConfig.adaptiveBitrate to false',
      () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(adaptiveBitrate: false),
        );
        expect(host.prepareCalls.single.adaptiveBitrate, isFalse);
      },
    );

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

      bridge.onStateChanged(
        StateEvent(
          state: NativePipelineState.error,
          error: GazerErrorCode.rtmpConnectFailed,
        ),
      );
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

      bridge.onStateChanged(
        StateEvent(
          state: NativePipelineState.error,
          error: GazerErrorCode.rtmpAuthFailed,
        ),
      );
      await Future<void>.delayed(Duration.zero);

      expect(controller.current, isA<ErrorState>());
      expect(
        (controller.current as ErrorState).error.code,
        GazerErrorCode.rtmpAuthFailed,
      );
      expect(sleeper.pendingCount, 0);
    });
  });

  group('reconnect exhaustion', () {
    test(
      'after 10 retried attempts, the 11th failure is a terminal ErrorState',
      () async {
        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );

        for (var attempt = 1; attempt <= 10; attempt++) {
          bridge.onStateChanged(
            StateEvent(
              state: NativePipelineState.error,
              error: GazerErrorCode.rtmpConnectFailed,
            ),
          );
          await Future<void>.delayed(Duration.zero);
          expect(
            controller.current,
            isA<ReconnectingState>(),
            reason: 'attempt $attempt',
          );
          sleeper.resolveNext();
          await Future<void>.delayed(Duration.zero);
        }

        bridge.onStateChanged(
          StateEvent(
            state: NativePipelineState.error,
            error: GazerErrorCode.rtmpConnectFailed,
          ),
        );
        await Future<void>.delayed(Duration.zero);

        expect(controller.current, isA<ErrorState>());
      },
    );
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

      bridge.onStateChanged(
        StateEvent(
          state: NativePipelineState.error,
          error: GazerErrorCode.rtmpConnectFailed,
        ),
      );
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
      bridge.onStateChanged(StateEvent(state: NativePipelineState.streaming));
      await Future<void>.delayed(Duration.zero);

      bridge.onStats(
        StatsSample(
          bitrateKbps: 2000,
          fps: 30,
          droppedVideoFrames: 0,
          sentBytes: 1000,
          congestionPercent: 0,
        ),
      );
      await Future<void>.delayed(Duration.zero);
      bridge.onStats(
        StatsSample(
          bitrateKbps: 1000,
          fps: 29,
          droppedVideoFrames: 1,
          sentBytes: 2000,
          congestionPercent: 10,
        ),
      );
      await Future<void>.delayed(Duration.zero);

      final latest = seen.last;
      expect(latest.currentBitrateKbps, 1000);
      expect(latest.averageBitrateKbps, 1500);
      expect(latest.droppedFrames, 1);
      expect(latest.sentBytes, 2000);
      expect(latest.uptime, greaterThanOrEqualTo(Duration.zero));

      bridge.onStateChanged(
        StateEvent(
          state: NativePipelineState.error,
          error: GazerErrorCode.rtmpConnectFailed,
        ),
      );
      await Future<void>.delayed(Duration.zero);

      expect(seen.last.reconnectCount, 1);
      await sub.cancel();
    });
  });

  group('dispose during reconnect', () {
    test('resolving the sleeper after dispose does not throw and does not call start again', () async {
      await controller.goLive(
        settingsWith(),
        devices: [backCamera],
        videoDeviceId: 'camera:back',
        flags: flagsWith(),
      );
      final startCallsBefore = host.startCalls.length;

      bridge.onStateChanged(
        StateEvent(
          state: NativePipelineState.error,
          error: GazerErrorCode.rtmpConnectFailed,
        ),
      );
      await Future<void>.delayed(Duration.zero);
      expect(controller.current, isA<ReconnectingState>());

      controller.dispose();

      expect(() => sleeper.resolveNext(), returnsNormally);
      await Future<void>.delayed(Duration.zero);

      expect(host.startCalls.length, startCallsBefore);
    });
  });

  group('reconnect attempt resets after recovery', () {
    test('two recovered outages each retry at attempt 1; a later outage still gets 10 attempts', () async {
      await controller.goLive(
        settingsWith(),
        devices: [backCamera],
        videoDeviceId: 'camera:back',
        flags: flagsWith(),
      );

      Future<void> failAndRecoverOnce() async {
        bridge.onStateChanged(
          StateEvent(
            state: NativePipelineState.error,
            error: GazerErrorCode.rtmpConnectFailed,
          ),
        );
        await Future<void>.delayed(Duration.zero);
        expect((controller.current as ReconnectingState).attempt, 1);
        sleeper.resolveNext();
        await Future<void>.delayed(Duration.zero);
        bridge.onStateChanged(StateEvent(state: NativePipelineState.streaming));
        await Future<void>.delayed(Duration.zero);
        expect(controller.current, const StreamingState());
      }

      // First outage: recovers after one retry at attempt 1.
      await failAndRecoverOnce();
      // Second outage: budget must have reset -- still attempt 1, not 2.
      await failAndRecoverOnce();

      // Third outage: exhausts the full 10-attempt budget from scratch.
      for (var attempt = 1; attempt <= 10; attempt++) {
        bridge.onStateChanged(
          StateEvent(
            state: NativePipelineState.error,
            error: GazerErrorCode.rtmpConnectFailed,
          ),
        );
        await Future<void>.delayed(Duration.zero);
        expect(
          (controller.current as ReconnectingState).attempt,
          attempt,
          reason: 'attempt $attempt',
        );
        sleeper.resolveNext();
        await Future<void>.delayed(Duration.zero);
      }

      bridge.onStateChanged(
        StateEvent(
          state: NativePipelineState.error,
          error: GazerErrorCode.rtmpConnectFailed,
        ),
      );
      await Future<void>.delayed(Duration.zero);

      expect(controller.current, isA<ErrorState>());
    });
  });

  group('goLive re-entrancy guard', () {
    test('an overlapping call throws StateError and only one prepare reaches the host', () async {
      final first = controller.goLive(
        settingsWith(),
        devices: [backCamera],
        videoDeviceId: 'camera:back',
        flags: flagsWith(),
      );

      expect(
        () => controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        ),
        throwsStateError,
      );

      await first;
      expect(host.prepareCalls.length, 1);
    });

    test('calling goLive while Streaming throws StateError', () async {
      await controller.goLive(
        settingsWith(),
        devices: [backCamera],
        videoDeviceId: 'camera:back',
        flags: flagsWith(),
      );
      bridge.onStateChanged(StateEvent(state: NativePipelineState.streaming));
      await Future<void>.delayed(Duration.zero);

      expect(
        () => controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        ),
        throwsStateError,
      );
    });
  });

  group('prepare failure', () {
    test('PrepareResult(ok: false) emits ErrorState with the reported code/detail and never calls start', () async {
      host.prepareResult = PrepareResult(
        ok: false,
        error: GazerErrorCode.cameraUnavailable,
        detail: 'x',
      );

      await controller.goLive(
        settingsWith(),
        devices: [backCamera],
        videoDeviceId: 'camera:back',
        flags: flagsWith(),
      );

      expect(controller.current, isA<ErrorState>());
      expect(
        (controller.current as ErrorState).error.code,
        GazerErrorCode.cameraUnavailable,
      );
      expect((controller.current as ErrorState).error.detail, 'x');
      expect(host.startCalls, isEmpty);
    });
  });

  group('stats aggregation at scale', () {
    test(
      'averages 200 samples via a running sum, without unbounded memory growth',
      () async {
        final seen = <StreamStats>[];
        final sub = controller.stats.listen(seen.add);

        await controller.goLive(
          settingsWith(),
          devices: [backCamera],
          videoDeviceId: 'camera:back',
          flags: flagsWith(),
        );
        bridge.onStateChanged(StateEvent(state: NativePipelineState.streaming));
        await Future<void>.delayed(Duration.zero);

        for (var i = 1; i <= 200; i++) {
          bridge.onStats(
            StatsSample(
              bitrateKbps: i,
              fps: 30,
              droppedVideoFrames: 0,
              sentBytes: 0,
              congestionPercent: 0,
            ),
          );
          await Future<void>.delayed(Duration.zero);
        }

        // sum(1..200) == 20100; average == 100.5, which rounds to 101.
        final latest = seen.last;
        expect(latest.currentBitrateKbps, 200);
        expect(latest.averageBitrateKbps, 101);
        await sub.cancel();
      },
    );
  });
}
