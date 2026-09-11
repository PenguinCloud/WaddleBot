import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/update_info.dart';
import 'package:gazer/services/license_client.dart';
import 'package:gazer/services/settings_repository.dart';
import 'package:gazer/services/update_checker.dart';

/// In-memory [SettingsRepository] for widget tests.
///
/// Starts from an injected seed (or [GazerSettings.defaults]) and never
/// touches `flutter_secure_storage`/`shared_preferences` plugin channels,
/// so it runs under plain `flutter test` with no platform mocking.
class FakeSettingsRepository implements SettingsRepository {
  FakeSettingsRepository([GazerSettings? seed])
    : _current = seed ?? GazerSettings.defaults();

  GazerSettings _current;

  /// Every value passed to [save], in call order — tests assert against
  /// this instead of re-reading through [load].
  final List<GazerSettings> saved = <GazerSettings>[];

  /// When set, [save] throws this instead of persisting — lets tests
  /// exercise a caller's save-failure error handling without a real
  /// storage backend.
  Object? saveError;

  @override
  Future<GazerSettings> load() async => _current;

  @override
  Future<void> save(GazerSettings s) async {
    final Object? error = saveError;
    if (error != null) {
      throw error;
    }
    _current = s;
    saved.add(s);
  }
}

/// Test double for [LicenseClient] — returns a canned [LicenseState]
/// instead of calling `license.penguintech.io`.
///
/// `LicenseClient` is a concrete class (not an abstract interface), so
/// `implements` here must also re-declare its public `baseUrl` field —
/// unused by any test, but required for the interface to be satisfied.
class FakeLicenseClient implements LicenseClient {
  FakeLicenseClient(this.stateToReturn);

  /// The [LicenseState] every [validateAndFetchFlags] call resolves to.
  final LicenseState stateToReturn;

  /// Number of times [keepalive] was called.
  int keepaliveCalls = 0;

  @override
  final String baseUrl = 'https://fake.license.invalid';

  @override
  Future<LicenseState> validateAndFetchFlags() async => stateToReturn;

  @override
  Future<void> keepalive() async {
    keepaliveCalls++;
  }
}

/// Test double for [UpdateChecker] — returns a canned (possibly `null`)
/// [UpdateInfo] instead of calling the GitHub releases API.
///
/// `UpdateChecker` is a concrete class (not an abstract interface), so
/// `implements` here must also re-declare its public `currentVersion` and
/// `releasesUrl` fields — unused by any test, but required for the
/// interface to be satisfied.
class FakeUpdateChecker implements UpdateChecker {
  FakeUpdateChecker([this.infoToReturn]);

  /// The value every [check] call resolves to; `null` means "up to date".
  final UpdateInfo? infoToReturn;

  @override
  final String currentVersion = '0.0.0';

  @override
  final String releasesUrl = 'https://fake.releases.invalid';

  @override
  Future<UpdateInfo?> check() async => infoToReturn;
}
