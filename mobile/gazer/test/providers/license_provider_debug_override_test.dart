import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:gazer/config/debug_overrides.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/services/license_client.dart';

class MockLicenseClient extends Mock implements LicenseClient {}

void main() {
  test('license() force-enables DebugOverrides.flags, status valid, lastFetched set, only when enabled', () async {
    final MockLicenseClient client = MockLicenseClient();
    final LicenseState base = LicenseState(
      status: LicenseStatus.unknown,
      flags: const <String, bool>{},
      lastFetched: null,
      deviceId: 'test-device-0001',
    );
    when(() => client.validateAndFetchFlags()).thenAnswer((_) async => base);

    final ProviderContainer container = ProviderContainer(
      overrides: [licenseClientProvider.overrideWith((ref) async => client)],
    );
    addTearDown(container.dispose);

    final LicenseState result = await container.read(licenseProvider.future);

    if (DebugOverrides.enabled) {
      expect(result.status, LicenseStatus.valid);
      expect(result.lastFetched, isNotNull);
      for (final String key in DebugOverrides.flags) {
        expect(result.flags[key], isTrue, reason: 'flag $key must be forced ON');
      }
    } else {
      expect(result.status, base.status);
      expect(result.flags, equals(base.flags));
      expect(result.lastFetched, base.lastFetched);
    }
  });
}
