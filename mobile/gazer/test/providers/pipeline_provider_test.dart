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
    final controller = PipelineController(
      host: host,
      events: bridge,
      policy: ReconnectPolicy(),
    );
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

    bridge.onStateChanged(StateEvent(state: NativePipelineState.preparing));
    await Future<void>.delayed(Duration.zero);

    expect(seen.first, const IdleState());
    expect(seen.last, const PreparingState());
    sub.close();
  });
}
