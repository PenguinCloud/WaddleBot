import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/quality.dart';
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

  group('StreamTargetSettings toString redaction (R22)', () {
    const secretPassword = 'hunter2-secret';
    const secretStreamKey = 'demo-key-0001';

    test('does not contain the raw password or streamKey', () {
      const settings = StreamTargetSettings(
        url: 'rtmps://ingest-a.example.com/app/path?token=abc',
        streamKey: secretStreamKey,
        username: 'demo-user',
        password: secretPassword,
      );
      final rendered = settings.toString();
      expect(rendered, isNot(contains(secretPassword)));
      expect(rendered, isNot(contains(secretStreamKey)));
      expect(rendered, isNot(contains('demo-user')));
      // The last-4 mask is intentionally still visible.
      expect(rendered, contains('****0001'));
      expect(rendered, contains('<redacted>'));
      // Host survives; query string (which carried a token) does not.
      expect(rendered, contains('ingest-a.example.com'));
      expect(rendered, isNot(contains('token=abc')));
    });

    test('null username/password/streamKey print as null, not redacted', () {
      const settings = StreamTargetSettings(url: 'rtmp://a.example.com/live');
      final rendered = settings.toString();
      expect(rendered, contains('streamKey: null'));
      expect(rendered, contains('username: null'));
      expect(rendered, contains('password: null'));
    });

    test('GazerSettings.toString() does not leak the nested credentials', () {
      final settings = GazerSettings(
        target: const StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live',
          streamKey: secretStreamKey,
          username: 'demo-user',
          password: secretPassword,
        ),
        quality: QualitySettings.defaults(),
        audio: AudioSourceChoice.auto,
        forceLibuvc: false,
        debugLogs: false,
      );
      final rendered = settings.toString();
      expect(rendered, isNot(contains(secretPassword)));
      expect(rendered, isNot(contains(secretStreamKey)));
      expect(rendered, isNot(contains('demo-user')));
      expect(rendered, contains('****0001'));
    });
  });
}
