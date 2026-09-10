import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/quality.dart';
import 'package:gazer/models/stream_target_settings.dart';

void main() {
  group('GazerSettings.defaults', () {
    test('is an empty target, default quality, auto audio, libuvc off', () {
      final defaults = GazerSettings.defaults();
      expect(defaults.target, StreamTargetSettings.empty());
      expect(defaults.quality, QualitySettings.defaults());
      expect(defaults.audio, AudioSourceChoice.auto);
      expect(defaults.forceLibuvc, isFalse);
    });
  });

  group('GazerSettings JSON round-trip', () {
    test('toJson/fromJson preserves nested target and quality', () {
      final original = const GazerSettings(
        target: StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live',
          streamKey: 'demo-key-0001',
        ),
        quality: QualitySettings(
          resolution: Resolution.p720,
          frameRate: FrameRate.fps60,
          videoBitrateKbps: 3000,
          adaptiveBitrate: false,
        ),
        audio: AudioSourceChoice.usbAudio,
        forceLibuvc: true,
      );
      final restored = GazerSettings.fromJson(original.toJson());
      expect(restored, original);
    });
  });

  group('GazerSettings equality', () {
    test('two instances with identical nested fields are ==', () {
      final a = GazerSettings.defaults();
      final b = GazerSettings.defaults();
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing audio choice breaks equality', () {
      final a = GazerSettings.defaults();
      final b = a.copyWith(audio: AudioSourceChoice.mic);
      expect(a == b, isFalse);
    });
  });

  group('AudioSourceChoice', () {
    test('has exactly the four supported values', () {
      expect(AudioSourceChoice.values, [
        AudioSourceChoice.auto,
        AudioSourceChoice.mic,
        AudioSourceChoice.usbAudio,
        AudioSourceChoice.silence,
      ]);
    });
  });
}
