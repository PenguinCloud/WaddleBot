import 'dart:convert';
import 'dart:developer' as developer;

/// Structured, sanitized logging for Gazer.
///
/// Emits one JSON line per call via `dart:developer`'s `log()` — never
/// `print` — masking secrets so tokens/credentials never reach device
/// logs. [debug] only emits when [verbose] is on, wired from the user's
/// Settings > Developer > Debug logs toggle (`GazerSettings.debugLogs`).
class GazerLog {
  GazerLog._();

  /// Whether [debug] calls actually emit.
  static bool verbose = false;

  /// Where every JSON line is written; overridable in tests to capture
  /// output instead of going through `dart:developer`'s `log()`, which
  /// cannot be intercepted directly.
  static void Function(String line) sink = _developerSink;

  /// Default [sink]: writes through `dart:developer`'s `log()` under the
  /// `gazer` name, the normal production path.
  static void _developerSink(String line) => developer.log(line, name: 'gazer');

  /// Emits an `info`-level JSON line for [event] with [fields] (sanitized).
  static void info(String event, [Map<String, Object?> fields = const {}]) =>
      _emit('info', event, fields);

  /// Emits a `warn`-level JSON line for [event] with [fields] (sanitized).
  static void warn(String event, [Map<String, Object?> fields = const {}]) =>
      _emit('warn', event, fields);

  /// Emits an `error`-level JSON line for [event] with [fields] (sanitized).
  static void error(String event, [Map<String, Object?> fields = const {}]) =>
      _emit('error', event, fields);

  /// Only emits when [verbose] is enabled.
  static void debug(String event, [Map<String, Object?> fields = const {}]) {
    if (!verbose) return;
    _emit('debug', event, fields);
  }

  /// Test-only: restores [verbose] and [sink] to their production defaults
  /// (`false` and [_developerSink]). Call from `tearDown` in any test that
  /// flips [verbose] or overrides [sink] — directly, or indirectly via a
  /// real notifier/controller — so the mutation never leaks into a later
  /// test.
  static void resetForTest() {
    verbose = false;
    sink = _developerSink;
  }

  /// Builds the JSON record (`ts`/`level`/`event` plus sanitized [fields])
  /// and writes it through [sink]. Never throws: a field value `jsonEncode`
  /// can't natively encode falls back to its `toString()`, via
  /// [JsonEncoder.toEncodable], instead of propagating a
  /// [JsonUnsupportedObjectError] to the caller.
  static void _emit(String level, String event, Map<String, Object?> fields) {
    final record = <String, Object?>{
      'ts': DateTime.now().toIso8601String(),
      'level': level,
      'event': event,
      ...sanitize(fields),
    };
    sink(jsonEncode(record, toEncodable: (Object? value) => value.toString()));
  }

  /// Masks [value]: `null`/empty -> `''`; otherwise `'****'` + the last 4
  /// characters, or just `'****'` when shorter than 4 characters.
  static String maskSecret(String? value) {
    if (value == null || value.isEmpty) return '';
    if (value.length < 4) return '****';
    return '****${value.substring(value.length - 4)}';
  }

  /// Masks any field named `password`/`streamKey`/`username` wholesale via
  /// [maskSecret]; a field named `url` keeps its scheme/host but masks
  /// only its last path segment, since the full path/query may embed the
  /// stream key.
  static Map<String, Object?> sanitize(Map<String, Object?> fields) {
    return fields.map((String key, Object? value) {
      if (value is! String) return MapEntry(key, value);
      switch (key) {
        case 'password':
        case 'streamKey':
        case 'username':
          return MapEntry(key, maskSecret(value));
        case 'url':
          return MapEntry(key, _maskUrlLastSegment(value));
        default:
          return MapEntry(key, value);
      }
    });
  }

  /// Masks only the last path segment of [url] via [maskSecret], preserving
  /// scheme/host/earlier segments; returns [url] unchanged if it can't be
  /// parsed or has no path segments to mask.
  static String _maskUrlLastSegment(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null || uri.pathSegments.isEmpty) return url;
    final segments = List<String>.from(uri.pathSegments);
    segments[segments.length - 1] = maskSecret(segments.last);
    return uri.replace(pathSegments: segments).toString();
  }
}
