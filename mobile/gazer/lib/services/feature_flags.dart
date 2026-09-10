import '../models/license_state.dart';

/// Read-only view over a [LicenseState] for flag checks.
///
/// A key absent from `state.flags` is treated as OFF, never as an error —
/// this is what makes "never-seen flags default OFF" true regardless of
/// whether the license server has ever heard of a given flag key.
class FeatureFlags {
  const FeatureFlags(this._state);

  final LicenseState _state;

  /// Whether [key] is enabled; defaults to `false` if [key] was never
  /// returned by the server.
  bool isEnabled(String key) => _state.flags[key] ?? false;

  /// Whether at least one successful validate+features fetch has ever
  /// completed. The first-launch rule blocks Go Live until this is true.
  bool get hasFetchedOnce => _state.lastFetched != null;
}
