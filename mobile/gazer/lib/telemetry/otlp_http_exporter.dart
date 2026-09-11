import 'dart:convert';

import 'package:dio/dio.dart';

/// One OTLP log record awaiting export.
typedef OtlpLogRecord = ({
  DateTime time,
  String level,
  String event,
  Map<String, Object?> attributes,
});

/// One OTLP metric data point awaiting export. [OtlpMetricPoint.kind] is
/// `'histogram'`, `'counter'`, or `'gauge'`.
typedef OtlpMetricPoint = ({
  DateTime time,
  String name,
  String kind,
  double value,
  Map<String, Object?> attributes,
});

/// One completed OTLP span awaiting export.
typedef OtlpSpanRecord = ({
  String name,
  DateTime start,
  DateTime end,
  Map<String, Object?> attributes,
});

/// Minimal OTLP/HTTP JSON exporter: encodes batched log/metric/span records
/// per the OTLP spec's JSON Protobuf Encoding mapping
/// (https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding --
/// camelCase field names, 64-bit integers as decimal strings) and POSTs to
/// a collector's `/v1/logs`, `/v1/metrics`, `/v1/traces` endpoints.
///
/// Exists because pub.dev has no OTLP logs+metrics exporter this app can
/// depend on today without either an incomplete/alpha implementation or an
/// unproven, days-old package -- see the design spec's Observability
/// section for the packages considered. Deliberately tiny: no
/// protobuf/gRPC codegen, reuses the already-pinned `dio` dependency, adds
/// zero new pub.dev packages.
class OtlpHttpExporter {
  OtlpHttpExporter({
    required Dio dio,
    required String endpoint,
    required Map<String, String> headers,
  })
    // ignore: prefer_initializing_formals
    : _dio = dio,
       // ignore: prefer_initializing_formals
       _endpoint = endpoint,
       // ignore: prefer_initializing_formals
       _headers = headers;

  final Dio _dio;
  final String _endpoint;
  final Map<String, String> _headers;

  /// Closes the underlying [Dio] client, aborting any in-flight request.
  /// Called by `GazerTelemetry.init`/`resetForTest` on the *previous*
  /// exporter whenever telemetry config is reloaded, so a config reload
  /// never leaks the old client's connection pool.
  void close() => _dio.close(force: true);

  /// Builds the OTLP-JSON body via [buildBody] and POSTs it to
  /// `'$_endpoint$path'`. Returns `true` on any 2xx response; `false` on
  /// any other status or exception -- **including an exception thrown by
  /// [buildBody] itself** (e.g. a caller-supplied attribute value whose
  /// `toString()` throws) -- so a dead collector, a malformed record, or
  /// an unencodable attribute never propagates to the caller. [buildBody]
  /// is evaluated lazily, inside this guard, rather than by the caller
  /// beforehand, specifically so encoding shares the same never-throw
  /// boundary as the network call.
  Future<bool> post(
    String path,
    Map<String, Object?> Function() buildBody,
  ) async {
    try {
      final Map<String, Object?> body = buildBody();
      final Response<dynamic> response = await _dio.post<dynamic>(
        '$_endpoint$path',
        data: jsonEncode(body),
        options: Options(
          headers: <String, String>{
            'Content-Type': 'application/json',
            ..._headers,
          },
          sendTimeout: const Duration(seconds: 5),
          receiveTimeout: const Duration(seconds: 5),
        ),
      );
      final int status = response.statusCode ?? 0;
      return status >= 200 && status < 300;
    } catch (_) {
      return false;
    }
  }

  /// Encodes the `resource` block shared by every OTLP payload type.
  static Map<String, Object?> resource({
    required String serviceName,
    required String serviceVersion,
    required String deploymentEnvironment,
    String? deviceModel,
  }) {
    return <String, Object?>{
      'attributes': <Map<String, Object?>>[
        attribute('service.name', serviceName),
        attribute('service.version', serviceVersion),
        attribute('deployment.environment', deploymentEnvironment),
        if (deviceModel != null && deviceModel.isNotEmpty)
          attribute('device.model', deviceModel),
      ],
    };
  }

  /// One OTLP `KeyValue` attribute, string-valued (the only value type this
  /// app's telemetry attributes ever need -- never pass PII, secrets, or a
  /// raw device identifier as [value]).
  static Map<String, Object?> attribute(String key, Object? value) =>
      <String, Object?>{
        'key': key,
        'value': <String, Object?>{'stringValue': value.toString()},
      };

