import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../telemetry/gazer_telemetry.dart';
import '../telemetry/telemetry_config.dart';

part 'telemetry_provider.g.dart';

/// Loads the resolved [TelemetryConfig] (Settings override > --dart-define
/// > default) and applies it via `GazerTelemetry.init` as a side effect --
/// so simply reading this provider once is what turns telemetry on for the
/// widget tree. `keepAlive: true`: telemetry must stay configured across
/// every screen for the app's lifetime, same rationale as
/// `licenseProvider`/`settingsNotifierProvider` (Task 12).
///
/// Not directly unit-tested -- its body calls `PackageInfo.fromPlatform()`
/// and touches real `shared_preferences`/`flutter_secure_storage` plugins,
/// so it is exercised only via `.overrideWith(...)` in downstream widget
/// tests (`SettingsScreen`/`StatusPanel`), matching the plan's established
/// leaf-provider testing boundary (`licenseClientProvider`,
/// `updateCheckerProvider`).
@Riverpod(keepAlive: true)
Future<TelemetryConfig> telemetryConfig(Ref ref) async {
  final PackageInfo packageInfo = await PackageInfo.fromPlatform();
  final TelemetryConfig config = await TelemetryConfig.load(
    prefs: SharedPreferencesAsync(),
    secure: const FlutterSecureStorage(),
    serviceVersion: packageInfo.version,
  );
  GazerTelemetry.init(config);
  return config;
}
