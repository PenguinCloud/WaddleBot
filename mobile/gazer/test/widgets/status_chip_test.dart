import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/l10n/app_localizations.dart';
import 'package:gazer/models/pipeline_state.dart';
import 'package:gazer/widgets/status_chip.dart';

Widget _wrap(Widget child) => MaterialApp(
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  home: Scaffold(body: child),
);

void main() {
  testWidgets('renders the correct color and label per state', (
    WidgetTester tester,
  ) async {
    final Map<PipelineState, Color> expected = <PipelineState, Color>{
      const IdleState(): Colors.grey,
      const PreparingState(): Colors.amber,
      const ConnectingState(): Colors.blue,
      const StreamingState(): Colors.green,
      const ReconnectingState(1, Duration(seconds: 1)): Colors.orange,
      const ErrorState(GazerError(code: GazerErrorCode.unknown)): Colors.red,
    };
    for (final MapEntry<PipelineState, Color> entry in expected.entries) {
      await tester.pumpWidget(
        _wrap(StatusChip(state: entry.key, onTap: () {})),
      );
      final Chip chip = tester.widget<Chip>(find.byType(Chip));
      expect(chip.backgroundColor, entry.value, reason: '${entry.key}');
    }
  });

  testWidgets('tapping the chip invokes onTap', (WidgetTester tester) async {
    bool tapped = false;
    await tester.pumpWidget(
      _wrap(StatusChip(state: const IdleState(), onTap: () => tapped = true)),
    );
    await tester.tap(find.byType(StatusChip));
    expect(tapped, isTrue);
  });
}
