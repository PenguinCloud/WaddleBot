import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../models/pipeline_state.dart';
import '../models/stream_stats.dart';
import '../pigeon/pipeline.g.dart';
import '../services/native_event_bridge.dart';
import '../services/permission_gate.dart';
import '../services/pipeline_controller.dart';
import '../services/reconnect_policy.dart';
import 'devices_provider.dart';

part 'pipeline_provider.g.dart';

/// Owns the [PipelineController] for the app's lifetime; overridden in
/// provider/widget tests with a controller wired to `FakeGazerHostApi`.
///
/// The real controller is built on [gazerHostApiProvider]'s [GazerHostApi]
/// (the Pigeon default messenger) and a fresh [NativeEventBridge]. The
/// bridge is registered with [GazerFlutterApi.setUp] so Kotlin -> Dart
/// pushes on the real platform channel actually reach it — constructing a
/// `NativeEventBridge` alone does not wire it to anything. Both the
/// `setUp` registration and the bridge's own streams are torn down
/// alongside the controller on [Ref.onDispose].
@Riverpod(keepAlive: true)
PipelineController pipelineController(Ref ref) {
  final events = NativeEventBridge();
  GazerFlutterApi.setUp(events);
  final controller = PipelineController(
    host: ref.watch(gazerHostApiProvider),
    events: events,
    policy: ReconnectPolicy(),
  );
  ref.onDispose(() {
    GazerFlutterApi.setUp(null);
    controller.dispose();
    events.dispose();
  });
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

/// The [PermissionGate] HomeScreen's Go Live handler consults before ever
/// calling [PipelineController.goLive]; overridden with a fake in widget
/// tests so no real `permission_handler` platform channel is ever hit.
@Riverpod(keepAlive: true)
PermissionGate permissionGate(Ref ref) => PermissionHandlerGate();
