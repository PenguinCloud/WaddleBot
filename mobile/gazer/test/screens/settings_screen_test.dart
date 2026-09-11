import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `Override` is not part of flutter_riverpod 3.4.3's main barrel export —
// it moved to `misc.dart` in this pin (see helpers/pump_app.dart).
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/quality.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:gazer/providers/devices_provider.dart';
import 'package:gazer/providers/license_provider.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../helpers/fake_host_api.dart';
import '../helpers/fakes.dart';
import '../helpers/pump_app.dart';

void main() {
  late FakeSettingsRepository settingsRepo;

  setUpAll(() {
    // SettingsScreen's version footer calls `PackageInfo.fromPlatform()`
    // directly (not through an overridable provider); this mock avoids a
    // real platform-channel call and gives the footer/ConsoleVersion a
    // real version string to render in these tests.
    PackageInfo.setMockInitialValues(
      appName: 'Gazer',
      packageName: 'io.waddlebot.gazer',
      version: '1.2.3',
      buildNumber: '1',
      buildSignature: '',
    );
  });

  List<Override> overrides({bool rtmpAuthEnabled = true}) => <Override>[
    settingsRepositoryProvider.overrideWithValue(settingsRepo),
    gazerHostApiProvider.overrideWithValue(FakeGazerHostApi()),
    licenseClientProvider.overrideWith(
      (Ref ref) async => FakeLicenseClient(
        LicenseState(
          status: LicenseStatus.valid,
          flags: <String, bool>{
            'waddlebot.gazer.camera-stream': true,
            'waddlebot.gazer.uvc-capture': true,
            'waddlebot.gazer.adaptive-bitrate': true,
            'waddlebot.gazer.rtmp-auth': rtmpAuthEnabled,
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

  setUp(() {
    settingsRepo = FakeSettingsRepository();
  });

  Future<void> pumpSettings(
    WidgetTester tester, {
    bool rtmpAuthEnabled = true,
  }) async {
    // Default 800x600 test viewport is shorter than this form (Save ends
    // up off-screen, so a tap on it silently misses); a taller viewport
    // keeps every control reachable without extra `ensureVisible` calls.
    await pumpGazerApp(
      tester,
      overrides: overrides(rtmpAuthEnabled: rtmpAuthEnabled),
      size: const Size(800, 1600),
    );
    await tester.tap(find.byIcon(Icons.settings));
    await tester.pumpAndSettle();
  }

  testWidgets('invalid URL shows an error and blocks save', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'RTMP URL'),
      'http://bad',
    );
    await tester.pump();
    expect(
      find.text('URL must start with rtmp:// or rtmps://'),
      findsOneWidget,
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pump();
    expect(settingsRepo.saved, isEmpty);
  });

  testWidgets('valid URL saves through the settings repository', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'RTMP URL'),
      'rtmp://example.com/live/mystream',
    );
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(settingsRepo.saved, hasLength(1));
    expect(
      settingsRepo.saved.single.target.url,
      'rtmp://example.com/live/mystream',
    );
  });

  testWidgets('bitrate slider snaps to 100kbps steps', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);
    final Slider slider = tester.widget<Slider>(find.byType(Slider));
    expect(slider.divisions, 45); // (5000 - 500) / 100
    expect(slider.min, 500);
    expect(slider.max, 5000);
  });

  testWidgets('username without password shows the both-or-neither error', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);
    await tester.enterText(
      find.widgetWithText(TextFormField, 'RTMP URL'),
      'rtmp://example.com/live/mystream',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'Username'),
      'alice',
    );
    await tester.pump();
    expect(
      find.text('Enter both username and password, or leave both blank'),
      findsOneWidget,
    );
  });

  testWidgets('secrets are obscured by default', (WidgetTester tester) async {
    await pumpSettings(tester);
    // `TextFormField` (unlike `TextField`) does not expose `obscureText` as
    // a retrievable field on itself — it only forwards the value to the
    // `TextField` it builds internally — so the assertion targets that
    // descendant `TextField` instead.
    final TextField keyField = tester.widget<TextField>(
      find.descendant(
        of: find.widgetWithText(TextFormField, 'Stream Key'),
        matching: find.byType(TextField),
      ),
    );
    final TextField pwField = tester.widget<TextField>(
      find.descendant(
        of: find.widgetWithText(TextFormField, 'Password'),
        matching: find.byType(TextField),
      ),
    );
    expect(keyField.obscureText, isTrue);
    expect(pwField.obscureText, isTrue);
  });

  testWidgets(
    'stream key and password reveal toggles show the full value and accept edits',
    (WidgetTester tester) async {
      await pumpSettings(tester);
      await tester.enterText(
        find.byKey(const Key('streamKeyField')),
        'supersecretkey',
      );
      await tester.enterText(find.byKey(const Key('passwordField')), 'hunter2');
      await tester.pump();

      await tester.tap(find.byKey(const Key('streamKeyRevealButton')));
      await tester.tap(find.byKey(const Key('passwordRevealButton')));
      await tester.pump();

      final TextField keyField = tester.widget<TextField>(
        find.descendant(
          of: find.byKey(const Key('streamKeyField')),
          matching: find.byType(TextField),
        ),
      );
      final TextField pwField = tester.widget<TextField>(
        find.descendant(
          of: find.byKey(const Key('passwordField')),
          matching: find.byType(TextField),
        ),
      );
      expect(keyField.obscureText, isFalse);
      expect(pwField.obscureText, isFalse);
    },
  );

  testWidgets('quality controls update the draft settings', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);

    final DropdownButtonFormField<Resolution> resolutionField = tester.widget(
      find.byKey(const Key('resolutionField')),
    );
    resolutionField.onChanged!(Resolution.p720);
    await tester.pump();
    expect(find.text('720p'), findsWidgets);

    final SegmentedButton<FrameRate> frameRateField = tester.widget(
      find.byKey(const Key('frameRateField')),
    );
    frameRateField.onSelectionChanged!(<FrameRate>{FrameRate.fps60});
    await tester.pump();
    expect(find.text('60 fps'), findsWidgets);

    final Slider slider = tester.widget(find.byKey(const Key('bitrateSlider')));
    slider.onChanged!(3200);
    await tester.pump();
    expect(find.text('Video Bitrate: 3200 kbps'), findsOneWidget);

    final SwitchListTile adaptiveSwitch = tester.widget(
      find.byKey(const Key('adaptiveBitrateSwitch')),
    );
    expect(adaptiveSwitch.value, isTrue);
    adaptiveSwitch.onChanged!(false);
    await tester.pump();

    final DropdownButtonFormField<AudioSourceChoice> audioField = tester.widget(
      find.byKey(const Key('audioSourceField')),
    );
    audioField.onChanged!(AudioSourceChoice.mic);
    await tester.pump();
    expect(find.text('Phone Microphone'), findsWidgets);
  });

  testWidgets(
    'long-pressing the version footer reveals the developer section',
    (WidgetTester tester) async {
      await pumpSettings(tester);
      expect(find.byKey(const Key('forceLibuvcSwitch')), findsNothing);

      await tester.longPress(find.byKey(const Key('versionFooter')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('forceLibuvcSwitch')), findsOneWidget);
      final SwitchListTile forceSwitch = tester.widget(
        find.byKey(const Key('forceLibuvcSwitch')),
      );
      expect(forceSwitch.value, isFalse);
      forceSwitch.onChanged!(true);
      await tester.pump();
    },
  );

  testWidgets('shows the fetched app version in the footer', (
    WidgetTester tester,
  ) async {
    await pumpSettings(tester);
    expect(find.text('Version 1.2.3'), findsOneWidget);
  });

  testWidgets(
    'rtmp-auth disabled with credentials shows the disabled-auth error',
    (WidgetTester tester) async {
      await pumpSettings(tester, rtmpAuthEnabled: false);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'RTMP URL'),
        'rtmp://example.com/live/mystream',
      );
      await tester.enterText(find.byKey(const Key('usernameField')), 'alice');
      await tester.enterText(find.byKey(const Key('passwordField')), 'secret');
      await tester.pump();
      expect(
        find.text(
          'Username/password authentication is not enabled for this license tier',
        ),
        findsOneWidget,
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pump();
      expect(settingsRepo.saved, isEmpty);
    },
  );

  testWidgets(
    'a save failure shows an error SnackBar and leaves the draft unsaved',
    (WidgetTester tester) async {
      await pumpSettings(tester);
      await tester.enterText(
        find.widgetWithText(TextFormField, 'RTMP URL'),
        'rtmp://example.com/live/mystream',
      );
      await tester.pump();

      settingsRepo.saveError = StateError('disk full');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();

      expect(
        find.text('Failed to save settings. Please try again.'),
        findsOneWidget,
      );
      expect(settingsRepo.saved, isEmpty);
    },
  );
}
