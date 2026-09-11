import 'dart:async';

import 'package:dio/dio.dart';

import '../services/gazer_log.dart';
import 'otlp_http_exporter.dart';
import 'telemetry_config.dart';

/// One completed or in-flight trace span. Obtained via
/// `GazerTelemetry.startSpan`; call [end] exactly once when the work it
/// covers finishes.
class Span {
  Span._(this._name) : _start = DateTime.now();

  final String _name;
  final DateTime _start;
  final Map<String, Object?> _attributes = <String, Object?>{};
  bool _ended = false;

  /// Attaches [value] under [key]; call before [end]. Never pass PII,
  /// secrets, or a raw device identifier -- see `GazerLog.sanitize` for the
  /// equivalent log-side rule.
  void setAttribute(String key, Object? value) => _attributes[key] = value;

  /// Records the span's end time and hands it to [GazerTelemetry] for
  /// export. A second call is a no-op (idempotent, so a defensive
  /// double-call from cleanup code never double-counts).
  void end() {
    if (_ended) return;
    _ended = true;
    GazerTelemetry._completeSpan(this, DateTime.now());
  }
}

/// Facade over the app's OpenTelemetry emission: structured logs, metrics
/// (histograms/counters/gauges), and traces, buffered in-memory and
/// exported every 10s as OTLP/HTTP JSON via [OtlpHttpExporter].
///
/// Every recording method is synchronous and never throws: signals always
/// land in the ring buffer (cap [ringBufferCap] per signal type,
/// drop-oldest) even when `TelemetryConfig.endpoint` is empty (export
/// disabled) or the collector is unreachable (export fails,
/// [exportFailures] increments) -- a dead or unconfigured endpoint never
/// breaks app functionality, per the house OpenTelemetry rule.
class GazerTelemetry {
  GazerTelemetry._();

  static const int ringBufferCap = 1000;
  static const Duration flushInterval = Duration(seconds: 10);

  static TelemetryConfig _config = const TelemetryConfig(
    endpoint: '',
    protocol: 'http/json',
    headers: <String, String>{},
    serviceName: 'gazer',
    serviceVersion: '0.0.0',
    deploymentEnvironment: 'dev',
  );

  static OtlpHttpExporter _exporter = OtlpHttpExporter(
    dio: Dio(),
    endpoint: '',
    headers: const <String, String>{},
  );
  static Timer? _timer;

  static final List<OtlpLogRecord> _logs = <OtlpLogRecord>[];
  static final List<OtlpMetricPoint> _metrics = <OtlpMetricPoint>[];
  static final List<OtlpSpanRecord> _spans = <OtlpSpanRecord>[];

  /// Count of export POST attempts that did not succeed for a transient
  /// (transport-level) reason -- timeout, connection refused, non-2xx --
  /// surfaced by the status panel. The batch is retained and retried on
  /// the next scheduled flush.
  static int exportFailures = 0;

  /// Count of export POST attempts that succeeded (2xx).
  static int exportSuccesses = 0;

  /// Count of batches dropped because they could not be encoded (e.g. an
  /// attribute value whose `toString()` throws, or a value `jsonEncode`
  /// cannot represent) -- distinct from [exportFailures] because retrying
  /// an un-encodable batch fails identically forever; see [_dropOnEncodeFailure].
  static int encodeFailures = 0;

  /// Applies [config] and rebuilds the exporter; starts the periodic flush
  /// scheduler on first call. Safe to call repeatedly -- e.g. every time
  /// Settings > Developer > Telemetry endpoint is saved, so a change takes
  /// effect without an app restart. The *previous* exporter's [Dio] client
  /// is closed (aborting any in-flight request) after the new one is
  /// installed, so repeated reloads never accumulate open HTTP clients or
  /// keep emitting through a stale client pointed at the old endpoint.
  static void init(TelemetryConfig config, {Dio? dio}) {
    _config = config;
    final OtlpHttpExporter previousExporter = _exporter;
    _exporter = OtlpHttpExporter(
      dio: dio ?? Dio(),
      endpoint: config.endpoint,
      headers: config.headers,
    );
    previousExporter.close();
    _timer ??= Timer.periodic(flushInterval, (_) => flush());
  }

