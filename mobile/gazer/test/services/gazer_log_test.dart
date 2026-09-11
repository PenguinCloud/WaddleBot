import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/services/gazer_log.dart';

/// A field value `jsonEncode` cannot natively encode (no `toJson()`), used
/// to prove `_emit`'s `toEncodable` fallback never throws.
class _Unencodable {
  @override
  String toString() => 'unencodable-value';
}

void main() {
  late void Function(String line) originalSink;
  late bool originalVerbose;

  setUpAll(() {
    originalSink = GazerLog.sink;
    originalVerbose = GazerLog.verbose;
  });

  setUp(() {
    GazerLog.verbose = false;
  });

  tearDown(() {
    GazerLog.sink = originalSink;
    GazerLog.verbose = originalVerbose;
  });

  group('maskSecret', () {
    final cases = <String?, String>{
      null: '',
      '': '',
      'abc': '****',
      'demo-key-0001': '****0001',
    };

    for (final entry in cases.entries) {
      test('${entry.key} -> "${entry.value}"', () {
        expect(GazerLog.maskSecret(entry.key), entry.value);
      });
    }
  });

  group('sanitize', () {
    test('masks password/streamKey/username and only the url last segment', () {
      final result = GazerLog.sanitize(<String, Object?>{
        'password': 's3cretpass',
        'streamKey': 'demo-key-0001',
        'username': 'demo-user',
        'url': 'rtmp://ingest.example.com/live/mystream',
        'host': 'ingest.example.com',
      });

      expect(result['password'], '****pass');
      expect(result['streamKey'], '****0001');
      expect(result['username'], '****user');
      expect(result['host'], 'ingest.example.com');

      final maskedUrl = result['url'] as String;
      expect(maskedUrl, startsWith('rtmp://ingest.example.com/live/'));
      expect(maskedUrl, isNot(contains('mystream')));
      expect(maskedUrl, contains('****ream'));
    });
  });

  group('emission', () {
    test('info emits one JSON line with ts/level/event/fields', () {
      final lines = <String>[];
      GazerLog.sink = lines.add;

      GazerLog.info('license.fetch', <String, Object?>{
        'status': 'valid',
        'flagCount': 4,
      });

      expect(lines, hasLength(1));
      final decoded = jsonDecode(lines.single) as Map<String, dynamic>;
      expect(decoded['level'], 'info');
      expect(decoded['event'], 'license.fetch');
      expect(decoded['status'], 'valid');
      expect(decoded['flagCount'], 4);
      expect(decoded['ts'], isNotNull);
    });

    test('debug emits only when verbose is enabled', () {
      final lines = <String>[];
      GazerLog.sink = lines.add;

      GazerLog.verbose = false;
      GazerLog.debug('pipeline.state', <String, Object?>{
        'from': 'idle',
        'to': 'preparing',
      });
      expect(lines, isEmpty);

      GazerLog.verbose = true;
      GazerLog.debug('pipeline.state', <String, Object?>{
        'from': 'idle',
        'to': 'preparing',
      });
      expect(lines, hasLength(1));
      final decoded = jsonDecode(lines.single) as Map<String, dynamic>;
      expect(decoded['level'], 'debug');
    });

    test(
      'non-encodable field values fall back to toString() instead of throwing',
      () {
        final lines = <String>[];
        GazerLog.sink = lines.add;

        expect(
          () => GazerLog.info('diagnostic', <String, Object?>{
            'weird': _Unencodable(),
          }),
          returnsNormally,
        );

        expect(lines, hasLength(1));
        final decoded = jsonDecode(lines.single) as Map<String, dynamic>;
        expect(decoded['weird'], 'unencodable-value');
      },
    );
  });
}
