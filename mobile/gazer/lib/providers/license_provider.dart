import 'package:device_info_plus/device_info_plus.dart';
import 'package:dio/dio.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/constants.dart';
import '../models/license_state.dart';
import '../services/device_id.dart';
import '../services/feature_flags.dart';
import '../services/keepalive_scheduler.dart';
import '../services/license_client.dart';

part 'license_provider.g.dart';

/// Constructs the [LicenseClient] the app talks to; overridden with a fake
/// in tests so no real HTTP call or platform channel is ever hit.
@Riverpod(keepAlive: true)
Future<LicenseClient> licenseClient(Ref ref) async {
  final packageInfo = await PackageInfo.fromPlatform();
  final deviceIdProvider = AndroidDeviceIdProvider(
    deviceInfo: DeviceInfoPlugin(),
    packageInfo: packageInfo,
  );
  return LicenseClient(
    dio: Dio(),
    cache: LicenseCache(SharedPreferencesAsync()),
    deviceIdProvider: deviceIdProvider,
    now: DateTime.now,
  );
}

/// Validates the license and fetches feature flags once at startup.
///
/// `keepAlive: true`: a single validation per app session, not re-fetched
/// on every screen visit — the app shell's separate keepalive timer is
/// what refreshes staleness while foregrounded.
@Riverpod(keepAlive: true)
Future<LicenseState> license(Ref ref) async {
  final client = await ref.watch(licenseClientProvider.future);
  return client.validateAndFetchFlags();
}

/// Read-only view over [license] for flag checks; never throws — while
/// [license] is loading or has errored, flags default to all-OFF via
/// [LicenseState.initial]'s empty flag map, since [FeatureFlags.isEnabled]
/// treats an absent key as OFF.
///
/// Uses [AsyncValue.value] (riverpod 3.4.3's nullable data accessor — the
/// `valueOrNull` name from earlier riverpod major versions no longer
/// exists), which is `null` while loading or erroring, same as
/// `valueOrNull` behaved.
@riverpod
FeatureFlags featureFlags(Ref ref) {
  final asyncState = ref.watch(licenseProvider);
  final state = asyncState.value ?? LicenseState.initial('');
  return FeatureFlags(state);
}

/// The app-wide [KeepaliveScheduler], pinging the license server every
/// [kLicenseKeepaliveInterval] while foregrounded — [GazerApp] starts it
/// once the first [license] fetch resolves and drives it thereafter via
/// `WidgetsBindingObserver.didChangeAppLifecycleState`.
///
/// `ref.onDispose(scheduler.stop)` guarantees the underlying [Timer] is
/// always cancelled when the provider container is disposed — including
/// in widget tests, where every `pumpGazerApp` call creates a fresh
/// `ProviderScope` that must never leak a pending [Timer] into the next
/// test.
@Riverpod(keepAlive: true)
KeepaliveScheduler keepaliveScheduler(Ref ref) {
  final scheduler = KeepaliveScheduler(
    ping: () async {
      final LicenseClient client = await ref.read(licenseClientProvider.future);
      await client.keepalive();
    },
    interval: kLicenseKeepaliveInterval,
  );
  ref.onDispose(scheduler.stop);
  return scheduler;
}
