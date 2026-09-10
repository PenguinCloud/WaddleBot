import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/services/feature_flags.dart';

void main() {
  group('FeatureFlags.isEnabled', () {
    test('a never-seen flag key is false', () {
      final flags = FeatureFlags(
        LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ),
      );
      expect(flags.isEnabled('waddlebot.gazer.rtmp-auth'), isFalse);
    });

    test('a known-true flag key is true', () {
      final flags = FeatureFlags(
        LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ),
      );
      expect(flags.isEnabled('waddlebot.gazer.camera-stream'), isTrue);
    });
  });

  group('FeatureFlags.hasFetchedOnce', () {
    test('is false before any successful fetch', () {
      final flags = FeatureFlags(LicenseState.initial('device-abc'));
      expect(flags.hasFetchedOnce, isFalse);
    });

    test('is true once lastFetched is set', () {
      final flags = FeatureFlags(
        LicenseState(
          status: LicenseStatus.valid,
          flags: const {},
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'device-abc',
        ),
      );
      expect(flags.hasFetchedOnce, isTrue);
    });
  });
}
