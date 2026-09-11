import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';

import 'package:gazer/app.dart';
import 'package:gazer/l10n/app_localizations.dart';
import 'package:gazer/models/pipeline_state.dart';
import 'package:gazer/providers/pipeline_provider.dart';
import 'package:gazer/providers/settings_provider.dart';

/// End-to-end "go live against an unreachable RTMP host" flow.
///
/// The Android emulator has no RTMP server and no route to a real one, so
/// this test cannot assert a live stream — it asserts the failure-handling
/// path: enter a loopback target nothing listens on, tap Go Live, watch the
/// pipeline reach ConnectingState then ReconnectingState(attempt: 1) within
/// ReconnectPolicy's first backoff window, then confirm Stop returns to
/// IdleState. Runs against the real app, the real Riverpod providers, and
/// the real Pigeon bridge to the on-device Kotlin GazerPipeline/RootEncoder
/// stack — nothing here is mocked.
void main() {
  final IntegrationTestWidgetsFlutterBinding binding =
      IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'go live against an unreachable RTMP host reaches Reconnecting(1), Stop returns to Idle',
    (WidgetTester tester) async {
      await tester.pumpWidget(const ProviderScope(child: GazerApp()));
      await tester.pumpAndSettle(const Duration(seconds: 5));

      final Element appElement = tester.element(find.byType(GazerApp));
      final ProviderContainer container = ProviderScope.containerOf(appElement);
      // `ProviderScope` genuinely is an ancestor of `GazerApp`, so
      // `containerOf(appElement)` above is correct. `AppLocalizations.of` is
      // not symmetric with it: it is `Localizations.of<AppLocalizations>(...)!`,
      // an *ancestor* lookup, and the `Localizations` widget is built by
      // `MaterialApp` *inside* `GazerApp` -- from `GazerApp`'s own element
      // there is no `Localizations` ancestor and the `!` throws. Resolve it
      // from a descendant instead: the settings gear lives in `HomeScreen`'s
      // `AppBar`, below `MaterialApp`, and is tapped on the very next line, so
      // it is guaranteed present and unambiguous here.
      final AppLocalizations l10n = AppLocalizations.of(
        tester.element(find.byKey(const Key('settingsGearButton'))),
      );

      // --- Settings: point at the emulator host loopback, nothing listens there ---
      await tester.tap(find.byKey(const Key('settingsGearButton')));
      await tester.pumpAndSettle();

      await tester.enterText(
        find.byKey(const Key('targetUrlField')),
        'rtmp://10.0.2.2:1935/live',
      );
      await tester.enterText(
        find.byKey(const Key('streamKeyField')),
        'demo-key-0001',
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('saveSettingsButton')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.settingsSavedMessage), findsOneWidget);

      final saved = await container.read(settingsProvider.future);
      expect(saved.target.url, 'rtmp://10.0.2.2:1935/live');
      expect(saved.target.streamKey, 'demo-key-0001');

      // --- Home: back camera, Go Live ---
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('backCameraOption')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.sourceBackCameraLabel), findsOneWidget);

      await tester.tap(find.byKey(const Key('goLiveButton')));
      await tester.pump(const Duration(milliseconds: 500));

      // --- Connecting ---
      final bool reachedConnecting = await _pumpUntil(
        tester,
        () => container.read(pipelineStateProvider).value is ConnectingState,
        timeout: const Duration(seconds: 5),
      );
      expect(
        reachedConnecting,
        isTrue,
        reason: 'expected ConnectingState shortly after Go Live',
      );
      expect(
        find.textContaining(l10n.statusChipConnectingLabel),
        findsOneWidget,
      );

      // --- Reconnecting (attempt 1), within ReconnectPolicy's first backoff window ---
      final bool reachedReconnecting = await _pumpUntil(tester, () {
        final PipelineState? state = container
            .read(pipelineStateProvider)
            .value;
        return state is ReconnectingState && state.attempt == 1;
      }, timeout: const Duration(seconds: 15));
      expect(
        reachedReconnecting,
        isTrue,
        reason:
            'expected ReconnectingState(attempt: 1) within 15s of a failed '
            'connection to an unreachable RTMP host',
      );
      expect(
        find.textContaining(l10n.statusChipReconnectingLabel),
        findsOneWidget,
      );

      // Android renders Flutter into a SurfaceView the screenshot API cannot
      // read back, so integration_test's IOCallbackManager throws
      // `Call convertFlutterSurfaceToImage() before taking a screenshot`
      // unless the surface is swapped for an ImageView first. The matching
      // revertFlutterImage is registered by convertFlutterSurfaceToImage
      // itself via addTearDown. `pump` (not `pumpAndSettle`) drives the frame
      // into that image: ReconnectPolicy's countdown timer keeps this tree
      // permanently unsettled, exactly as _pumpUntil's doc comment explains.
      await binding.convertFlutterSurfaceToImage();
      await tester.pump(const Duration(milliseconds: 500));
      await binding.takeScreenshot('go-live-unreachable');

      // --- Stop cancels the reconnect loop and returns to Idle ---
      await tester.tap(find.byKey(const Key('stopButton')));
      final bool backToIdle = await _pumpUntil(
        tester,
        () => container.read(pipelineStateProvider).value is IdleState,
        timeout: const Duration(seconds: 5),
      );
      expect(
        backToIdle,
        isTrue,
        reason: 'expected IdleState shortly after Stop',
      );
      await tester.pumpAndSettle();
      expect(find.textContaining(l10n.statusChipIdleLabel), findsOneWidget);
    },
  );
}

/// Pumps in short increments until [predicate] is true or [timeout]
/// elapses. `pumpAndSettle` alone cannot wait for the reconnect transition:
/// ReconnectPolicy's countdown timer keeps the tree "unsettled" indefinitely,
/// so a bounded polling pump is used instead.
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
