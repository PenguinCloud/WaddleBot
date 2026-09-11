import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/l10n/app_localizations.dart';
import 'package:gazer/pigeon/pipeline.g.dart';
import 'package:gazer/widgets/source_picker.dart';

final List<VideoDevice> _devices = <VideoDevice>[
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

void main() {
  testWidgets('renders one tile per device', (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SourcePicker(
            devices: _devices,
            selectedId: 'camera:back',
            onSelected: (_) {},
          ),
        ),
      ),
    );
    expect(find.byType(RadioListTile<String>), findsNWidgets(2));
    expect(find.text('Back camera'), findsOneWidget);
    expect(find.text('Front camera'), findsOneWidget);
  });

  testWidgets('tapping a tile calls onSelected with its id', (
    WidgetTester tester,
  ) async {
    String? selected;
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SourcePicker(
            devices: _devices,
            selectedId: null,
            onSelected: (String id) => selected = id,
          ),
        ),
      ),
    );
    await tester.tap(find.text('Front camera'));
    expect(selected, 'camera:front');
  });

  testWidgets('a UVC device falls back to its raw name (M2 kinds)', (
    WidgetTester tester,
  ) async {
    final List<VideoDevice> uvcDevices = <VideoDevice>[
      VideoDevice(
        id: 'uvc:1',
        kind: VideoDeviceKind.uvcCamera2,
        name: 'Elgato Cam Link',
      ),
    ];
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: SourcePicker(
            devices: uvcDevices,
            selectedId: null,
            onSelected: (_) {},
          ),
        ),
      ),
    );
    expect(find.text('Elgato Cam Link'), findsOneWidget);
  });
}
