import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/services/device_id.dart';
import 'package:gazer/services/license_client.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:shared_preferences_platform_interface/in_memory_shared_preferences_async.dart';
import 'package:shared_preferences_platform_interface/shared_preferences_async_platform_interface.dart';

class _MockDio extends Mock implements Dio {}

class _FakeDeviceIdProvider implements DeviceIdProvider {
  @override
  Future<String> deviceId() async => 'device-abc';
}

void main() {
  setUpAll(() {
    registerFallbackValue(<String, String>{});
  });

  late _MockDio dio;
  late LicenseCache cache;
  late DateTime fakeNow;

  setUp(() {
    dio = _MockDio();
    SharedPreferencesAsyncPlatform.instance =
        InMemorySharedPreferencesAsync.empty();
    cache = LicenseCache(SharedPreferencesAsync());
    fakeNow = DateTime.utc(2026, 9, 7, 12);
  });

  LicenseClient buildClient() => LicenseClient(
    dio: dio,
    cache: cache,
    deviceIdProvider: _FakeDeviceIdProvider(),
    now: () => fakeNow,
  );

  group('LicenseCache round trip', () {
    test('read() returns null when nothing was ever written', () async {
      expect(await cache.read(), isNull);
    });

    test('write() then read() returns the same LicenseState', () async {
      final state = LicenseState(
        status: LicenseStatus.valid,
        flags: const {'waddlebot.gazer.camera-stream': true},
        lastFetched: fakeNow,
        deviceId: 'device-abc',
      );
      await cache.write(state);
      expect(await cache.read(), state);
    });
  });

  group('validateAndFetchFlags success', () {
    test(
      'returns valid status, server flags, and lastFetched = now()',
      () async {
        when(() => dio.post<dynamic>(any(), data: any(named: 'data')))
            .thenAnswer((invocation) async {
              final path = invocation.positionalArguments.first as String;
              if (path.endsWith('/validate')) {
                return Response(
                  requestOptions: RequestOptions(path: path),
                  statusCode: 200,
                  data: <String, dynamic>{},
                );
              }
              return Response(
                requestOptions: RequestOptions(path: path),
                statusCode: 200,
                data: {
                  'features': {'waddlebot.gazer.camera-stream': true},
                },
              );
            });

        final state = await buildClient().validateAndFetchFlags();

        expect(state.status, LicenseStatus.valid);
        expect(state.flags['waddlebot.gazer.camera-stream'], isTrue);
        expect(state.lastFetched, fakeNow);
      },
    );
  });

  group('validateAndFetchFlags network error with fresh cache', () {
    test('within 7 days -> gracePeriod with cached flags', () async {
      await cache.write(
        LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: fakeNow.subtract(const Duration(days: 3)),
          deviceId: 'device-abc',
        ),
      );
      when(() => dio.post<dynamic>(any(), data: any(named: 'data'))).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/validate'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      final state = await buildClient().validateAndFetchFlags();

      expect(state.status, LicenseStatus.gracePeriod);
      expect(state.flags['waddlebot.gazer.camera-stream'], isTrue);
    });
  });

  group('validateAndFetchFlags network error with stale cache', () {
    test('older than 7 days -> unknown', () async {
      await cache.write(
        LicenseState(
          status: LicenseStatus.valid,
          flags: const {'waddlebot.gazer.camera-stream': true},
          lastFetched: fakeNow.subtract(const Duration(days: 10)),
          deviceId: 'device-abc',
        ),
      );
      when(() => dio.post<dynamic>(any(), data: any(named: 'data'))).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/validate'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      final state = await buildClient().validateAndFetchFlags();

      expect(state.status, LicenseStatus.unknown);
    });

    test('no cache at all -> unknown with empty flags', () async {
      when(() => dio.post<dynamic>(any(), data: any(named: 'data'))).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/validate'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      final state = await buildClient().validateAndFetchFlags();

      expect(state.status, LicenseStatus.unknown);
      expect(state.flags, isEmpty);
    });
  });

  group('validateAndFetchFlags 4xx response', () {
    test('-> invalid', () async {
      when(() => dio.post<dynamic>(any(), data: any(named: 'data'))).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/validate'),
          type: DioExceptionType.badResponse,
          response: Response(
            requestOptions: RequestOptions(path: '/validate'),
            statusCode: 401,
          ),
        ),
      );

      final state = await buildClient().validateAndFetchFlags();

      expect(state.status, LicenseStatus.invalid);
    });
  });

  group('validateAndFetchFlags never throws', () {
    test('an unexpected exception (malformed response shape) is swallowed, not rethrown', () async {
      when(() => dio.post<dynamic>(any(), data: any(named: 'data')))
          .thenAnswer((invocation) async {
            final path = invocation.positionalArguments.first as String;
            return Response(
              requestOptions: RequestOptions(path: path),
              statusCode: 200,
              data: <String, dynamic>{},
            );
          });

      expect(buildClient().validateAndFetchFlags(), completes);
    });
  });

  group('keepalive', () {
    test('is fire-and-forget: completes even when the POST throws', () async {
      when(() => dio.post<dynamic>(any(), data: any(named: 'data'))).thenThrow(
        DioException(
          requestOptions: RequestOptions(path: '/keepalive'),
          type: DioExceptionType.connectionTimeout,
        ),
      );

      await expectLater(buildClient().keepalive(), completes);
    });
  });
}
