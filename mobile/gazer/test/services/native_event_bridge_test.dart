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

    bridge.onStateChanged(StateEvent(state: NativePipelineState.streaming));
    await Future<void>.delayed(Duration.zero);

    expect(events, hasLength(1));
    expect(events.single.state, NativePipelineState.streaming);
    await sub.cancel();
  });

  test('onStats forwards to stats', () async {
    final samples = <StatsSample>[];
    final sub = bridge.stats.listen(samples.add);

    bridge.onStats(
      StatsSample(
        bitrateKbps: 2000,
        fps: 30,
        droppedVideoFrames: 0,
        sentBytes: 100,
        congestionPercent: 0,
      ),
    );
    await Future<void>.delayed(Duration.zero);

    expect(samples, hasLength(1));
    expect(samples.single.bitrateKbps, 2000);
    await sub.cancel();
  });

  test('onUsbAttached forwards to usbAttached', () async {
    final devices = <VideoDevice>[];
    final sub = bridge.usbAttached.listen(devices.add);

    bridge.onUsbAttached(
      VideoDevice(
        id: 'uvc:1',
        kind: VideoDeviceKind.uvcCamera2,
        name: 'UGREEN Capture',
      ),
    );
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
