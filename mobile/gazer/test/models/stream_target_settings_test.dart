import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/stream_target_settings.dart';

void main() {
  group('StreamTargetSettings.empty', () {
    test('has a blank url and no key or credentials', () {
      final empty = StreamTargetSettings.empty();
      expect(empty.url, isEmpty);
      expect(empty.streamKey, isNull);
      expect(empty.username, isNull);
      expect(empty.password, isNull);
    });
  });

  group('StreamTargetSettings JSON round-trip', () {
    test('toJson/fromJson preserves every field including credentials', () {
      const original = StreamTargetSettings(
        url: 'rtmps://ingest-b.example.com/app',
        streamKey: 'demo-key-0002',
        username: 'demo',
        password: 's3cret',
      );
      final restored = StreamTargetSettings.fromJson(original.toJson());
      expect(restored, original);
    });

    test('nullable fields round-trip as null', () {
      const original = StreamTargetSettings(
        url: 'rtmp://ingest-a.example.com/live',
      );
      final restored = StreamTargetSettings.fromJson(original.toJson());
      expect(restored.streamKey, isNull);
      expect(restored.username, isNull);
      expect(restored.password, isNull);
    });
  });

  group('StreamTargetSettings equality', () {
    test('two instances with identical fields are ==', () {
      const a = StreamTargetSettings(
        url: 'rtmp://a.example.com/live',
        streamKey: 'k',
      );
      const b = StreamTargetSettings(
        url: 'rtmp://a.example.com/live',
        streamKey: 'k',
      );
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing url breaks equality', () {
      const a = StreamTargetSettings(url: 'rtmp://a.example.com/live');
      const b = StreamTargetSettings(url: 'rtmp://b.example.com/live');
      expect(a == b, isFalse);
    });
  });
}
