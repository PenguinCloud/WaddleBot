import 'package:flutter/foundation.dart';

/// Debug-only feature-flag override sourced from a `--dart-define` at
/// build/test time. Exists so integration tests and local development can
/// force license flags ON without a live license-server round trip.
/// Ignored entirely in release builds because [kDebugMode] is false there,
/// regardless of what was passed as `GAZER_FLAGS_OVERRIDE` — see the
/// release-build guard in `test/config/debug_overrides_test.dart` and the
/// mandatory code-review check in this task's Step 6.
class DebugOverrides {
  const DebugOverrides._();

  /// Raw comma-separated flag-key list from
  /// `--dart-define=GAZER_FLAGS_OVERRIDE=...`. Empty when not supplied.
  static const String flagsOverride = String.fromEnvironment('GAZER_FLAGS_OVERRIDE');

  /// True only when running a debug build AND a non-empty override was
  /// supplied. Both conditions are required — kDebugMode is false in
  /// release/profile builds regardless of the define, so this can never
  /// leak into a production build no matter what was passed at build time.
  static bool get enabled => kDebugMode && flagsOverride.isNotEmpty;

  /// Parsed flag keys from [flagsOverride]: comma-split, trimmed, empty
  /// entries dropped.
  static Set<String> get flags => flagsOverride
      .split(',')
      .map((s) => s.trim())
      .where((s) => s.isNotEmpty)
      .toSet();
}
