import 'package:flutter_test/flutter_test.dart';

import 'package:gazer/config/seed.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/quality.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/services/settings_repository.dart';

import '../fixtures/mock_targets.dart' as fixtures;

class _InMemorySettingsRepository implements SettingsRepository {
  _InMemorySettingsRepository(this._stored);
  GazerSettings _stored;
  int saveCount = 0;

  @override
  Future<GazerSettings> load() async => _stored;

  @override
  Future<void> save(GazerSettings s) async {
    _stored = s;
    saveCount++;
  }
}

void main() {
  group('applySeedIfRequested', () {
    test('is a no-op without --dart-define=GAZER_SEED=true', () async {
      final repo = _InMemorySettingsRepository(GazerSettings.defaults());
      await applySeedIfRequested(repo);
      if (!const bool.fromEnvironment('GAZER_SEED')) {
        expect(repo.saveCount, 0);
        expect(await repo.load(), GazerSettings.defaults());
      }
    });

    test('seeds an empty (defaults) repository when GAZER_SEED=true', () async {
      final repo = _InMemorySettingsRepository(GazerSettings.defaults());
      await applySeedIfRequested(repo);
      if (const bool.fromEnvironment('GAZER_SEED')) {
        expect(repo.saveCount, 1);
        final GazerSettings result = await repo.load();
        expect(result.target, fixtures.mockTargets.first);
        expect(result.quality, QualitySettings.defaults());
      }
    });

    test('never overwrites a repository with non-default settings, even when GAZER_SEED=true', () async {
      final GazerSettings customized = GazerSettings.defaults().copyWith(
        target: const StreamTargetSettings(
          url: 'rtmp://real-user-endpoint.example.com/live',
        ),
      );
      final repo = _InMemorySettingsRepository(customized);
      await applySeedIfRequested(repo);
      expect(repo.saveCount, 0, reason: 'never clobber real saved settings');
      expect(await repo.load(), customized);
    });
  });
}