  /// Whether the current config would actually send data over the network
  /// (a non-empty endpoint). Used by the status panel's
  /// disabled/exporting/last-export-failed line.
  static bool get isExporting => _config.endpoint.isNotEmpty;

  /// Records one structured log line. Fed automatically from `GazerLog`'s
  /// existing sanitize-then-emit path -- see this task's `gazer_log.dart`
  /// modification -- so callers normally never call this directly.
  static void recordLog(
    String level,
    String event, [
    Map<String, Object?> attributes = const <String, Object?>{},
  ]) {
    _push(_logs, (
      time: DateTime.now(),
      level: level,
      event: event,
      attributes: attributes,
    ));
  }

  /// Records one histogram observation, e.g. `gazer.rtmp.connect_latency_ms`.
  static void histogram(
    String name,
    num value, [
    Map<String, Object?> attributes = const <String, Object?>{},
  ]) {
    _push(_metrics, (
      time: DateTime.now(),
      name: name,
      kind: 'histogram',
      value: value.toDouble(),
      attributes: attributes,
    ));
  }

  /// Increments a monotonic counter by 1, e.g. `gazer.pipeline.state_change`.
  static void counter(
    String name, [
    Map<String, Object?> attributes = const <String, Object?>{},
  ]) {
    _push(_metrics, (
      time: DateTime.now(),
      name: name,
      kind: 'counter',
      value: 1.0,
      attributes: attributes,
    ));
  }

  /// Records the current value of a gauge (e.g. a queue depth) -- provided
  /// for the house metrics guidance ("gauges for state"); no M1 caller
  /// uses this yet.
  static void gauge(
    String name,
    num value, [
    Map<String, Object?> attributes = const <String, Object?>{},
  ]) {
    _push(_metrics, (
      time: DateTime.now(),
      name: name,
      kind: 'gauge',
      value: value.toDouble(),
      attributes: attributes,
    ));
  }

  /// Starts a new span named [name]; the caller must call `Span.end`
  /// exactly once when the covered work finishes.
  static Span startSpan(String name) => Span._(name);

  static void _completeSpan(Span span, DateTime end) {
    _push(_spans, (
      name: span._name,
      start: span._start,
      end: end,
      attributes: Map<String, Object?>.from(span._attributes),
    ));
  }

  static void _push<T>(List<T> buffer, T item) {
    buffer.add(item);
    if (buffer.length > ringBufferCap) buffer.removeAt(0);
  }

  /// Batches whatever is currently buffered per signal type and POSTs each
  /// non-empty batch as OTLP/HTTP JSON. A no-op (no HTTP calls at all)
  /// when [isExporting] is false. Each signal type's batch is removed
  /// from the buffer on a successful (2xx) POST *or* on an encode
  /// failure (a malformed batch would fail identically forever if kept,
  /// see [_dropOnEncodeFailure]); only a transient transport failure
  /// leaves the batch buffered for the next scheduled flush (still
  /// subject to the ring buffer's drop-oldest cap).
  static Future<void> flush() async {
    if (!isExporting) return;
    final Map<String, Object?> resourceAttrs = OtlpHttpExporter.resource(
      serviceName: _config.serviceName,
      serviceVersion: _config.serviceVersion,
      deploymentEnvironment: _config.deploymentEnvironment,
    );
    await Future.wait<void>(<Future<void>>[
      _flushLogs(resourceAttrs),
      _flushMetrics(resourceAttrs),
      _flushSpans(resourceAttrs),
    ]);
  }

