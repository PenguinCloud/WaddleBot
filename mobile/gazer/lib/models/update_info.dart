/// Describes an available update, surfaced by `UpdateChecker` when the
/// latest `gazer-v*` GitHub release tag is newer than the running app.
///
/// Hand-written (not freezed): never persisted, and `Uri` has no built-in
/// json_serializable converter, so JSON codegen would need a bespoke
/// converter for no benefit — this is a display-only, in-memory value.
class UpdateInfo {
  const UpdateInfo({
    required this.latestVersion,
    required this.currentVersion,
    required this.releaseUrl,
  });

  /// Latest `gazer-vX.Y.Z` tag found on GitHub Releases, without the prefix.
  final String latestVersion;

  /// The running app's version, from `package_info_plus`.
  final String currentVersion;

  /// GitHub Release page for [latestVersion]; opened via `url_launcher`.
  final Uri releaseUrl;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is UpdateInfo &&
          other.latestVersion == latestVersion &&
          other.currentVersion == currentVersion &&
          other.releaseUrl == releaseUrl);

  @override
  int get hashCode => Object.hash(latestVersion, currentVersion, releaseUrl);

  @override
  String toString() =>
      'UpdateInfo(latestVersion: $latestVersion, currentVersion: $currentVersion, releaseUrl: $releaseUrl)';
}
