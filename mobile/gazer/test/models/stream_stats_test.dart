import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/stream_stats.dart';

void main() {
  group('StreamStats.zero', () {
    test('is the all-zero snapshot', () {
      const zero = StreamStats(
        currentBitrateKbps: 0,
        averageBitrateKbps: 0,
        fps: 0,
        droppedFrames: 0,
        sentBytes: 0,
        uptime: Duration.zero,
        reconnectCount: 0,
        congestionPercent: 0,
      );
      expect(StreamStats.zero(), zero);
    });
  });

  group('StreamStats equality', () {
    test('two instances with identical fields are ==', () {
      const a = StreamStats(
        currentBitrateKbps: 2000,
        averageBitrateKbps: 1900,
        fps: 29.5,
        droppedFrames: 3,
        sentBytes: 123456,
        uptime: Duration(seconds: 62),
        reconnectCount: 1,
        congestionPercent: 12.5,
      );
      const b = StreamStats(
        currentBitrateKbps: 2000,
        averageBitrateKbps: 1900,
        fps: 29.5,
        droppedFrames: 3,
        sentBytes: 123456,
        uptime: Duration(seconds: 62),
        reconnectCount: 1,
        congestionPercent: 12.5,
      );
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing reconnectCount breaks equality', () {
      final a = StreamStats.zero();
      final b = a.copyWith(reconnectCount: 2);
      expect(a == b, isFalse);
    });
  });
}
