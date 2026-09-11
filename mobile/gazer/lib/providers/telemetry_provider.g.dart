// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'telemetry_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
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

@ProviderFor(telemetryConfig)
final telemetryConfigProvider = TelemetryConfigProvider._();

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

final class TelemetryConfigProvider
    extends
        $FunctionalProvider<
          AsyncValue<TelemetryConfig>,
          TelemetryConfig,
          FutureOr<TelemetryConfig>
        >
    with $FutureModifier<TelemetryConfig>, $FutureProvider<TelemetryConfig> {
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
  TelemetryConfigProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'telemetryConfigProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$telemetryConfigHash();

  @$internal
  @override
  $FutureProviderElement<TelemetryConfig> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<TelemetryConfig> create(Ref ref) {
    return telemetryConfig(ref);
  }
}

String _$telemetryConfigHash() => r'fabef078cbde242c177b35bf87ccf15a477d3d0f';
