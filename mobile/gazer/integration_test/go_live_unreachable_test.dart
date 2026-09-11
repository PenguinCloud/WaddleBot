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
      // `SettingsNotifier.save` is asynchronous -- a secure-storage write over
      // a platform channel -- and schedules no frames while it is in flight,
      // so `pumpAndSettle` returns *before* the confirmation SnackBar is ever
      // built and a plain `expect` right after it finds nothing. Poll for the
      // message instead; polling is also what keeps this robust on a
      // software-rendered emulator, where a single frame can take seconds and
      // a settle-then-assert can just as easily overshoot the SnackBar's own
      // ~4s auto-dismiss.
      final bool savedMessageShown = await _pumpUntil(
        tester,
        () => find.text(l10n.settingsSavedMessage).evaluate().isNotEmpty,
        timeout: const Duration(seconds: 15),
      );
      expect(
        savedMessageShown,
        isTrue,
        reason:
            'expected the "settings saved" confirmation SnackBar within 15s '
            'of tapping Save',
      );

      final saved = await container.read(settingsProvider.future);
      expect(saved.target.url, 'rtmp://10.0.2.2:1935/live');
      expect(saved.target.streamKey, 'demo-key-0001');

      // --- Home: back camera, Go Live ---
      await tester.pageBack();
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('backCameraOption')));
      await tester.pumpAndSettle();
      expect(find.text(l10n.sourceBackCameraLabel), findsOneWidget);

      // Go Live stays disabled until the first license/flag fetch resolves --
      // HomeScreen's canGoLive requires flags.hasFetchedOnce, and only the
      // resolved LicenseState carries a lastFetched. LicenseClient never
      // throws (an unreachable or rejecting license.penguintech.io degrades to
      // the offline fallback), but the round trip still has to *finish*, and
      // nothing earlier in this test waits for it. Wait for the button itself
      // rather than tapping a disabled one and then blaming the pipeline for
      // never reaching ConnectingState.
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
            'resolved and a camera was selected',
      );

      // Record every state the pipeline emits, from the provider's own stream,
      // starting before the tap. Snapshot polling cannot assert a *transition*
      // here: ReconnectPolicy's first backoff window is ~1s (base 1s, +/-20%
      // jitter) and on a software-rendered emulator one `tester.pump` can take
      // longer than that, so `container.read(...)` polling steps straight over
      // ReconnectingState(attempt: 1) even though it genuinely occurred. A
      // listener sees every emission, so the assertions below cannot miss one.
      final List<PipelineState> seenStates = <PipelineState>[];
      final ProviderSubscription<AsyncValue<PipelineState>> stateSubscription =
          container.listen<AsyncValue<PipelineState>>(pipelineStateProvider, (
            AsyncValue<PipelineState>? previous,
            AsyncValue<PipelineState> next,
          ) {
            final PipelineState? state = next.value;
            if (state != null) {
              seenStates.add(state);
            }
          });
      addTearDown(stateSubscription.close);

      await tester.tap(find.byKey(const Key('goLiveButton')));
      await tester.pump(const Duration(milliseconds: 500));

      // --- Connecting, then Reconnecting(attempt: 1) ---
      //
      // One accumulating poll rather than a chain of snapshot assertions.
      // Every stage of this flow is transient and the windows are short
      // relative to a frame on a software-rendered emulator: the RTMP connect
      // to an unreachable host is refused immediately, ReconnectPolicy's first
      // backoff window is ~1s, and each retry re-prepares the encoder (which
      // republishes PreparingState) before reconnecting. A snapshot
      // `expect(find.textContaining(...), findsOneWidget)` therefore asserts
      // whatever happens to be on screen at one arbitrary instant. Recording
      // every chip label seen and every state emitted, and asserting against
      // the accumulated evidence, asserts the same three facts -- the pipeline
      // reached Connecting, it reached ReconnectingState(attempt: 1), and the
      // chip rendered both -- without depending on catching any one of them in
      // a single frame. ReconnectPolicy doubles each backoff window, so the
      // evidence set fills in within a few cycles.
      final Set<String> chipLabelsSeen = <String>{};
      final bool sawConnectAndReconnect = await _pumpUntil(tester, () {
        final String? label = _currentChipLabel(tester);
        if (label != null) {
          chipLabelsSeen.add(label);
        }
        return chipLabelsSeen.contains(l10n.statusChipConnectingLabel) &&
            chipLabelsSeen.contains(l10n.statusChipReconnectingLabel) &&
            seenStates.any((PipelineState s) => s is ConnectingState) &&
            seenStates.any(
              (PipelineState s) => s is ReconnectingState && s.attempt == 1,
            );
      }, timeout: const Duration(seconds: 90));
      expect(
        sawConnectAndReconnect,
        isTrue,
        reason:
            'expected the pipeline to reach ConnectingState and then '
            'ReconnectingState(attempt: 1) against an unreachable RTMP host, '
            'with the status chip rendering both '
            '"${l10n.statusChipConnectingLabel}" and '
            '"${l10n.statusChipReconnectingLabel}". '
            'Chip labels seen: $chipLabelsSeen. '
            'States seen: ${seenStates.map((PipelineState s) => s.runtimeType).toList()}',
      );

      // Hold until a reconnect backoff window is actually on screen, so the
      // screenshot below captures the reconnecting UI rather than whatever the
      // retry loop happens to be doing.
      final bool reconnectingOnScreen = await _pumpUntil(
        tester,
        () => _currentChipLabel(tester) == l10n.statusChipReconnectingLabel,
        timeout: const Duration(seconds: 60),
      );
      expect(
        reconnectingOnScreen,
        isTrue,
        reason:
            'expected the status chip to be showing '
            '"${l10n.statusChipReconnectingLabel}" when the screenshot is taken',
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
      // Stop is only rendered while the pipeline is connecting/streaming/
      // reconnecting; taking the screenshot above costs frames, so re-confirm
      // the button is on screen instead of tapping into empty space.
      final bool stopShown = await _pumpUntil(
        tester,
        () => find.byKey(const Key('stopButton')).evaluate().isNotEmpty,
        timeout: const Duration(seconds: 15),
      );
      expect(stopShown, isTrue, reason: 'expected the Stop button on screen');
      await tester.tap(find.byKey(const Key('stopButton')));
      // `PipelineController.stop` emits Idle only after the native
      // `GazerPipeline.stop()` round trip returns, and that call tears down
      // the RootEncoder engine (stopStream + release, a camera close and two
      // MediaCodec releases). On a software-rendered emulator mid-reconnect
      // that takes well over the couple of seconds it takes on real hardware,
      // so bound this generously rather than asserting a wall-clock budget
      // this test was never written to measure.
      final bool backToIdle = await _pumpUntil(
        tester,
        () => seenStates.any((PipelineState s) => s is IdleState),
        timeout: const Duration(seconds: 45),
      );
      expect(
        backToIdle,
        isTrue,
        reason:
            'expected IdleState after Stop. '
            'States seen: ${seenStates.map((PipelineState s) => s.runtimeType).toList()}',
      );
      final Set<String?> idleChipLabelsSeen = <String?>{};
      final bool idleShown = await _pumpUntil(tester, () {
        final String? label = _currentChipLabel(tester);
        idleChipLabelsSeen.add(label);
        return label == l10n.statusChipIdleLabel;
      }, timeout: const Duration(seconds: 30));
      expect(
        idleShown,
        isTrue,
        reason:
            'expected the status chip to settle on '
            '"${l10n.statusChipIdleLabel}" after Stop. '
            'Chip labels seen after Stop: $idleChipLabelsSeen. '
            'States seen: ${seenStates.map((PipelineState s) => s.runtimeType).toList()}',
      );
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

/// The text currently rendered inside the status chip, or null when the chip
/// (or its label) is not in the tree. Read through the chip's own key rather
/// than a bare text finder so a label that also appears elsewhere in the tree
/// can never be mistaken for the chip's own state.
String? _currentChipLabel(WidgetTester tester) {
  final Finder chip = find.byKey(const Key('statusChip'));
  if (chip.evaluate().isEmpty) {
    return null;
  }
  final Iterable<Element> labels = find
      .descendant(of: chip, matching: find.byType(Text))
      .evaluate();
  if (labels.isEmpty) {
    return null;
  }
  return (labels.first.widget as Text).data;
}
