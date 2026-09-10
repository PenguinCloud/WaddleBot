import 'package:dio/dio.dart';

import '../models/update_info.dart';

/// Polls GitHub Releases for `penguintechinc/waddlebot` and reports the
/// newest `gazer-vX.Y.Z` tag, if it is newer than [currentVersion].
///
/// Non-blocking, startup-only in the app shell; any failure (network,
/// malformed body, unparseable tags) resolves to `null` rather than
/// throwing — an update notice is never worth crashing over.
class UpdateChecker {
  UpdateChecker({
    required this._dio,
    required this.currentVersion,
    this.releasesUrl =
        'https://api.github.com/repos/penguintechinc/waddlebot/releases',
  });

  final Dio _dio;

  /// The running app's version, from `package_info_plus`.
  final String currentVersion;

  /// GitHub Releases API endpoint to poll.
  final String releasesUrl;

  static final RegExp _tagPattern = RegExp(r'^gazer-v(\d+)\.(\d+)\.(\d+)$');
  static final RegExp _semverPrefix = RegExp(r'^(\d+)\.(\d+)\.(\d+)');

  /// Returns [UpdateInfo] for the newest `gazer-v*` release strictly newer
  /// than [currentVersion], or `null` when up to date or on any error.
  Future<UpdateInfo?> check() async {
    try {
      final response = await _dio.get<List<dynamic>>(releasesUrl);
      final releases = response.data as List<dynamic>;

      String? bestTag;
      List<int>? bestVersion;
      String? bestUrl;
      for (final release in releases) {
        final map = release as Map<String, dynamic>;
        final tagName = map['tag_name'] as String?;
        if (tagName == null) continue;
        final match = _tagPattern.firstMatch(tagName);
        if (match == null) continue;
        final version = [
          int.parse(match.group(1)!),
          int.parse(match.group(2)!),
          int.parse(match.group(3)!),
        ];
        if (bestVersion == null || _compare(version, bestVersion) > 0) {
          bestVersion = version;
          bestTag = tagName;
          bestUrl = map['html_url'] as String?;
        }
      }
      if (bestVersion == null || bestTag == null || bestUrl == null) {
        return null;
      }

      final current = _parseSemver(currentVersion);
      if (current != null && _compare(bestVersion, current) <= 0) {
        return null;
      }

      return UpdateInfo(
        latestVersion: bestTag.substring('gazer-v'.length),
        currentVersion: currentVersion,
        releaseUrl: Uri.parse(bestUrl),
      );
    } catch (_) {
      return null;
    }
  }

  List<int>? _parseSemver(String v) {
    final match = _semverPrefix.firstMatch(v);
    if (match == null) return null;
    return [
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      int.parse(match.group(3)!),
    ];
  }

  int _compare(List<int> a, List<int> b) {
    for (var i = 0; i < 3; i++) {
      if (a[i] != b[i]) return a[i].compareTo(b[i]);
    }
    return 0;
  }
}
