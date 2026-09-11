import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/gazer_settings.dart';
import '../services/gazer_log.dart';
import '../services/settings_repository.dart';

part 'settings_provider.g.dart';

/// The [SettingsRepository] implementation the app uses; overridden in
/// tests with a fake so [SettingsNotifier] never touches real storage.
@Riverpod(keepAlive: true)
SettingsRepository settingsRepository(Ref ref) => SecureSettingsRepository(
  secure: const FlutterSecureStorage(),
  prefs: SharedPreferencesAsync(),
);

/// Loads, holds, and persists the user's [GazerSettings].
///
/// `keepAlive: true` because settings must survive navigation between
/// HomeScreen and SettingsScreen without re-reading storage on every visit.
///
/// Generates `settingsProvider`, not `settingsNotifierProvider`:
/// riverpod_generator's default `provider_name_strip_pattern` (`Notifier$`)
/// strips a trailing "Notifier" from an annotated class name before
/// appending "Provider", specifically to avoid "NotifierNotifierProvider"
/// stuttering — this is the generator's stable, documented default across
/// versions, not a quirk of this pin. Every other provider in this file set
/// is function-based (`license`, `featureFlags`, `videoDevices`, ...), so
/// this stripping only ever applies here. Consumers (Task 13+ UI) import
/// `settingsProvider`.
@Riverpod(keepAlive: true)
class SettingsNotifier extends _$SettingsNotifier {
  @override
  Future<GazerSettings> build() async {
    final GazerSettings settings = await ref
        .watch(settingsRepositoryProvider)
        .load();
    GazerLog.verbose = settings.debugLogs;
    return settings;
  }

  /// Persists [s] via the repository and updates provider state so every
  /// listener (HomeScreen enablement, StatusPanel) sees the new settings.
  /// Also re-applies [GazerLog.verbose] so toggling Settings > Developer
  /// > Debug logs takes effect immediately, without an app restart.
  ///
  /// Named `save`, not `update`: `$AsyncNotifier`/`$AsyncClassModifier`
  /// (riverpod 3.4.3) already defines a protected mutation helper method
  /// also named `update` (signature: a `FutureOr<ValueT> Function(ValueT)`
  /// callback) on every generated class-based AsyncNotifier, so a
  /// same-named override here with an incompatible signature is a compile
  /// error, not a valid override — the task brief's sample (written before
  /// this exact riverpod_generator/riverpod pin) predates that framework
  /// method.
  Future<void> save(GazerSettings s) async {
    await ref.read(settingsRepositoryProvider).save(s);
    GazerLog.verbose = s.debugLogs;
    state = AsyncData(s);
  }
}