  static Future<void> _flushLogs(Map<String, Object?> resourceAttrs) async {
    if (_logs.isEmpty) return;
    final List<OtlpLogRecord> batch = List<OtlpLogRecord>.of(_logs);
    // The body-builder closure is passed to `post`, not invoked here --
    // `post` evaluates it inside its own never-throw guard and reports
    // which half (encode vs. transport) failed, so this switch can tell
    // a permanently-malformed batch from a transient network error.
    final PostResult result = await _exporter.post(
      '/v1/logs',
      () => OtlpHttpExporter.encodeLogs(
        resourceAttrs: resourceAttrs,
        records: batch,
      ),
    );
    switch (result) {
      case PostResult.success:
        exportSuccesses++;
        _logs.removeRange(0, batch.length);
      case PostResult.encodeFailure:
        _logs.removeRange(0, batch.length);
        _dropOnEncodeFailure('logs', batch.length);
      case PostResult.transportFailure:
        exportFailures++;
    }
  }

  static Future<void> _flushMetrics(Map<String, Object?> resourceAttrs) async {
    if (_metrics.isEmpty) return;
    final List<OtlpMetricPoint> batch = List<OtlpMetricPoint>.of(_metrics);
    final PostResult result = await _exporter.post(
      '/v1/metrics',
      () => OtlpHttpExporter.encodeMetrics(
        resourceAttrs: resourceAttrs,
        points: batch,
      ),
    );
    switch (result) {
      case PostResult.success:
        exportSuccesses++;
        _metrics.removeRange(0, batch.length);
      case PostResult.encodeFailure:
        _metrics.removeRange(0, batch.length);
        _dropOnEncodeFailure('metrics', batch.length);
      case PostResult.transportFailure:
        exportFailures++;
    }
  }

  static Future<void> _flushSpans(Map<String, Object?> resourceAttrs) async {
    if (_spans.isEmpty) return;
    final List<OtlpSpanRecord> batch = List<OtlpSpanRecord>.of(_spans);
    final PostResult result = await _exporter.post(
      '/v1/traces',
      () => OtlpHttpExporter.encodeSpans(
        resourceAttrs: resourceAttrs,
        spans: batch,
      ),
    );
    switch (result) {
      case PostResult.success:
        exportSuccesses++;
        _spans.removeRange(0, batch.length);
      case PostResult.encodeFailure:
        _spans.removeRange(0, batch.length);
        _dropOnEncodeFailure('spans', batch.length);
      case PostResult.transportFailure:
        exportFailures++;
    }
  }

  /// Counts and logs (once, at DEBUG) a batch dropped because it could
  /// not be encoded -- an un-encodable record (e.g. a `toString()` that
  /// throws) would fail identically on every future retry, so the batch
  /// is dropped rather than left to block every later record of the same
  /// signal type (buffered and incoming) until the ring buffer's
  /// drop-oldest cap eventually evicts it -- effectively an unbounded
  /// blackout for that signal. Logs [signal] and [count] only, never
  /// attribute values, since the value that failed to encode may not be
  /// sanitized (it never reached `GazerLog.sanitize`). A no-op beyond the
  /// counter increment unless `GazerLog.verbose` is on, per
  /// `GazerLog.debug`'s normal gating.
  static void _dropOnEncodeFailure(String signal, int count) {
    encodeFailures++;
    GazerLog.debug('telemetry.encodeFailure', <String, Object?>{
      'signal': signal,
      'count': count,
    });
  }

  /// Test/teardown hook: cancels the flush scheduler and clears every
  /// buffer, counter, and config back to the inert default. Not used by
  /// production code -- call in `tearDown` of any test that calls [init].
  static void resetForTest() {
    _timer?.cancel();
    _timer = null;
    _logs.clear();
    _metrics.clear();
    _spans.clear();
    exportFailures = 0;
    exportSuccesses = 0;
    encodeFailures = 0;
    _config = const TelemetryConfig(
      endpoint: '',
      protocol: 'http/json',
      headers: <String, String>{},
      serviceName: 'gazer',
      serviceVersion: '0.0.0',
      deploymentEnvironment: 'dev',
    );
    _exporter = OtlpHttpExporter(
      dio: Dio(),
      endpoint: '',
      headers: const <String, String>{},
    );
  }
}
