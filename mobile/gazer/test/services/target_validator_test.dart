import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/models/validation_issue.dart';
import 'package:gazer/services/target_validator.dart';

void main() {
  const validator = TargetValidator();

  group('TargetValidator.validate (table-driven)', () {
    final cases =
        <
          String,
          ({StreamTargetSettings target, List<ValidationIssue> expected})
        >{
          'valid rtmp': (
            target: const StreamTargetSettings(
              url: 'rtmp://ingest-a.example.com/live',
            ),
            expected: const [],
          ),
          'valid rtmps': (
            target: const StreamTargetSettings(
              url: 'rtmps://ingest-b.example.com/app',
            ),
            expected: const [],
          ),
          'missing scheme': (
            target: const StreamTargetSettings(url: 'ingest.example.com/live'),
            expected: const [
              ValidationIssue(field: 'url', messageKey: 'errorUrlScheme'),
            ],
          ),
          'http scheme rejected': (
            target: const StreamTargetSettings(
              url: 'http://bad.example.com/live',
            ),
            expected: const [
              ValidationIssue(field: 'url', messageKey: 'errorUrlScheme'),
            ],
          ),
          'empty host': (
            target: const StreamTargetSettings(url: 'rtmp:///live'),
            expected: const [
              ValidationIssue(field: 'url', messageKey: 'errorUrlHost'),
            ],
          ),
          'missing app path': (
            target: const StreamTargetSettings(url: 'rtmp://host.example.com'),
            expected: const [
              ValidationIssue(field: 'url', messageKey: 'errorUrlPath'),
            ],
          ),
          'username without password rejected': (
            target: const StreamTargetSettings(
              url: 'rtmp://ingest-a.example.com/live',
              username: 'demo',
            ),
            expected: const [
              ValidationIssue(
                field: 'auth',
                messageKey: 'errorAuthBothOrNeither',
              ),
            ],
          ),
          'password without username rejected': (
            target: const StreamTargetSettings(
              url: 'rtmp://ingest-a.example.com/live',
              password: 'secret',
            ),
            expected: const [
              ValidationIssue(
                field: 'auth',
                messageKey: 'errorAuthBothOrNeither',
              ),
            ],
          ),
        };

    cases.forEach((description, testCase) {
      test(description, () {
        expect(validator.validate(testCase.target), testCase.expected);
      });
    });
  });

  group('TargetValidator.effectiveUrl', () {
    test('key appended when url lacks it', () {
      const t = StreamTargetSettings(
        url: 'rtmp://ingest-a.example.com/live',
        streamKey: 'demo-key-0001',
      );
      expect(
        TargetValidator.effectiveUrl(t),
        'rtmp://ingest-a.example.com/live/demo-key-0001',
      );
    });

    test('key not double-appended when url already ends with it', () {
      const t = StreamTargetSettings(
        url: 'rtmp://ingest-a.example.com/live/demo-key-0001',
        streamKey: 'demo-key-0001',
      );
      expect(
        TargetValidator.effectiveUrl(t),
        'rtmp://ingest-a.example.com/live/demo-key-0001',
      );
    });

    test('key with leading slash is normalised, not double-slashed', () {
      const t = StreamTargetSettings(
        url: 'rtmp://ingest-a.example.com/live',
        streamKey: '/demo-key-0001',
      );
      expect(
        TargetValidator.effectiveUrl(t),
        'rtmp://ingest-a.example.com/live/demo-key-0001',
      );
    });

    test(
      'trailing slash on url never produces a doubled slash before the key',
      () {
        const t = StreamTargetSettings(
          url: 'rtmp://ingest-a.example.com/live/',
          streamKey: 'demo-key-0001',
        );
        final result = TargetValidator.effectiveUrl(t);
        expect(result, 'rtmp://ingest-a.example.com/live/demo-key-0001');
        expect(result.contains('//demo-key-0001'), isFalse);
      },
    );

    test('no key returns the url unchanged', () {
      const t = StreamTargetSettings(url: 'rtmp://ingest-a.example.com/live');
      expect(
        TargetValidator.effectiveUrl(t),
        'rtmp://ingest-a.example.com/live',
      );
    });
  });
}
