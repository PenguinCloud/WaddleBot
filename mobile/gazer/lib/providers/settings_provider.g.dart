// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'settings_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The [SettingsRepository] implementation the app uses; overridden in
/// tests with a fake so [SettingsNotifier] never touches real storage.

@ProviderFor(settingsRepository)
final settingsRepositoryProvider = SettingsRepositoryProvider._();

/// The [SettingsRepository] implementation the app uses; overridden in
/// tests with a fake so [SettingsNotifier] never touches real storage.

final class SettingsRepositoryProvider
    extends
        $FunctionalProvider<
          SettingsRepository,
          SettingsRepository,
          SettingsRepository
        >
    with $Provider<SettingsRepository> {
  /// The [SettingsRepository] implementation the app uses; overridden in
  /// tests with a fake so [SettingsNotifier] never touches real storage.
  SettingsRepositoryProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'settingsRepositoryProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$settingsRepositoryHash();

  @$internal
  @override
  $ProviderElement<SettingsRepository> $createElement(
    $ProviderPointer pointer,
  ) => $ProviderElement(pointer);

  @override
  SettingsRepository create(Ref ref) {
    return settingsRepository(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(SettingsRepository value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<SettingsRepository>(value),
    );
  }
}

String _$settingsRepositoryHash() =>
    r'1cccbb9ebd7f08e53072aea3c2863910eda6d71f';

/// Loads, holds, and persists the user's [GazerSettings].
///
/// `keepAlive: true` because settings must survive navigation between
/// HomeScreen and SettingsScreen without re-reading storage on every visit.
///
/// Generates `settingsProvider`, not `settingsNotifierProvider`:
/// riverpod_generator's default `provider_name_strip_pattern` (`Notifier$`)
/// strips a trailing "Notifier" from an annotated class name before
/// appending "Provider", specifically to avoid "NotifierNotifierProvider"
/// stuttering — this is the generator's stable, documented default across
/// versions, not a quirk of this pin. Every other provider in this file set
/// is function-based (`license`, `featureFlags`, `videoDevices`, ...), so
/// this stripping only ever applies here. Consumers (Task 13+ UI) import
/// `settingsProvider`.

@ProviderFor(SettingsNotifier)
final settingsProvider = SettingsNotifierProvider._();

/// Loads, holds, and persists the user's [GazerSettings].
///
/// `keepAlive: true` because settings must survive navigation between
/// HomeScreen and SettingsScreen without re-reading storage on every visit.
///
/// Generates `settingsProvider`, not `settingsNotifierProvider`:
/// riverpod_generator's default `provider_name_strip_pattern` (`Notifier$`)
/// strips a trailing "Notifier" from an annotated class name before
/// appending "Provider", specifically to avoid "NotifierNotifierProvider"
/// stuttering — this is the generator's stable, documented default across
/// versions, not a quirk of this pin. Every other provider in this file set
/// is function-based (`license`, `featureFlags`, `videoDevices`, ...), so
/// this stripping only ever applies here. Consumers (Task 13+ UI) import
/// `settingsProvider`.
final class SettingsNotifierProvider
    extends $AsyncNotifierProvider<SettingsNotifier, GazerSettings> {
  /// Loads, holds, and persists the user's [GazerSettings].
  ///
  /// `keepAlive: true` because settings must survive navigation between
  /// HomeScreen and SettingsScreen without re-reading storage on every visit.
  ///
  /// Generates `settingsProvider`, not `settingsNotifierProvider`:
  /// riverpod_generator's default `provider_name_strip_pattern` (`Notifier$`)
  /// strips a trailing "Notifier" from an annotated class name before
  /// appending "Provider", specifically to avoid "NotifierNotifierProvider"
  /// stuttering — this is the generator's stable, documented default across
  /// versions, not a quirk of this pin. Every other provider in this file set
  /// is function-based (`license`, `featureFlags`, `videoDevices`, ...), so
  /// this stripping only ever applies here. Consumers (Task 13+ UI) import
  /// `settingsProvider`.
  SettingsNotifierProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'settingsProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$settingsNotifierHash();

  @$internal
  @override
  SettingsNotifier create() => SettingsNotifier();
}

String _$settingsNotifierHash() => r'f32da68cd31363428ef6796de056fbc25bb4fa91';

/// Loads, holds, and persists the user's [GazerSettings].
///
/// `keepAlive: true` because settings must survive navigation between
/// HomeScreen and SettingsScreen without re-reading storage on every visit.
///
/// Generates `settingsProvider`, not `settingsNotifierProvider`:
/// riverpod_generator's default `provider_name_strip_pattern` (`Notifier$`)
/// strips a trailing "Notifier" from an annotated class name before
/// appending "Provider", specifically to avoid "NotifierNotifierProvider"
/// stuttering — this is the generator's stable, documented default across
/// versions, not a quirk of this pin. Every other provider in this file set
/// is function-based (`license`, `featureFlags`, `videoDevices`, ...), so
/// this stripping only ever applies here. Consumers (Task 13+ UI) import
/// `settingsProvider`.

abstract class _$SettingsNotifier extends $AsyncNotifier<GazerSettings> {
  FutureOr<GazerSettings> build();
  @$mustCallSuper
  @override
  WhenComplete runBuild() {
    final ref = this.ref as $Ref<AsyncValue<GazerSettings>, GazerSettings>;
    final element =
        ref.element
            as $ClassProviderElement<
              AnyNotifier<AsyncValue<GazerSettings>, GazerSettings>,
              AsyncValue<GazerSettings>,
              Object?,
              Object?
            >;
    return element.handleCreate(ref, build);
  }
}
