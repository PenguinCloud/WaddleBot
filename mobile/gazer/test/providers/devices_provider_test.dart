import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/providers/devices_provider.dart';

import '../helpers/fake_host_api.dart';

void main() {
  test(
    'videoDevicesProvider forwards GazerHostApi.listVideoDevices()',
    () async {
      final host = FakeGazerHostApi();
      final container = ProviderContainer(
        overrides: [gazerHostApiProvider.overrideWithValue(host)],
      );
      addTearDown(container.dispose);

      final devices = await container.read(videoDevicesProvider.future);

      expect(devices, isEmpty);
      expect(host.calls, contains('listVideoDevices'));
    },
  );

  test(
    'audioDevicesProvider forwards GazerHostApi.listAudioDevices()',
    () async {
      final host = FakeGazerHostApi();
      final container = ProviderContainer(
        overrides: [gazerHostApiProvider.overrideWithValue(host)],
      );
      addTearDown(container.dispose);

      final devices = await container.read(audioDevicesProvider.future);

      expect(devices, isEmpty);
      expect(host.calls, contains('listAudioDevices'));
    },
  );
}
