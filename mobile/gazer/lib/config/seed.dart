/// Debug-only mock-data seeding for a fresh install.
///
/// Applies a mock stream target + default quality preset when the app is
/// launched with `--dart-define=GAZER_SEED=true` in a debug build. Exists
/// for local development and `make mobile-screenshots` capture runs —
/// never active in a release build (kDebugMode gates it) and never
/// overwrites settings a real user already saved.
library;

import 'package:flutter/foundation.dart';

import '../models/gazer_settings.dart';
import '../models/quality.dart';
import '../services/settings_repository.dart';
import 'mock_targets.dart' as fixtures;

bool get _seedRequested => kDebugMode && const bool.fromEnvironment('GAZER_SEED');

/// Seeds [repo] with a mock target + default quality preset when
/// `--dart-define=GAZER_SEED=true` was passed to a debug build AND the
/// repository has no previously-saved settings (its `load()` still
/// returns [GazerSettings.defaults] — the empty-state sentinel). Never
/// overwrites a real user's saved settings; safe to call on every launch.
Future<void> applySeedIfRequested(SettingsRepository repo) async {
  if (!_seedRequested) return;

  final GazerSettings current = await repo.load();
  if (current != GazerSettings.defaults()) {
    return; // real settings already saved - never clobber them
  }

  final GazerSettings seeded = current.copyWith(
    target: fixtures.mockTargets.first,
    quality: QualitySettings.defaults(),
  );
  await repo.save(seeded);
}
