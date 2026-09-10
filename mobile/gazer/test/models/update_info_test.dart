import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/update_info.dart';

void main() {
  group('UpdateInfo equality', () {
    test('two instances with identical fields are ==', () {
      final a = UpdateInfo(
        latestVersion: '1.2.3',
        currentVersion: '1.2.0',
        releaseUrl: Uri.parse(
          'https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.2.3',
        ),
      );
      final b = UpdateInfo(
        latestVersion: '1.2.3',
        currentVersion: '1.2.0',
        releaseUrl: Uri.parse(
          'https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.2.3',
        ),
      );
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing latestVersion breaks equality', () {
      final a = UpdateInfo(
        latestVersion: '1.2.3',
        currentVersion: '1.2.0',
        releaseUrl: Uri.parse('https://example.com/a'),
      );
      final b = UpdateInfo(
        latestVersion: '1.3.0',
        currentVersion: '1.2.0',
        releaseUrl: Uri.parse('https://example.com/a'),
      );
      expect(a == b, isFalse);
    });
  });

  test('fields are exposed exactly as constructed', () {
    final info = UpdateInfo(
      latestVersion: '2.0.0',
      currentVersion: '1.9.9',
      releaseUrl: Uri.parse('https://example.com/release'),
    );
    expect(info.latestVersion, '2.0.0');
    expect(info.currentVersion, '1.9.9');
    expect(info.releaseUrl, Uri.parse('https://example.com/release'));
  });

  test('toString includes all three fields', () {
    final info = UpdateInfo(
      latestVersion: '2.0.0',
      currentVersion: '1.9.9',
      releaseUrl: Uri.parse('https://example.com/release'),
    );
    expect(
      info.toString(),
      'UpdateInfo(latestVersion: 2.0.0, currentVersion: 1.9.9, releaseUrl: https://example.com/release)',
    );
  });
}
