// Task 2 toolchain smoke test: proves flutter test runs end-to-end inside
// the gazer-toolchain container before any app code exists. Task 13
// replaces lib/main.dart with GazerApp; this test deliberately never
// imports it, so it keeps passing unmodified through that rewrite.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('smoke: MaterialApp renders content', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: Text('gazer')));

    expect(find.text('gazer'), findsOneWidget);
  });
}
