import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/license_state.dart';

void main() {
  group('LicenseState.initial', () {
    test('is unknown status, no flags, never fetched', () {
      final initial = LicenseState.initial('device-abc');
      expect(initial.status, LicenseStatus.unknown);
      expect(initial.flags, isEmpty);
      expect(initial.lastFetched, isNull);
      expect(initial.deviceId, 'device-abc');
    });
  });

  group('LicenseState JSON round-trip', () {
    test('toJson/fromJson preserves status, flags map, and lastFetched', () {
      final original = LicenseState(
        status: LicenseStatus.valid,
        flags: const {
          'waddlebot.gazer.camera-stream': true,
          'waddlebot.gazer.uvc-capture': false,
        },
        lastFetched: DateTime.utc(2026, 9, 7, 12, 30),
        deviceId: 'device-abc',
      );
      final restored = LicenseState.fromJson(original.toJson());
      expect(restored, original);
    });

    test('null lastFetched round-trips as null', () {
      final original = LicenseState.initial('device-abc');
      final restored = LicenseState.fromJson(original.toJson());
      expect(restored.lastFetched, isNull);
    });
  });

  group('LicenseState equality', () {
    test('two instances with identical fields are ==', () {
      final a = LicenseState.initial('device-abc');
      final b = LicenseState.initial('device-abc');
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing deviceId breaks equality', () {
      final a = LicenseState.initial('device-abc');
      final b = LicenseState.initial('device-xyz');
      expect(a == b, isFalse);
    });
  });

  group('LicenseStatus', () {
    test('has exactly the four supported values', () {
      expect(LicenseStatus.values, [
        LicenseStatus.unknown,
        LicenseStatus.valid,
        LicenseStatus.gracePeriod,
        LicenseStatus.invalid,
      ]);
    });
  });
}
