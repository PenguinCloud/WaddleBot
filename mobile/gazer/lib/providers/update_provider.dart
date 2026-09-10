import 'package:dio/dio.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../config/constants.dart';
import '../models/update_info.dart';
import '../services/update_checker.dart';

part 'update_provider.g.dart';

/// The [UpdateChecker] the app uses; overridden in tests with one wired to
/// a mocked Dio.
///
/// [UpdateChecker.releasesUrl] is wired explicitly to [kGithubReleasesUrl]
/// rather than the constructor's own literal default, so the single
/// source of truth in `config/constants.dart` is what production actually
/// polls.
@Riverpod(keepAlive: true)
Future<UpdateChecker> updateChecker(Ref ref) async {
  final packageInfo = await PackageInfo.fromPlatform();
  return UpdateChecker(
    dio: Dio(),
    currentVersion: packageInfo.version,
    releasesUrl: kGithubReleasesUrl,
  );
}

/// Startup, non-blocking update check surfaced in the status panel.
@riverpod
Future<UpdateInfo?> updateInfo(Ref ref) async {
  final checker = await ref.watch(updateCheckerProvider.future);
  return checker.check();
}
