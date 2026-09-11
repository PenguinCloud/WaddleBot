import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `Override` (the type `ProviderScope.overrides` needs) is not part of
// flutter_riverpod 3.4.3's main barrel export — it moved to `misc.dart` in
// this pin, so it must be imported explicitly (see helpers/pump_app.dart).
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/stream_target_settings.dart';
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

/// Golden coverage for [StatusPanel] at the two breakpoints: phone
/// (bottom sheet, portrait) and tablet (persistent side pane, landscape).
///
/// Per the task brief: these run under `flutter_test`'s default test
/// font (no `flutter_test_config.dart`, no bundled Roboto) — deterministic
/// across every machine that runs `make mobile-run` regardless of host
/// fonts, so they verify layout and colour, not real glyph shapes. Real
/// glyphs are covered by the marketing-screenshots pass instead.
void main() {
  late FakeGazerHostApi hostApi;

  List<Override> overrides() => <Override>[
    settingsRepositoryProvider.overrideWithValue(
      FakeSettingsRepository(
        GazerSettings.defaults().copyWith(
          target: const StreamTargetSettings(
            url: 'rtmp://example.com/live/mystream',
            streamKey: 'demo-key-0001',
          ),
        ),
      ),
    ),
    gazerHostApiProvider.overrideWithValue(hostApi),
    licenseClientProvider.overrideWith(
      (Ref ref) async => FakeLicenseClient(
        LicenseState(
          status: LicenseStatus.valid,
          flags: const <String, bool>{
            'waddlebot.gazer.camera-stream': true,
            'waddlebot.gazer.uvc-capture': true,
            'waddlebot.gazer.adaptive-bitrate': true,
            'waddlebot.gazer.rtmp-auth': true,
          },
          lastFetched: DateTime.utc(2026, 9, 7),
          deviceId: 'test-device',
        ),
      ),
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

  setUp(() {
    hostApi = FakeGazerHostApi();
  });

  testWidgets('status panel — phone portrait', (WidgetTester tester) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(390, 844),
    );
    await tester.tap(find.byType(StatusChip));
    await tester.pumpAndSettle();
    await expectLater(
      find.byType(StatusPanel),
      matchesGoldenFile('status_panel_phone_portrait.png'),
    );
  });

  testWidgets('status panel — tablet landscape', (WidgetTester tester) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(1280, 800),
    );
    await expectLater(
      find.byType(StatusPanel),
      matchesGoldenFile('status_panel_tablet_landscape.png'),
    );
  });
}
