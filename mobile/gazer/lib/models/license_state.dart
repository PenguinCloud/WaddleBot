import 'package:freezed_annotation/freezed_annotation.dart';

part 'license_state.freezed.dart';
part 'license_state.g.dart';

/// Result of the most recent license/feature-flag validation.
///
/// `unknown` means no successful fetch has ever completed and no usable
/// cache exists (blocks streaming per the first-launch rule); `gracePeriod`
/// means the server is unreachable but the cache is within its 7-day grace
/// window.
enum LicenseStatus { unknown, valid, gracePeriod, invalid }

/// Cached license/feature-flag state, persisted as JSON by `LicenseCache`.
///
/// [flags] holds every flag key the server has ever returned; a key absent
/// from this map is treated as OFF by `FeatureFlags`, never as an error.
@freezed
abstract class LicenseState with _$LicenseState {
  const factory LicenseState({
    required LicenseStatus status,
    required Map<String, bool> flags,
    DateTime? lastFetched,
    required String deviceId,
  }) = _LicenseState;

  /// Deserializes a [LicenseState] from JSON (`LicenseCache` reads this
  /// back from `shared_preferences` key `gazer.license.state`).
  factory LicenseState.fromJson(Map<String, dynamic> json) =>
      _$LicenseStateFromJson(json);

  /// Pre-first-fetch state for a freshly resolved [deviceId]: unknown
  /// status, no flags, never fetched.
  factory LicenseState.initial(String deviceId) => LicenseState(
    status: LicenseStatus.unknown,
    flags: const {},
    lastFetched: null,
    deviceId: deviceId,
  );
}