  /// Encodes a `resourceLogs` OTLP/HTTP JSON body for one batch of log
  /// records.
  static Map<String, Object?> encodeLogs({
    required Map<String, Object?> resourceAttrs,
    required List<OtlpLogRecord> records,
  }) {
    return <String, Object?>{
      'resourceLogs': <Map<String, Object?>>[
        <String, Object?>{
          'resource': resourceAttrs,
          'scopeLogs': <Map<String, Object?>>[
            <String, Object?>{
              'logRecords': <Map<String, Object?>>[
                for (final OtlpLogRecord r in records)
                  <String, Object?>{
                    'timeUnixNano': _nanos(r.time),
                    'severityText': r.level,
                    'body': <String, Object?>{'stringValue': r.event},
                    'attributes': <Map<String, Object?>>[
                      for (final e in r.attributes.entries)
                        attribute(e.key, e.value),
                    ],
                  },
              ],
            },
          ],
        },
      ],
    };
  }

  /// Encodes a `resourceMetrics` OTLP/HTTP JSON body. Points sharing a
  /// `name`+`kind` are grouped into one `Metric` entry with multiple data
  /// points.
  static Map<String, Object?> encodeMetrics({
    required Map<String, Object?> resourceAttrs,
    required List<OtlpMetricPoint> points,
  }) {
    final Map<String, List<OtlpMetricPoint>> byNameAndKind =
        <String, List<OtlpMetricPoint>>{};
    for (final OtlpMetricPoint p in points) {
      byNameAndKind
          .putIfAbsent('${p.name}|${p.kind}', () => <OtlpMetricPoint>[])
          .add(p);
    }
    return <String, Object?>{
      'resourceMetrics': <Map<String, Object?>>[
        <String, Object?>{
          'resource': resourceAttrs,
          'scopeMetrics': <Map<String, Object?>>[
            <String, Object?>{
              'metrics': <Map<String, Object?>>[
                for (final group in byNameAndKind.values)
                  _encodeMetricGroup(group),
              ],
            },
          ],
        },
      ],
    };
  }

  static Map<String, Object?> _encodeMetricGroup(List<OtlpMetricPoint> group) {
    final String name = group.first.name;
    final String kind = group.first.kind;
    switch (kind) {
      case 'histogram':
        return <String, Object?>{
          'name': name,
          'histogram': <String, Object?>{
            'aggregationTemporality':
                1, // DELTA -- see class doc: each observation is its own bucket
            'dataPoints': <Map<String, Object?>>[
              for (final OtlpMetricPoint p in group)
                <String, Object?>{
                  'timeUnixNano': _nanos(p.time),
                  'count': '1',
                  'sum': p.value,
                  'min': p.value,
                  'max': p.value,
                  'explicitBounds': <double>[],
                  'bucketCounts': <String>['1'],
                  'attributes': <Map<String, Object?>>[
                    for (final e in p.attributes.entries)
                      attribute(e.key, e.value),
                  ],
                },
            ],
          },
        };
      case 'counter':
        return <String, Object?>{
          'name': name,
          'sum': <String, Object?>{
            'isMonotonic': true,
            'aggregationTemporality': 1, // DELTA -- each counter() call is one +1 delta, not a running total
            'dataPoints': _plainDataPoints(group),
          },
        };
      default: // gauge
        return <String, Object?>{
          'name': name,
          'gauge': <String, Object?>{'dataPoints': _plainDataPoints(group)},
        };
    }
  }

  static List<Map<String, Object?>> _plainDataPoints(
    List<OtlpMetricPoint> group,
  ) {
    return <Map<String, Object?>>[
      for (final OtlpMetricPoint p in group)
        <String, Object?>{
          'timeUnixNano': _nanos(p.time),
          'asDouble': p.value,
          'attributes': <Map<String, Object?>>[
            for (final e in p.attributes.entries) attribute(e.key, e.value),
          ],
        },
    ];
  }

  /// Encodes a `resourceSpans` OTLP/HTTP JSON body for one batch of
  /// completed spans.
  static Map<String, Object?> encodeSpans({
    required Map<String, Object?> resourceAttrs,
    required List<OtlpSpanRecord> spans,
  }) {
    return <String, Object?>{
      'resourceSpans': <Map<String, Object?>>[
        <String, Object?>{
          'resource': resourceAttrs,
          'scopeSpans': <Map<String, Object?>>[
            <String, Object?>{
              'spans': <Map<String, Object?>>[
                for (final OtlpSpanRecord s in spans)
                  <String, Object?>{
                    'name': s.name,
                    'startTimeUnixNano': _nanos(s.start),
                    'endTimeUnixNano': _nanos(s.end),
                    'attributes': <Map<String, Object?>>[
                      for (final e in s.attributes.entries)
                        attribute(e.key, e.value),
                    ],
                  },
              ],
            },
          ],
        },
      ],
    };
  }

  /// OTLP JSON encodes 64-bit integers (including nanosecond timestamps) as
  /// decimal strings -- see the OTLP spec's JSON Protobuf Encoding section.
  static String _nanos(DateTime t) =>
      (t.microsecondsSinceEpoch * 1000).toString();
}
