import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/widgets/masked_text.dart';

void main() {
  testWidgets('shows only the last 4 characters by default', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: MaskedText(value: 'abcd1234efgh', revealSemanticsLabel: 'Show'),
        ),
      ),
    );
    expect(find.text('••••••••efgh'), findsOneWidget);
    expect(find.text('abcd1234efgh'), findsNothing);
  });

  testWidgets('reveals the full value when tapped', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: MaskedText(value: 'abcd1234efgh', revealSemanticsLabel: 'Show'),
        ),
      ),
    );
    await tester.tap(find.byIcon(Icons.visibility));
    await tester.pump();
    expect(find.text('abcd1234efgh'), findsOneWidget);
  });
}
