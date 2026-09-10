// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'update_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The [UpdateChecker] the app uses; overridden in tests with one wired to
/// a mocked Dio.
///
/// [UpdateChecker.releasesUrl] is wired explicitly to [kGithubReleasesUrl]
/// rather than the constructor's own literal default, so the single
/// source of truth in `config/constants.dart` is what production actually
/// polls.

@ProviderFor(updateChecker)
final updateCheckerProvider = UpdateCheckerProvider._();

/// The [UpdateChecker] the app uses; overridden in tests with one wired to
/// a mocked Dio.
///
/// [UpdateChecker.releasesUrl] is wired explicitly to [kGithubReleasesUrl]
/// rather than the constructor's own literal default, so the single
/// source of truth in `config/constants.dart` is what production actually
/// polls.

final class UpdateCheckerProvider
    extends
        $FunctionalProvider<
          AsyncValue<UpdateChecker>,
          UpdateChecker,
          FutureOr<UpdateChecker>
        >
    with $FutureModifier<UpdateChecker>, $FutureProvider<UpdateChecker> {
  /// The [UpdateChecker] the app uses; overridden in tests with one wired to
  /// a mocked Dio.
  ///
  /// [UpdateChecker.releasesUrl] is wired explicitly to [kGithubReleasesUrl]
  /// rather than the constructor's own literal default, so the single
  /// source of truth in `config/constants.dart` is what production actually
  /// polls.
  UpdateCheckerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'updateCheckerProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$updateCheckerHash();

  @$internal
  @override
  $FutureProviderElement<UpdateChecker> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<UpdateChecker> create(Ref ref) {
    return updateChecker(ref);
  }
}

String _$updateCheckerHash() => r'5bb6d8058fc2f09aa42db041ad278579d19d0719';

/// Startup, non-blocking update check surfaced in the status panel.

@ProviderFor(updateInfo)
final updateInfoProvider = UpdateInfoProvider._();

/// Startup, non-blocking update check surfaced in the status panel.

final class UpdateInfoProvider
    extends
        $FunctionalProvider<
          AsyncValue<UpdateInfo?>,
          UpdateInfo?,
          FutureOr<UpdateInfo?>
        >
    with $FutureModifier<UpdateInfo?>, $FutureProvider<UpdateInfo?> {
  /// Startup, non-blocking update check surfaced in the status panel.
  UpdateInfoProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'updateInfoProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$updateInfoHash();

  @$internal
  @override
  $FutureProviderElement<UpdateInfo?> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<UpdateInfo?> create(Ref ref) {
    return updateInfo(ref);
  }
}

String _$updateInfoHash() => r'717902bb002e48c65783b5c9d7685a55494638cd';
