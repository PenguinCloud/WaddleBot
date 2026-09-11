import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:gazer/app.dart';

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

  testWidgets('capture docs/screenshots/gazer marketing set ($_formFactor)', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: GazerApp()));
    await tester.pumpAndSettle(const Duration(seconds: 5));

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
    await binding.takeScreenshot(_formFactor == 'phone' ? 'home-idle-phone' : 'home-tablet');

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
