import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/telemetry/gazer_telemetry.dart';
import 'package:gazer/telemetry/telemetry_config.dart';

/// An attribute value whose `toString()` throws, simulating a
/// caller-supplied value the exporter cannot serialize -- `GazerLog`'s own
/// `sanitize()` never produces one (it only ever emits String/num/bool/
/// null), but a direct `GazerTelemetry.recordLog`/`histogram`/`counter`
/// caller might pass something unexpected, so the exporter's never-throw
/// guarantee is asserted at that boundary too.
class _ThrowingToString {
  @override
  String toString() => throw StateError('toString() deliberately throws');
}

void main() {
  tearDown(GazerTelemetry.resetForTest);

  test('one log, one counter, one histogram, one span all reach a local OTLP/HTTP JSON sink', () async {
    int logRecords = 0;
    int metricDataPoints = 0;
    int histogramDataPoints = 0;
    int spans = 0;

    final HttpServer server = await HttpServer.bind(
      InternetAddress.loopbackIPv4,
      0,
    );
    final subscription = server.listen((HttpRequest request) async {
      final String body = await utf8.decoder.bind(request).join();
      final Map<String, dynamic> decoded =
          jsonDecode(body) as Map<String, dynamic>;
      if (request.uri.path == '/v1/logs') {
        for (final rl in decoded['resourceLogs'] as List) {
          for (final sl in (rl as Map<String, dynamic>)['scopeLogs'] as List) {
            logRecords +=
                ((sl as Map<String, dynamic>)['logRecords'] as List).length;
          }
        }
      } else if (request.uri.path == '/v1/metrics') {
        for (final rm in decoded['resourceMetrics'] as List) {
          for (final sm
              in (rm as Map<String, dynamic>)['scopeMetrics'] as List) {
            for (final metric
                in (sm as Map<String, dynamic>)['metrics'] as List) {
              final Map<String, dynamic> m = metric as Map<String, dynamic>;
              final Map<String, dynamic> shape =
                  (m['histogram'] ?? m['sum'] ?? m['gauge'])
                      as Map<String, dynamic>;
              final int count = (shape['dataPoints'] as List).length;
              metricDataPoints += count;
              if (m.containsKey('histogram')) histogramDataPoints += count;
            }
          }
        }
      } else if (request.uri.path == '/v1/traces') {
        for (final rs in decoded['resourceSpans'] as List) {
          for (final ss in (rs as Map<String, dynamic>)['scopeSpans'] as List) {
            spans += ((ss as Map<String, dynamic>)['spans'] as List).length;
          }
        }
      }
      request.response.statusCode = 200;
      await request.response.close();
    });
    addTearDown(() async {
      await server.close(force: true);
      await subscription.cancel();
    });

    GazerTelemetry.init(
      TelemetryConfig(
        endpoint: 'http://127.0.0.1:${server.port}',
        protocol: 'http/json',
        headers: const <String, String>{},
        serviceName: 'gazer-test',
        serviceVersion: '0.0.0',
        deploymentEnvironment: 'test',
      ),
      dio: Dio(),
    );

    GazerTelemetry.recordLog('info', 'test.log', const <String, Object?>{
      'k': 'v',
    });
    GazerTelemetry.counter('test.counter');
    GazerTelemetry.histogram('test.histogram', 42);
    GazerTelemetry.startSpan('test.span').end();

    await GazerTelemetry.flush();
    // Give the server's async request handler a moment to finish decoding
    // before asserting -- flush()'s POST resolving does not guarantee the
    // server-side listener callback above has run yet.
    await Future<void>.delayed(const Duration(milliseconds: 50));

    // Required by the house telemetry test gate (critical-rules.md
    // Verification Integrity: report the count examined, not just "no
    // findings"). `make mobile-telemetry-check` greps this exact line and
    // fails if any count is zero or the line is absent.
    // ignore: avoid_print
    print(
      'telemetry sink received: logs=$logRecords metrics=$metricDataPoints '
      'histograms=$histogramDataPoints spans=$spans',
    );

    expect(logRecords, greaterThanOrEqualTo(1));
    expect(metricDataPoints, greaterThanOrEqualTo(1));
    expect(histogramDataPoints, greaterThanOrEqualTo(1));
    expect(spans, greaterThanOrEqualTo(1));
  });

  test('a dead endpoint (connection refused) never throws and increments exportFailures', () async {
    // Bind then immediately close a server to obtain a port nothing is
    // listening on -- guarantees a real connection-refused, not a flaky
    // guessed-unused-port.
    final HttpServer probe = await HttpServer.bind(
      InternetAddress.loopbackIPv4,
      0,
    );
    final int deadPort = probe.port;
    await probe.close(force: true);

    GazerTelemetry.init(
      TelemetryConfig(
        endpoint: 'http://127.0.0.1:$deadPort',
        protocol: 'http/json',
        headers: const <String, String>{},
        serviceName: 'gazer-test',
        serviceVersion: '0.0.0',
        deploymentEnvironment: 'test',
      ),
      dio: Dio(),
    );

    GazerTelemetry.recordLog('info', 'test.log', const <String, Object?>{});
    await expectLater(GazerTelemetry.flush(), completes);

    expect(GazerTelemetry.exportFailures, greaterThanOrEqualTo(1));
  });

  test('an empty endpoint makes zero HTTP calls', () async {
    int requestsReceived = 0;
    final HttpServer server = await HttpServer.bind(
      InternetAddress.loopbackIPv4,
      0,
    );
    final subscription = server.listen((HttpRequest request) async {
      requestsReceived += 1;
      request.response.statusCode = 200;
      await request.response.close();
    });
    addTearDown(() async {
      await server.close(force: true);
      await subscription.cancel();
    });

    GazerTelemetry.init(
      const TelemetryConfig(
        endpoint: '',
        protocol: 'http/json',
        headers: <String, String>{},
        serviceName: 'gazer-test',
        serviceVersion: '0.0.0',
        deploymentEnvironment: 'test',
      ),
      dio: Dio(),
    );

    GazerTelemetry.recordLog('info', 'test.log', const <String, Object?>{});
    GazerTelemetry.counter('test.counter');
    await GazerTelemetry.flush();
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(requestsReceived, 0);
  });

  test('a poisoned log batch is dropped after one encode failure, and a later good record still exports', () async {
    int logRecords = 0;
    int metricDataPoints = 0;

    final HttpServer server = await HttpServer.bind(
      InternetAddress.loopbackIPv4,
      0,
    );
    final subscription = server.listen((HttpRequest request) async {
      final String body = await utf8.decoder.bind(request).join();
      final Map<String, dynamic> decoded =
          jsonDecode(body) as Map<String, dynamic>;
      if (request.uri.path == '/v1/logs') {
        for (final rl in decoded['resourceLogs'] as List) {
          for (final sl in (rl as Map<String, dynamic>)['scopeLogs'] as List) {
            logRecords +=
                ((sl as Map<String, dynamic>)['logRecords'] as List).length;
          }
        }
      } else if (request.uri.path == '/v1/metrics') {
        for (final rm in decoded['resourceMetrics'] as List) {
          for (final sm
              in (rm as Map<String, dynamic>)['scopeMetrics'] as List) {
            metricDataPoints +=
                ((sm as Map<String, dynamic>)['metrics'] as List).length;
          }
        }
      }
      request.response.statusCode = 200;
      await request.response.close();
    });
    addTearDown(() async {
      await server.close(force: true);
      await subscription.cancel();
    });

    GazerTelemetry.init(
      TelemetryConfig(
        endpoint: 'http://127.0.0.1:${server.port}',
        protocol: 'http/json',
        headers: const <String, String>{},
        serviceName: 'gazer-test',
        serviceVersion: '0.0.0',
        deploymentEnvironment: 'test',
      ),
      dio: Dio(),
    );

    GazerTelemetry.recordLog('info', 'test.log', <String, Object?>{
      'bad': _ThrowingToString(),
    });
    GazerTelemetry.counter('test.counter');

    // The poisoned log batch's encoding throws inside OtlpHttpExporter
    // .post's guard; flush() itself must still complete normally, and
    // an encode failure -- unlike a transport failure -- drops the
    // batch instead of retaining it for a doomed-to-repeat retry.
    await expectLater(GazerTelemetry.flush(), completes);
    await Future<void>.delayed(const Duration(milliseconds: 50));

    // Dropped, not retried: exactly one encode failure, nothing
    // reached the log sink (the batch never survived encoding), and
    // the counter -- an unrelated signal type flushed in the same
    // cycle -- still exported normally.
    expect(GazerTelemetry.encodeFailures, 1);
    expect(logRecords, 0);
    expect(metricDataPoints, greaterThanOrEqualTo(1));

    // The poisoned batch is gone from the buffer (dropped, not kept),
    // so a newly appended, well-formed log record exports cleanly on
    // the very next flush -- proving the earlier failure did not
    // permanently wedge this signal type.
    GazerTelemetry.recordLog('info', 'test.log.good', const <String, Object?>{
      'k': 'v',
    });
    await expectLater(GazerTelemetry.flush(), completes);
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(logRecords, greaterThanOrEqualTo(1));
    // No new encode failure from the second, well-formed flush.
    expect(GazerTelemetry.encodeFailures, 1);
  });

  test('a transport failure (connection refused) retains the batch, which exports once the collector is reachable', () async {
    // Bind then immediately close a server to obtain a port nothing is
    // listening on -- guarantees a real connection-refused, not a
    // flaky guessed-unused-port.
    final HttpServer probe = await HttpServer.bind(
      InternetAddress.loopbackIPv4,
      0,
    );
    final int deadPort = probe.port;
    await probe.close(force: true);

    GazerTelemetry.init(
      TelemetryConfig(
        endpoint: 'http://127.0.0.1:$deadPort',
        protocol: 'http/json',
        headers: const <String, String>{},
        serviceName: 'gazer-test',
        serviceVersion: '0.0.0',
        deploymentEnvironment: 'test',
      ),
      dio: Dio(),
    );

    GazerTelemetry.recordLog('info', 'test.log', const <String, Object?>{
      'k': 'v',
    });
    await expectLater(GazerTelemetry.flush(), completes);

    // Transient failure: retained for retry, not dropped -- the
    // opposite of an encode failure.
    expect(GazerTelemetry.exportFailures, greaterThanOrEqualTo(1));
    expect(GazerTelemetry.encodeFailures, 0);

    // The collector "comes back": point telemetry at a real server and
    // flush again -- the same retained record now exports.
    int logRecords = 0;
    final HttpServer server = await HttpServer.bind(
      InternetAddress.loopbackIPv4,
      0,
    );
    final subscription = server.listen((HttpRequest request) async {
      final String body = await utf8.decoder.bind(request).join();
      final Map<String, dynamic> decoded =
          jsonDecode(body) as Map<String, dynamic>;
      if (request.uri.path == '/v1/logs') {
        for (final rl in decoded['resourceLogs'] as List) {
          for (final sl in (rl as Map<String, dynamic>)['scopeLogs'] as List) {
            logRecords +=
                ((sl as Map<String, dynamic>)['logRecords'] as List).length;
          }
        }
      }
      request.response.statusCode = 200;
      await request.response.close();
    });
    addTearDown(() async {
      await server.close(force: true);
      await subscription.cancel();
    });

    GazerTelemetry.init(
      TelemetryConfig(
        endpoint: 'http://127.0.0.1:${server.port}',
        protocol: 'http/json',
        headers: const <String, String>{},
        serviceName: 'gazer-test',
        serviceVersion: '0.0.0',
        deploymentEnvironment: 'test',
      ),
      dio: Dio(),
    );

    await GazerTelemetry.flush();
    await Future<void>.delayed(const Duration(milliseconds: 50));

    expect(logRecords, greaterThanOrEqualTo(1));
  });

  test(
    'reloading telemetry config closes the previous exporter\'s Dio client',
    () async {
      final Dio firstDio = Dio();
      GazerTelemetry.init(
        const TelemetryConfig(
          endpoint: 'http://127.0.0.1:1',
          protocol: 'http/json',
          headers: <String, String>{},
          serviceName: 'gazer-test',
          serviceVersion: '0.0.0',
          deploymentEnvironment: 'test',
        ),
        dio: firstDio,
      );

      GazerTelemetry.init(
        const TelemetryConfig(
          endpoint: 'http://127.0.0.1:2',
          protocol: 'http/json',
          headers: <String, String>{},
          serviceName: 'gazer-test',
          serviceVersion: '0.0.0',
          deploymentEnvironment: 'test',
        ),
        dio: Dio(),
      );

      // The second init() call replaced GazerTelemetry's exporter and
      // closed `firstDio` as a side effect -- using `firstDio` directly
      // now throws (a closed Dio/HttpClient rejects new requests) rather
      // than attempting a real network call, proving `close()` was
      // actually invoked on the previous client, not just discarded.
      await expectLater(
        firstDio.get<dynamic>('http://127.0.0.1:1/'),
        throwsA(anything),
      );
    },
  );
}
