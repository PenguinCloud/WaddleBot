import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `Override` (the type `ProviderScope.overrides` needs) is not part of
// flutter_riverpod 3.4.3's main barrel export — it moved to `misc.dart` in
// this pin, so it must be imported explicitly.
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/app.dart';

/// Pumps a fully-wired [GazerApp] under a [ProviderScope] carrying
/// [overrides].
///
/// When [size] is given, sets the test binding's `view.physicalSize` (and
/// pins `devicePixelRatio` to 1.0) before pumping, so responsive-layout
/// tests can drive the widget tree at a specific viewport (phone vs.
/// tablet breakpoints). The view is reset via [addTearDown] so later tests
/// in the same file are unaffected.
///
/// Resets [gazerRouter] to `'/'` before every pump: it is a top-level
/// singleton, so its current location otherwise persists across every
/// `testWidgets` in a file (they share one Dart isolate) — without this,
/// only the first test that navigates away from `'/'` actually starts at
/// HomeScreen, and every later one resumes wherever the previous test left
/// navigation.
Future<void> pumpGazerApp(
  WidgetTester t, {
  List<Override> overrides = const <Override>[],
  Size? size,
}) async {
  if (size != null) {
    t.view.physicalSize = size;
    t.view.devicePixelRatio = 1.0;
    addTearDown(t.view.reset);
  }
  gazerRouter.go('/');
  await t.pumpWidget(
    ProviderScope(overrides: overrides, child: const GazerApp()),
  );
  await t.pumpAndSettle();
}
