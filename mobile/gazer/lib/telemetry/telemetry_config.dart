import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// shared_preferences key for the user-configurable OTLP endpoint override
/// (Settings > Developer > Telemetry endpoint). Non-secret: an endpoint URL
/// alone carries no credentials.
const String kTelemetryEndpointKey = 'gazer.telemetry.endpoint';

/// flutter_secure_storage key for the user-configurable OTLP headers
/// override -- secure storage because a header commonly carries an auth
/// token (e.g. `authorization: Bearer ...`).
const String kTelemetryHeadersKey = 'gazer.telemetry.headers';

/// Resolved OpenTelemetry export configuration.
///
/// Resolution order, independently per field: a non-empty Settings >
/// Developer value wins; otherwise the matching `--dart-define`
/// (`OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_HEADERS`) is used;
/// otherwise the field is empty. An empty [endpoint] after resolution means
/// telemetry export is disabled -- every signal still records to
/// `GazerTelemetry`'s in-memory ring buffer, it just never leaves the
/// device.
class TelemetryConfig {
  const TelemetryConfig({
    required this.endpoint,
    required this.protocol,
    required this.headers,
    required this.serviceName,
    required this.serviceVersion,
    required this.deploymentEnvironment,
  });

  /// OTLP receiver base URL, e.g. `'https://otel.example.com:4318'`; empty
  /// disables export.
  final String endpoint;

  /// Always `'http/json'` in M1 regardless of what
  /// `OTEL_EXPORTER_OTLP_PROTOCOL` requests -- `grpc`/`http/protobuf` are
  /// standard values but this app has no gRPC/protobuf codegen (see the
  /// design spec's Observability section for why). Recorded so a future
  /// milestone can honour it once a gRPC/protobuf path exists.
  final String protocol;

  /// Extra headers sent with every export POST, e.g. an auth bearer token.
  final Map<String, String> headers;

  /// `OTEL_SERVICE_NAME`; defaults to `'gazer'`.
  final String serviceName;

  /// `service.version` resource attribute -- this app's own version via
  /// `package_info_plus`, never a define.
  final String serviceVersion;

  /// `deployment.environment` resource attribute; `--dart-define=GAZER_ENV`,
  /// defaults to `'dev'`.
  final String deploymentEnvironment;

  static const String _defineEndpoint = String.fromEnvironment(
    'OTEL_EXPORTER_OTLP_ENDPOINT',
  );
  static const String _defineHeaders = String.fromEnvironment(
    'OTEL_EXPORTER_OTLP_HEADERS',
  );
  static const String _defineServiceName = String.fromEnvironment(
    'OTEL_SERVICE_NAME',
    defaultValue: 'gazer',
  );
  static const String _defineEnv = String.fromEnvironment(
    'GAZER_ENV',
    defaultValue: 'dev',
  );

  /// Resolves a [TelemetryConfig] from the persisted Settings overrides
  /// (pass `''` for whichever was never saved) and this app's own version.
  factory TelemetryConfig.resolve({
    required String settingsEndpoint,
    required String settingsHeadersJson,
    required String serviceVersion,
  }) {
    return TelemetryConfig(
      endpoint: settingsEndpoint.isNotEmpty
          ? settingsEndpoint
          : _defineEndpoint,
      protocol: 'http/json',
      headers: _parseHeaders(
        settingsHeadersJson.isNotEmpty ? settingsHeadersJson : _defineHeaders,
      ),
      serviceName: _defineServiceName,
      serviceVersion: serviceVersion,
      deploymentEnvironment: _defineEnv,
    );
  }

  /// Reads the persisted Settings > Developer overrides (a missing key
  /// means "not set") and resolves the effective config -- the one call
  /// site both `main.dart` and `telemetryConfigProvider` use.
  static Future<TelemetryConfig> load({
    required SharedPreferencesAsync prefs,
    required FlutterSecureStorage secure,
    required String serviceVersion,
  }) async {
    final String settingsEndpoint =
        await prefs.getString(kTelemetryEndpointKey) ?? '';
    final String settingsHeaders =
        await secure.read(key: kTelemetryHeadersKey) ?? '';
    return TelemetryConfig.resolve(
      settingsEndpoint: settingsEndpoint,
      settingsHeadersJson: settingsHeaders,
      serviceVersion: serviceVersion,
    );
  }

  /// Persists a new endpoint override; `''` clears it back to the
  /// `--dart-define` default. Called from `SettingsScreen`'s Save button.
  static Future<void> saveEndpointOverride(
    SharedPreferencesAsync prefs,
    String endpoint,
  ) => prefs.setString(kTelemetryEndpointKey, endpoint);

  /// `OTEL_EXPORTER_OTLP_HEADERS` format: comma-separated `key=value` pairs.
  /// A pair missing `=` is skipped, never thrown -- a malformed override
  /// degrades to "that one header is missing", not a crash.
  static Map<String, String> _parseHeaders(String raw) {
    if (raw.isEmpty) return const <String, String>{};
    final result = <String, String>{};
    for (final String pair in raw.split(',')) {
      final int idx = pair.indexOf('=');
      if (idx <= 0) continue;
      result[pair.substring(0, idx).trim()] = pair.substring(idx + 1).trim();
    }
    return result;
  }
}
