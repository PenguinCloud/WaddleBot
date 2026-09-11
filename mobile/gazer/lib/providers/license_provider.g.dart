// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'license_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Constructs the [LicenseClient] the app talks to; overridden with a fake
/// in tests so no real HTTP call or platform channel is ever hit.

@ProviderFor(licenseClient)
final licenseClientProvider = LicenseClientProvider._();

/// Constructs the [LicenseClient] the app talks to; overridden with a fake
/// in tests so no real HTTP call or platform channel is ever hit.

final class LicenseClientProvider
    extends
        $FunctionalProvider<
          AsyncValue<LicenseClient>,
          LicenseClient,
          FutureOr<LicenseClient>
        >
    with $FutureModifier<LicenseClient>, $FutureProvider<LicenseClient> {
  /// Constructs the [LicenseClient] the app talks to; overridden with a fake
  /// in tests so no real HTTP call or platform channel is ever hit.
  LicenseClientProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'licenseClientProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$licenseClientHash();

  @$internal
  @override
  $FutureProviderElement<LicenseClient> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<LicenseClient> create(Ref ref) {
    return licenseClient(ref);
  }
}

String _$licenseClientHash() => r'b08af60b52b979d9229e7a75ff9c2ea3a02f9332';

/// Validates the license and fetches feature flags once at startup.
///
/// `keepAlive: true`: a single validation per app session, not re-fetched
/// on every screen visit — the app shell's separate keepalive timer is
/// what refreshes staleness while foregrounded.

@ProviderFor(license)
final licenseProvider = LicenseProvider._();

/// Validates the license and fetches feature flags once at startup.
///
/// `keepAlive: true`: a single validation per app session, not re-fetched
/// on every screen visit — the app shell's separate keepalive timer is
/// what refreshes staleness while foregrounded.

final class LicenseProvider
    extends
        $FunctionalProvider<
          AsyncValue<LicenseState>,
          LicenseState,
          FutureOr<LicenseState>
        >
    with $FutureModifier<LicenseState>, $FutureProvider<LicenseState> {
  /// Validates the license and fetches feature flags once at startup.
  ///
  /// `keepAlive: true`: a single validation per app session, not re-fetched
  /// on every screen visit — the app shell's separate keepalive timer is
  /// what refreshes staleness while foregrounded.
  LicenseProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'licenseProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$licenseHash();

  @$internal
  @override
  $FutureProviderElement<LicenseState> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<LicenseState> create(Ref ref) {
    return license(ref);
  }
}

String _$licenseHash() => r'a62a4adb71d32d7c7afcc55aebb3be657c38c1b0';

/// Read-only view over [license] for flag checks; never throws — while
/// [license] is loading or has errored, flags default to all-OFF via
/// [LicenseState.initial]'s empty flag map, since [FeatureFlags.isEnabled]
/// treats an absent key as OFF.
///
/// Uses [AsyncValue.value] (riverpod 3.4.3's nullable data accessor — the
/// `valueOrNull` name from earlier riverpod major versions no longer
/// exists), which is `null` while loading or erroring, same as
/// `valueOrNull` behaved.

@ProviderFor(featureFlags)
final featureFlagsProvider = FeatureFlagsProvider._();

/// Read-only view over [license] for flag checks; never throws — while
/// [license] is loading or has errored, flags default to all-OFF via
/// [LicenseState.initial]'s empty flag map, since [FeatureFlags.isEnabled]
/// treats an absent key as OFF.
///
/// Uses [AsyncValue.value] (riverpod 3.4.3's nullable data accessor — the
/// `valueOrNull` name from earlier riverpod major versions no longer
/// exists), which is `null` while loading or erroring, same as
/// `valueOrNull` behaved.

final class FeatureFlagsProvider
    extends $FunctionalProvider<FeatureFlags, FeatureFlags, FeatureFlags>
    with $Provider<FeatureFlags> {
  /// Read-only view over [license] for flag checks; never throws — while
  /// [license] is loading or has errored, flags default to all-OFF via
  /// [LicenseState.initial]'s empty flag map, since [FeatureFlags.isEnabled]
  /// treats an absent key as OFF.
  ///
  /// Uses [AsyncValue.value] (riverpod 3.4.3's nullable data accessor — the
  /// `valueOrNull` name from earlier riverpod major versions no longer
  /// exists), which is `null` while loading or erroring, same as
  /// `valueOrNull` behaved.
  FeatureFlagsProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'featureFlagsProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$featureFlagsHash();

  @$internal
  @override
  $ProviderElement<FeatureFlags> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  FeatureFlags create(Ref ref) {
    return featureFlags(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(FeatureFlags value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<FeatureFlags>(value),
    );
  }
}

String _$featureFlagsHash() => r'5824535ddd6eab1f0d0e7c4e389e780b96698a47';

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

@ProviderFor(keepaliveScheduler)
final keepaliveSchedulerProvider = KeepaliveSchedulerProvider._();

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

final class KeepaliveSchedulerProvider
    extends
        $FunctionalProvider<
          KeepaliveScheduler,
          KeepaliveScheduler,
          KeepaliveScheduler
        >
    with $Provider<KeepaliveScheduler> {
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
  KeepaliveSchedulerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'keepaliveSchedulerProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$keepaliveSchedulerHash();

  @$internal
  @override
  $ProviderElement<KeepaliveScheduler> $createElement(
    $ProviderPointer pointer,
  ) => $ProviderElement(pointer);

  @override
  KeepaliveScheduler create(Ref ref) {
    return keepaliveScheduler(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(KeepaliveScheduler value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<KeepaliveScheduler>(value),
    );
  }
}

String _$keepaliveSchedulerHash() =>
    r'3313b05822d1e655916ae16975e9048d52bd963f';
