import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/l10n/app_localizations.dart';
import 'package:gazer/screens/status_panel.dart';

void main() {
  testWidgets('showStatusPanel opens a bottom sheet showing StatusPanel', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (BuildContext context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () => showStatusPanel(context),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.byType(StatusPanel), findsOneWidget);
    expect(find.text('Status'), findsOneWidget);
  });
}
