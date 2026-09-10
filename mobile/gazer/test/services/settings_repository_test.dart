import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/quality.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/services/settings_repository.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

/// Mocktail fake for [FlutterSecureStorage], backed by an in-memory map so
/// write/read/delete behave like the real secure storage across a test.
class _FakeSecureStorage extends Mock implements FlutterSecureStorage {}

void main() {
  late Map<String, String> secureStore;
  late _FakeSecureStorage secure;
  late SharedPreferencesAsync prefs;
  late SecureSettingsRepository repository;

  setUp(() {
    secureStore = <String, String>{};
    secure = _FakeSecureStorage();
    when(
      () => secure.write(
        key: any(named: 'key'),
        value: any(named: 'value'),
      ),
    ).thenAnswer((invocation) async {
      final key = invocation.namedArguments[#key] as String;
      final value = invocation.namedArguments[#value] as String?;
      if (value == null) {
        secureStore.remove(key);
      } else {
        secureStore[key] = value;
      }
    });
    when(() => secure.read(key: any(named: 'key'))).thenAnswer(
      (invocation) async =>
          secureStore[invocation.namedArguments[#key] as String],
    );
    when(() => secure.delete(key: any(named: 'key')))
        .thenAnswer((invocation) async {
          secureStore.remove(invocation.namedArguments[#key] as String);
        });

    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    prefs = SharedPreferencesAsync();

    repository = SecureSettingsRepository(secure: secure, prefs: prefs);
  });

  group('SecureSettingsRepository.load with nothing stored', () {
    test('returns GazerSettings.defaults()', () async {
      final loaded = await repository.load();
      expect(loaded, GazerSettings.defaults());
    });
  });

  group('SecureSettingsRepository save/load round trip', () {
    test('preserves target, quality, audio and developer settings', () async {
      final original = const GazerSettings(
        target: StreamTargetSettings(
          url: 'rtmps://ingest-b.example.com/app',
          streamKey: 'demo-key-0002',
          username: 'demo',
          password: 's3cret',
        ),
        quality: QualitySettings(
          resolution: Resolution.p1080,
          frameRate: FrameRate.fps60,
          videoBitrateKbps: 4500,
          adaptiveBitrate: false,
        ),
        audio: AudioSourceChoice.usbAudio,
        forceLibuvc: true,
      );

      await repository.save(original);
      final loaded = await repository.load();

      expect(loaded, original);
    });
  });

  group('secrets never written to prefs', () {
    test('no shared_preferences key contains "target"', () async {
      final original = GazerSettings(
        target: const StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live',
          streamKey: 'demo-key-0001',
          username: 'demo',
          password: 's3cret',
        ),
        quality: QualitySettings.defaults(),
        audio: AudioSourceChoice.auto,
        forceLibuvc: false,
      );

      await repository.save(original);

      final prefsKeys = await prefs.getKeys();
      expect(prefsKeys.any((key) => key.contains('target')), isFalse);
    });
  });
}
