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
import 'package:gazer/services/pipeline_controller.dart';
import 'package:gazer/services/reconnect_policy.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  late FakeGazerHostApi hostApi;
  late FakeSettingsRepository settingsRepo;

  LicenseState license({required bool flagsSet}) => LicenseState(
    status: LicenseStatus.valid,
    flags: <String, bool>{
      'waddlebot.gazer.camera-stream': flagsSet,
      'waddlebot.gazer.uvc-capture': flagsSet,
      'waddlebot.gazer.adaptive-bitrate': flagsSet,
      'waddlebot.gazer.rtmp-auth': flagsSet,
    },
    lastFetched: flagsSet ? DateTime.utc(2026, 9, 7) : null,
    deviceId: 'test-device',
  );

  setUp(() {
    hostApi = FakeGazerHostApi()
      ..videoDevices = <VideoDevice>[
        VideoDevice(
          id: 'camera:back',
          kind: VideoDeviceKind.backCamera,
          name: 'Back Camera',
        ),
        VideoDevice(
          id: 'camera:front',
          kind: VideoDeviceKind.frontCamera,
          name: 'Front Camera',
        ),
      ];
    settingsRepo = FakeSettingsRepository(
      GazerSettings.defaults().copyWith(
        target: const StreamTargetSettings(
          url: 'rtmp://example.com/live/mystream',
        ),
      ),
    );
  });

  List<Override> overrides({required LicenseState license}) => <Override>[
    settingsRepositoryProvider.overrideWithValue(settingsRepo),
    gazerHostApiProvider.overrideWithValue(hostApi),
    // Wires hostApi.bridge into the controller under test so
    // hostApi.emitState(...) below actually reaches pipelineStateProvider
    // — see Task 11's FakeGazerHostApi doc (overriding gazerHostApiProvider
    // alone does not connect the two).
    pipelineControllerProvider.overrideWithValue(
      PipelineController(
        host: hostApi,
        events: hostApi.bridge,
        policy: ReconnectPolicy(),
      ),
    ),
    licenseClientProvider.overrideWith(
      (Ref ref) async => FakeLicenseClient(license),
    ),
    isOnlineProvider.overrideWith((Ref ref) => Stream<bool>.value(true)),
    updateCheckerProvider.overrideWith(
      (Ref ref) async => FakeUpdateChecker(null),
    ),
  ];

  testWidgets('source picker lists the fake devices', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: license(flagsSet: true)),
    );
    expect(find.text('Back camera'), findsOneWidget);
    expect(find.text('Front camera'), findsOneWidget);
  });

  testWidgets('Go Live is disabled when flags have not been fetched', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: LicenseState.initial('test-device')),
    );
    final FilledButton button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Go Live'),
    );
    expect(button.onPressed, isNull);
  });

  testWidgets('Go Live is enabled once settings and flags are valid', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: license(flagsSet: true)),
    );
    final FilledButton button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, 'Go Live'),
    );
    expect(button.onPressed, isNotNull);
  });

  testWidgets(
    'tapping Go Live calls prepare then start with the effective URL',
    (WidgetTester tester) async {
      await pumpGazerApp(
        tester,
        overrides: overrides(license: license(flagsSet: true)),
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
      await tester.pumpAndSettle();
      expect(hostApi.prepareCalls, hasLength(1));
      expect(hostApi.startCalls, hasLength(1));
      expect(hostApi.startCalls.single.url, 'rtmp://example.com/live/mystream');
    },
  );

  testWidgets('Stop appears while streaming', (WidgetTester tester) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: license(flagsSet: true)),
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.pumpAndSettle();
    // `emitState` awaits a real Future.delayed internally; testWidgets runs
    // inside a FakeAsync zone where a bare await never elapses on its own,
    // so real async work must run via `runAsync` (see fake_host_api.dart's
    // emitState doc — it targets both plain `test()` bodies, which run in a
    // real zone already, and `testWidgets`, which does not).
    await tester.runAsync(
      () => hostApi.emitState(NativePipelineState.streaming),
    );
    await tester.pumpAndSettle();
    expect(find.widgetWithText(FilledButton, 'Stop'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Go Live'), findsNothing);

    await tester.tap(find.widgetWithText(FilledButton, 'Stop'));
    await tester.pumpAndSettle();
    expect(hostApi.stopCallCount, 1);
  });

  testWidgets('selecting a different source is used by the next Go Live', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: license(flagsSet: true)),
    );
    await tester.tap(find.text('Front camera'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.pumpAndSettle();
    expect(hostApi.prepareCalls.single.videoDeviceId, 'camera:front');
  });

  testWidgets('re-entrant Go Live taps show a SnackBar and only prepare once', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: license(flagsSet: true)),
    );
    // `tester.tap` alone never rebuilds the tree, so tapping twice with no
    // intervening pump fires the same still-enabled "Go Live" button's
    // onPressed a second time while the first call's `goLive()` is
    // suspended at its first await (inside `_host.prepare`) — a
    // deterministic (not flaky) race against PipelineController's
    // `_goingLive` re-entrancy guard, which throws StateError.
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.pumpAndSettle();
    expect(hostApi.prepareCalls, hasLength(1));
    expect(
      find.text('Could not start the stream. Please try again.'),
      findsOneWidget,
    );
  });

  testWidgets(
    'a selected device that vanished before Go Live shows a SnackBar',
    (WidgetTester tester) async {
      await pumpGazerApp(
        tester,
        overrides: overrides(license: license(flagsSet: true)),
      );
      // The selection settles to 'camera:back' during the first build and
      // is never cleared by HomeScreen if the device list later changes
      // (M1 has no hot-plug refresh) — `canGoLive`'s `_selectedDeviceId !=
      // null` check does not re-verify the id is still in `devices`, so
      // this is exactly the gap PipelineController.goLive's own
      // `devices.any(...)` check (surfaced here as ArgumentError) defends.
      final BuildContext context = tester.element(find.byType(Scaffold));
      hostApi.videoDevices = <VideoDevice>[];
      ProviderScope.containerOf(
        context,
        listen: false,
      ).refresh(videoDevicesProvider);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
      await tester.pumpAndSettle();
      expect(hostApi.prepareCalls, isEmpty);
      expect(
        find.text('Could not start the stream. Please try again.'),
        findsOneWidget,
      );
    },
  );

  testWidgets('error state shows the localized message and action text', (
    WidgetTester tester,
  ) async {
    await pumpGazerApp(
      tester,
      overrides: overrides(license: license(flagsSet: true)),
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Go Live'));
    await tester.pumpAndSettle();
    // cameraUnavailable is not in ReconnectPolicy's retryable set, so the
    // controller emits ErrorState directly instead of a transient
    // ReconnectingState — see reconnect_policy.dart's shouldRetry table.
    await tester.runAsync(
      () => hostApi.emitState(
        NativePipelineState.error,
        error: GazerErrorCode.cameraUnavailable,
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('The camera is unavailable.'), findsOneWidget);
    expect(
      find.text('Check camera permission in system settings.'),
      findsOneWidget,
    );
  });
}
