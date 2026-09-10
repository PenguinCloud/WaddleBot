import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/services/update_checker.dart';
import 'package:mocktail/mocktail.dart';

class _MockDio extends Mock implements Dio {}

void main() {
  late _MockDio dio;

  setUp(() {
    dio = _MockDio();
  });

  Response<List<dynamic>> releasesResponse(
    List<Map<String, dynamic>> releases,
  ) => Response<List<dynamic>>(
    requestOptions: RequestOptions(path: 'releases'),
    statusCode: 200,
    data: releases,
  );

  group('UpdateChecker.check', () {
    test('a newer gazer-v tag returns UpdateInfo', () async {
      when(() => dio.get<List<dynamic>>(any())).thenAnswer(
        (_) async => releasesResponse([
          {
            'tag_name': 'gazer-v1.3.0',
            'html_url': 'https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.3.0',
          },
        ]),
      );
      final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

      final info = await checker.check();

      expect(info, isNotNull);
      expect(info!.latestVersion, '1.3.0');
      expect(info.currentVersion, '1.2.0');
      expect(
        info.releaseUrl,
        Uri.parse(
          'https://github.com/penguintechinc/waddlebot/releases/tag/gazer-v1.3.0',
        ),
      );
    });

    test('an equal tag returns null', () async {
      when(() => dio.get<List<dynamic>>(any())).thenAnswer(
        (_) async => releasesResponse([
          {
            'tag_name': 'gazer-v1.2.0',
            'html_url': 'https://example.com/gazer-v1.2.0',
          },
        ]),
      );
      final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

      expect(await checker.check(), isNull);
    });

    test('non-gazer tags are ignored', () async {
      when(() => dio.get<List<dynamic>>(any())).thenAnswer(
        (_) async => releasesResponse([
          {'tag_name': 'v1.9.0', 'html_url': 'https://example.com/v1.9.0'},
          {
            'tag_name': 'backend-v2.0.0',
            'html_url': 'https://example.com/backend-v2.0.0',
          },
        ]),
      );
      final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

      expect(await checker.check(), isNull);
    });

    test('a malformed release list returns null', () async {
      when(() => dio.get<List<dynamic>>(any())).thenAnswer(
        (_) async => Response<List<dynamic>>(
          requestOptions: RequestOptions(path: 'releases'),
          statusCode: 200,
          data: 'not-a-list' as List<dynamic>?, // cast to bypass type checker; runtime error caught by try-catch
        ),
      );
      final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

      expect(await checker.check(), isNull);
    });

    test('a network error returns null', () async {
      when(() => dio.get<List<dynamic>>(any())).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: 'releases'),
          type: DioExceptionType.connectionTimeout,
        ),
      );
      final checker = UpdateChecker(dio: dio, currentVersion: '1.2.0');

      expect(await checker.check(), isNull);
    });

    test('semver compare treats 1.10.0 as newer than 1.9.9', () async {
      when(() => dio.get<List<dynamic>>(any())).thenAnswer(
        (_) async => releasesResponse([
          {
            'tag_name': 'gazer-v1.10.0',
            'html_url': 'https://example.com/gazer-v1.10.0',
          },
        ]),
      );
      final checker = UpdateChecker(dio: dio, currentVersion: '1.9.9');

      final info = await checker.check();

      expect(info, isNotNull);
      expect(info!.latestVersion, '1.10.0');
    });
  });
}
