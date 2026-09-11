import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app.dart';
import 'telemetry/gazer_telemetry.dart';
import 'telemetry/telemetry_config.dart';

/// Entry point for the Gazer mobile app.
///
/// Wraps [GazerApp] in a [ProviderScope] so every Riverpod provider in the
/// widget tree resolves against the real (non-test) provider graph. Also
/// resolves and applies [TelemetryConfig] before the first frame -- so
/// telemetry buffering (and export, if an endpoint is configured) is live
/// from the very first log/metric/span the app emits -- and records the
/// resulting startup latency as `gazer.app.startup_ms`.
Future<void> main() async {
  final Stopwatch startupTimer = Stopwatch()..start();
  WidgetsFlutterBinding.ensureInitialized();

  final PackageInfo packageInfo = await PackageInfo.fromPlatform();
  final TelemetryConfig telemetryConfig = await TelemetryConfig.load(
    prefs: SharedPreferencesAsync(),
    secure: const FlutterSecureStorage(),
    serviceVersion: packageInfo.version,
  );
  GazerTelemetry.init(telemetryConfig);

  startupTimer.stop();
  GazerTelemetry.histogram(
    'gazer.app.startup_ms',
    startupTimer.elapsedMilliseconds.toDouble(),
  );

  runApp(const ProviderScope(child: GazerApp()));
}
