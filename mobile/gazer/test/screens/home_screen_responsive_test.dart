import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `Override` (the type `ProviderScope.overrides` needs) is not part of
// flutter_riverpod 3.4.3's main barrel export — it moved to `misc.dart` in
// this pin, so it must be imported explicitly (see helpers/pump_app.dart).
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/telemetry_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/screens/status_panel.dart';
import 'package:gazer/telemetry/telemetry_config.dart';
import 'package:gazer/widgets/status_chip.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  List<Override> overrides() => <Override>[
    settingsRepositoryProvider.overrideWithValue(FakeSettingsRepository()),
    gazerHostApiProvider.overrideWithValue(FakeGazerHostApi()),
    licenseClientProvider.overrideWith(
      (Ref ref) async => FakeLicenseClient(LicenseState.initial('test-device')),
    ),
    isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
    updateCheckerProvider.overrideWith(
      (Ref ref) async => FakeUpdateChecker(null),
    ),
    telemetryConfigProvider.overrideWith(
      (Ref ref) async => const TelemetryConfig(
        endpoint: '',
        protocol: 'http/json',
        headers: <String, String>{},
        serviceName: 'gazer',
        serviceVersion: '0.0.0',
        deploymentEnvironment: 'test',
      ),
    ),
  ];

  testWidgets('phone width (390) shows the chip but not the side pane', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(390, 844),
    );
    expect(find.byType(StatusChip), findsOneWidget);
    expect(find.byType(StatusPanel), findsNothing);
  });

  testWidgets('tablet width (1280) shows the side pane', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(1280, 800),
    );
    expect(find.byType(StatusPanel), findsOneWidget);
  });
}
