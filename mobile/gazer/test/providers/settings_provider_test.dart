import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/providers/settings_provider.dart';
import 'package:gazer/services/gazer_log.dart';
import 'package:gazer/services/settings_repository.dart';

class _FakeSettingsRepository implements SettingsRepository {
  GazerSettings stored = GazerSettings.defaults();
  int saveCallCount = 0;

  @override
  Future<GazerSettings> load() async => stored;

  @override
  Future<void> save(GazerSettings s) async {
    saveCallCount += 1;
    stored = s;
  }
}

void main() {
  tearDown(() {
    // Every test here builds/saves through the real SettingsNotifier, which
    // sets GazerLog.verbose from GazerSettings.debugLogs — reset so a
    // future test with debugLogs: true never leaks into a later test.
    GazerLog.resetForTest();
  });

  test('SettingsNotifier.build loads from the repository', () async {
    final repo = _FakeSettingsRepository();
    final container = ProviderContainer(
      overrides: [settingsRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    final loaded = await container.read(settingsProvider.future);

    expect(loaded, GazerSettings.defaults());
  });

  test(
    'SettingsNotifier.save persists via the repository and updates state',
    () async {
      final repo = _FakeSettingsRepository();
      final container = ProviderContainer(
        overrides: [settingsRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(settingsProvider.future);
      final defaults = GazerSettings.defaults();
      final updated = defaults.copyWith(
        quality: defaults.quality.copyWith(videoBitrateKbps: 3000),
      );

      await container.read(settingsProvider.notifier).save(updated);

      expect(repo.saveCallCount, 1);
      expect(repo.stored, updated);
      expect(container.read(settingsProvider).value, updated);
    },
  );
}
