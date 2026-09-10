// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'devices_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// The [GazerHostApi] the app talks to; overridden in tests with
/// `FakeGazerHostApi` so no real Pigeon channel is ever touched.

@ProviderFor(gazerHostApi)
final gazerHostApiProvider = GazerHostApiProvider._();

/// The [GazerHostApi] the app talks to; overridden in tests with
/// `FakeGazerHostApi` so no real Pigeon channel is ever touched.

final class GazerHostApiProvider
    extends $FunctionalProvider<GazerHostApi, GazerHostApi, GazerHostApi>
    with $Provider<GazerHostApi> {
  /// The [GazerHostApi] the app talks to; overridden in tests with
  /// `FakeGazerHostApi` so no real Pigeon channel is ever touched.
  GazerHostApiProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'gazerHostApiProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$gazerHostApiHash();

  @$internal
  @override
  $ProviderElement<GazerHostApi> $createElement($ProviderPointer pointer) =>
      $ProviderElement(pointer);

  @override
  GazerHostApi create(Ref ref) {
    return gazerHostApi(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(GazerHostApi value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<GazerHostApi>(value),
    );
  }
}

String _$gazerHostApiHash() => r'5979de3860a9464220eb38b8bbd81cb50840fbfa';

/// Enumerable video sources (M1: back/front camera only).

@ProviderFor(videoDevices)
final videoDevicesProvider = VideoDevicesProvider._();

/// Enumerable video sources (M1: back/front camera only).

final class VideoDevicesProvider
    extends
        $FunctionalProvider<
          AsyncValue<List<VideoDevice>>,
          List<VideoDevice>,
          FutureOr<List<VideoDevice>>
        >
    with
        $FutureModifier<List<VideoDevice>>,
        $FutureProvider<List<VideoDevice>> {
  /// Enumerable video sources (M1: back/front camera only).
  VideoDevicesProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'videoDevicesProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$videoDevicesHash();

  @$internal
  @override
  $FutureProviderElement<List<VideoDevice>> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<List<VideoDevice>> create(Ref ref) {
    return videoDevices(ref);
  }
}

String _$videoDevicesHash() => r'dad06377622782436f20a2bf72d82ba4193779d4';

/// Enumerable audio sources (M1: mic + silence only).

@ProviderFor(audioDevices)
final audioDevicesProvider = AudioDevicesProvider._();

/// Enumerable audio sources (M1: mic + silence only).

final class AudioDevicesProvider
    extends
        $FunctionalProvider<
          AsyncValue<List<AudioDevice>>,
          List<AudioDevice>,
          FutureOr<List<AudioDevice>>
        >
    with
        $FutureModifier<List<AudioDevice>>,
        $FutureProvider<List<AudioDevice>> {
  /// Enumerable audio sources (M1: mic + silence only).
  AudioDevicesProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'audioDevicesProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$audioDevicesHash();

  @$internal
  @override
  $FutureProviderElement<List<AudioDevice>> $createElement(
    $ProviderPointer pointer,
  ) => $FutureProviderElement(pointer);

  @override
  FutureOr<List<AudioDevice>> create(Ref ref) {
    return audioDevices(ref);
  }
}

String _$audioDevicesHash() => r'b058a30d525010e96fffdce2b7a1b31ff9c4ebf6';
