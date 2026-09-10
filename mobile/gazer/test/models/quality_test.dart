import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/quality.dart';

void main() {
  group('Resolution', () {
    test('p540 has 960x540 dimensions and label', () {
      expect(Resolution.p540.width, 960);
      expect(Resolution.p540.height, 540);
      expect(Resolution.p540.label, '540p');
    });

    test('all five tiers expose correct width/height pairs', () {
      expect(Resolution.p180.width, 320);
      expect(Resolution.p180.height, 180);
      expect(Resolution.p360.width, 640);
      expect(Resolution.p360.height, 360);
      expect(Resolution.p720.width, 1280);
      expect(Resolution.p720.height, 720);
      expect(Resolution.p1080.width, 1920);
      expect(Resolution.p1080.height, 1080);
    });
  });

  group('FrameRate', () {
    test('exposes the four supported values', () {
      expect(FrameRate.fps15.value, 15);
      expect(FrameRate.fps30.value, 30);
      expect(FrameRate.fps50.value, 50);
      expect(FrameRate.fps60.value, 60);
    });
  });

  group('QualitySettings.defaults', () {
    test('is 540p/30fps/2000kbps/adaptive-on', () {
      final defaults = QualitySettings.defaults();
      expect(defaults.resolution, Resolution.p540);
      expect(defaults.frameRate, FrameRate.fps30);
      expect(defaults.videoBitrateKbps, 2000);
      expect(defaults.adaptiveBitrate, isTrue);
    });
  });

  group('QualitySettings JSON round-trip', () {
    test('toJson/fromJson preserves every field', () {
      const original = QualitySettings(
        resolution: Resolution.p1080,
        frameRate: FrameRate.fps60,
        videoBitrateKbps: 4500,
        adaptiveBitrate: false,
      );
      final restored = QualitySettings.fromJson(original.toJson());
      expect(restored, original);
    });
  });

  group('QualitySettings equality', () {
    test('two instances with identical fields are ==', () {
      const a = QualitySettings(
        resolution: Resolution.p720,
        frameRate: FrameRate.fps30,
        videoBitrateKbps: 2000,
        adaptiveBitrate: true,
      );
      const b = QualitySettings(
        resolution: Resolution.p720,
        frameRate: FrameRate.fps30,
        videoBitrateKbps: 2000,
        adaptiveBitrate: true,
      );
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing bitrate breaks equality', () {
      const a = QualitySettings(
        resolution: Resolution.p720,
        frameRate: FrameRate.fps30,
        videoBitrateKbps: 2000,
        adaptiveBitrate: true,
      );
      const b = QualitySettings(
        resolution: Resolution.p720,
        frameRate: FrameRate.fps30,
        videoBitrateKbps: 2500,
        adaptiveBitrate: true,
      );
      expect(a == b, isFalse);
    });
  });
}
