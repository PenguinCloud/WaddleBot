import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/update_info.dart';
import 'package:gazer/providers/update_provider.dart';
import 'package:gazer/services/update_checker.dart';

class _FakeUpdateChecker implements UpdateChecker {
  _FakeUpdateChecker(this.result);

  final UpdateInfo? result;

  @override
  Future<UpdateInfo?> check() async => result;

  @override
  String get currentVersion => '1.0.0';

  @override
  String get releasesUrl => 'https://example.com';
}

void main() {
  test('updateInfoProvider forwards UpdateChecker.check()', () async {
    final info = UpdateInfo(
      latestVersion: '1.1.0',
      currentVersion: '1.0.0',
      releaseUrl: Uri.parse('https://example.com/release'),
    );
    final container = ProviderContainer(
      overrides: [
        updateCheckerProvider.overrideWith(
          (ref) async => _FakeUpdateChecker(info),
        ),
      ],
    );
    addTearDown(container.dispose);

    final result = await container.read(updateInfoProvider.future);

    expect(result, info);
  });

  test('updateInfoProvider is null when no update is available', () async {
    final container = ProviderContainer(
      overrides: [
        updateCheckerProvider.overrideWith(
          (ref) async => _FakeUpdateChecker(null),
        ),
      ],
    );
    addTearDown(container.dispose);

    final result = await container.read(updateInfoProvider.future);

    expect(result, isNull);
  });
}
