import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `Override` is not part of flutter_riverpod 3.4.3's main barrel export —
// it moved to `misc.dart` in this pin (see helpers/pump_app.dart).
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/screens/home_screen.dart';
import 'package:gazer/screens/settings_screen.dart';
import 'package:gazer/services/keepalive_scheduler.dart';

import 'helpers/fake_host_api.dart';
import 'helpers/fakes.dart';
import 'helpers/pump_app.dart';

void main() {
  late FakeGazerHostApi hostApi;
  late FakeSettingsRepository settingsRepo;
  late FakeLicenseClient licenseClient;

  setUp(() {
    hostApi = FakeGazerHostApi();
    settingsRepo = FakeSettingsRepository();
    licenseClient = FakeLicenseClient(
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
    );
  });

  List<Override> overrides() => <Override>[
    settingsRepositoryProvider.overrideWithValue(settingsRepo),
    gazerHostApiProvider.overrideWithValue(hostApi),
    licenseClientProvider.overrideWith((Ref ref) async => licenseClient),
    isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
    updateCheckerProvider.overrideWith(
      (Ref ref) async => FakeUpdateChecker(null),
    ),
  ];

  testWidgets('app builds and shows HomeScreen at the initial route', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(tester, overrides: overrides());
    expect(find.byType(HomeScreen), findsOneWidget);
    expect(find.byType(SettingsScreen), findsNothing);
  });

  testWidgets('navigating to /settings shows SettingsScreen', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(tester, overrides: overrides());
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pumpAndSettle();
    expect(find.byType(SettingsScreen), findsOneWidget);
  });

  testWidgets(
    'keepalive scheduler starts after the first license fetch and stops on paused',
    (WidgetTester tester) async {
      late KeepaliveScheduler scheduler;
      await pumpGazerApp(
        tester,
        overrides: <Override>[
          ...overrides(),
          keepaliveSchedulerProvider.overrideWith((Ref ref) {
            scheduler = KeepaliveScheduler(
              ping: () async {},
              interval: const Duration(minutes: 5),
            );
            ref.onDispose(scheduler.stop);
            return scheduler;
          }),
        ],
      );

      expect(scheduler.isRunning, isTrue);

      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      expect(scheduler.isRunning, isFalse);
    },
  );
}
