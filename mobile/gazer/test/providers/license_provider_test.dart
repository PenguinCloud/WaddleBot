import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/services/license_client.dart';

class _FakeLicenseClient implements LicenseClient {
  _FakeLicenseClient(this.result);

  final LicenseState result;

  // LicenseClient is a concrete class with a public `baseUrl` field (part
  // of its implicit interface), so `implements LicenseClient` must supply
  // it too, unlike the task brief's sample which predates checking this
  // against the real LicenseClient shape.
  @override
  String get baseUrl => 'https://example.com';

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
        licenseClientProvider.overrideWith(
          (ref) async => _FakeLicenseClient(state),
        ),
      ],
    );
    addTearDown(container.dispose);

    await container.read(licenseProvider.future);
    final flags = container.read(featureFlagsProvider);

    expect(flags.isEnabled('waddlebot.gazer.camera-stream'), isTrue);
    expect(flags.isEnabled('waddlebot.gazer.uvc-capture'), isFalse);
    expect(flags.hasFetchedOnce, isTrue);
  });

  test(
    'featureFlagsProvider defaults every flag OFF before the fetch resolves',
    () async {
      final container = ProviderContainer(
        overrides: [
          licenseClientProvider.overrideWith(
            (ref) async =>
                _FakeLicenseClient(LicenseState.initial('device-abc')),
          ),
        ],
      );
      addTearDown(container.dispose);

      final flags = container.read(featureFlagsProvider);

      expect(flags.isEnabled('waddlebot.gazer.camera-stream'), isFalse);
      expect(flags.hasFetchedOnce, isFalse);
    },
  );
}
