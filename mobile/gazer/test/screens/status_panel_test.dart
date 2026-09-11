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
import 'package:gazer/pigeon/pipeline.g.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/screens/status_panel.dart';
import 'package:gazer/services/pipeline_controller.dart';
import 'package:gazer/services/reconnect_policy.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  late FakeGazerHostApi hostApi;
  late FakeSettingsRepository settingsRepo;

  setUp(() {
    hostApi = FakeGazerHostApi();
    settingsRepo = FakeSettingsRepository(
      GazerSettings.defaults().copyWith(
        target: const StreamTargetSettings(
          url: 'rtmp://example.com/live/mystream',
          streamKey: 'demo-key-0001',
        ),
      ),
    );
  });

  List<Override> overrides() => <Override>[
    settingsRepositoryProvider.overrideWithValue(settingsRepo),
    gazerHostApiProvider.overrideWithValue(hostApi),
    // Wires hostApi.bridge into the controller under test so
    // hostApi.emitStats(...) below actually reaches streamStatsProvider
    // — see Task 11's FakeGazerHostApi doc.
    pipelineControllerProvider.overrideWithValue(
      PipelineController(
        host: hostApi,
        events: hostApi.bridge,
        policy: ReconnectPolicy(),
      ),
    ),
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
  ];

  testWidgets('phone layout shows the chip and opens a bottom sheet', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(390, 844),
    );
    expect(find.byType(StatusPanel), findsNothing);
    await tester.tap(find.text('Idle'));
    await tester.pumpAndSettle();
    expect(find.byType(StatusPanel), findsOneWidget);
    expect(find.text('No capture card connected'), findsOneWidget);
  });

  testWidgets('tablet layout shows the panel as a persistent pane', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(1280, 800),
    );
    expect(find.byType(StatusPanel), findsOneWidget);
  });

  testWidgets('renders live stats from a stats sample', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(1280, 800),
    );
    // FakeGazerHostApi.emitStats awaits a real Future.delayed internally;
    // testWidgets runs inside a FakeAsync zone where a bare await never
    // elapses on its own, so real async work must run via `runAsync` (see
    // fake_host_api.dart's emitState/emitStats doc).
    await tester.runAsync(
      () => hostApi.emitStats(
        StatsSample(
          bitrateKbps: 2200,
          fps: 29.8,
          droppedVideoFrames: 3,
          sentBytes: 1000,
          congestionPercent: 0,
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.textContaining('2200'), findsOneWidget);
  });

  testWidgets('masked stream key shows only the last 4 characters', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(),
      size: const Size(1280, 800),
    );
    expect(find.text('•••••••••0001'), findsOneWidget);
    expect(find.text('demo-key-0001'), findsNothing);
  });
}
