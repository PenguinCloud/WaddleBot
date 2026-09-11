import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:gazer/app.dart';
import 'package:gazer/config/seed.dart';
import 'package:gazer/services/settings_repository.dart';

/// Which physical form factor this capture run targets, set at build time
/// via `--dart-define=GAZER_SCREENSHOT_FORM_FACTOR=phone|tablet`. Controls
/// only which named screenshots this run captures — both runs execute the
/// same widget flow; the emulator/AVD chosen for each run (gazer_ci vs.
/// gazer_tablet, see scripts/mobile_screenshots_entrypoint.sh) supplies the
/// actual phone-vs-tablet screen size that drives StatusPanel's responsive
/// layout.
const String _formFactor = String.fromEnvironment(
  'GAZER_SCREENSHOT_FORM_FACTOR',
  defaultValue: 'phone',
);

void main() {
  final IntegrationTestWidgetsFlutterBinding binding =
      IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('capture docs/screenshots/gazer marketing set ($_formFactor)', (
    WidgetTester tester,
  ) async {
    // `flutter build apk --target=integration_test/screenshots_test.dart`
    // makes THIS file's `main()` the app's actual Dart entrypoint --
    // lib/main.dart (and its applySeedIfRequested call before runApp) never
    // executes in this flow, exactly like every other integration_test/
    // entrypoint in this app (see go_live_unreachable_test.dart, which
    // populates settings via the UI instead for the same reason). Seed the
    // same underlying platform storage GazerApp's own SecureSettingsRepository
    // will read from, directly, before pumping the widget tree.
    await applySeedIfRequested(
      SecureSettingsRepository(
        secure: const FlutterSecureStorage(),
        prefs: SharedPreferencesAsync(),
      ),
    );

    await tester.pumpWidget(const ProviderScope(child: GazerApp()));
    await tester.pumpAndSettle(const Duration(seconds: 5));

    // Wait for the license/flag fetch to resolve before capturing anything.
    // DebugOverrides (providers/license_provider.dart) forces the M1 flags
    // ON once that fetch completes -- success or degraded, it never throws
    // -- via the --dart-define=GAZER_FLAGS_OVERRIDE set at build time (see
    // mobile_screenshots_entrypoint.sh's FLAGS_DEFINE). Until it resolves,
    // Go Live stays disabled and the status panel's License row is stuck on
    // "Fetching features...". pumpAndSettle cannot wait for a real network
    // round trip; poll instead, same pattern and timeout as
    // go_live_unreachable_test.dart's wait for goLiveButton to enable.
    final bool goLiveEnabled = await _pumpUntil(
      tester,
      () =>
          tester
              .widget<FilledButton>(find.byKey(const Key('goLiveButton')))
              .onPressed !=
          null,
      timeout: const Duration(seconds: 60),
    );
    expect(
      goLiveEnabled,
      isTrue,
      reason:
          'expected Go Live to become enabled once the license/flag fetch '
          'resolved, so screenshots reflect a settled state rather than a '
          'stalled "Fetching features..." license row',
    );

    // Android renders Flutter into a SurfaceView the screenshot API cannot
    // read back, so integration_test's IOCallbackManager throws
    // `Call convertFlutterSurfaceToImage() before taking a screenshot`
    // unless the surface is swapped for an ImageView first (see
    // go_live_unreachable_test.dart for the single-screenshot precedent).
    // Called once, before the first capture: the converted image surface
    // keeps serving every subsequent `takeScreenshot` call in this same
    // test, so it does not need to be repeated per-screenshot.
    await binding.convertFlutterSurfaceToImage();
    await tester.pump();

    // Home, idle, mock target/quality already seeded by --dart-define=GAZER_SEED=true at launch.
    // Phone keeps the historical "home-idle-phone" name; tablet uses "home-tablet" to match
    // the fixed 5-file marketing set (see the Produces line and collect_screenshots.sh NAMES).
    await binding.takeScreenshot(
      _formFactor == 'phone' ? 'home-idle-phone' : 'home-tablet',
    );

    if (_formFactor == 'phone') {
      await tester.tap(find.byKey(const Key('settingsGearButton')));
      await tester.pumpAndSettle();
      await binding.takeScreenshot('settings-$_formFactor');
      await tester.pageBack();
      await tester.pumpAndSettle();
    }

    await tester.tap(find.byKey(const Key('statusChip')));
    await tester.pumpAndSettle();
    await binding.takeScreenshot('status-panel-$_formFactor');
  });
}

/// Pumps in short increments until [predicate] is true or [timeout]
/// elapses. Mirrors go_live_unreachable_test.dart's helper of the same
/// name/signature (private to each file — not shared across
/// integration_test/ entrypoints).
Future<bool> _pumpUntil(
  WidgetTester tester,
  bool Function() predicate, {
  required Duration timeout,
  Duration step = const Duration(milliseconds: 250),
}) async {
  final Stopwatch sw = Stopwatch()..start();
  while (sw.elapsed < timeout) {
    await tester.pump(step);
    if (predicate()) return true;
  }
  return false;
}
