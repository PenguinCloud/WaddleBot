import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/quality.dart';

import 'mock_targets.dart';

void main() {
  test('mockTargets has exactly the 4 spec presets in spec order', () {
    expect(mockTargets, hasLength(4));
    expect(mockTargets[0].url, 'rtmp://ingest-a.example.com/live');
    expect(mockTargets[0].streamKey, 'demo-key-0001');
    expect(mockTargets[0].username, isNull);

    expect(mockTargets[1].url, 'rtmps://ingest-b.example.com/app');
    expect(mockTargets[1].streamKey, 'demo-key-0002');
    expect(mockTargets[1].username, 'demo');
    expect(mockTargets[1].password, isNotNull);

    expect(mockTargets[2].url, 'rtmp://10.0.2.2:1935/live');
    expect(mockTargets[2].streamKey, isNull);

    expect(mockTargets[3].url, 'http://bad.example.com');
  });

  test(
    'mockQualityPresets has exactly 2 presets: default and low-bandwidth',
    () {
      expect(mockQualityPresets, hasLength(2));
      expect(mockQualityPresets[0], QualitySettings.defaults());
      expect(mockQualityPresets[1].resolution, Resolution.p360);
      expect(mockQualityPresets[1].frameRate, FrameRate.fps15);
      expect(mockQualityPresets[1].videoBitrateKbps, 800);
      expect(mockQualityPresets[1].adaptiveBitrate, isFalse);
    },
  );
}
