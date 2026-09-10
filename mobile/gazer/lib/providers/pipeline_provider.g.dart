// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'pipeline_provider.dart';

// **************************************************************************
// RiverpodGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint, type=warning
/// Owns the [PipelineController] for the app's lifetime; overridden in
/// provider/widget tests with a controller wired to `FakeGazerHostApi`.
///
/// The real controller is built on [gazerHostApiProvider]'s [GazerHostApi]
/// (the Pigeon default messenger) and a fresh [NativeEventBridge]. The
/// bridge is registered with [GazerFlutterApi.setUp] so Kotlin -> Dart
/// pushes on the real platform channel actually reach it — constructing a
/// `NativeEventBridge` alone does not wire it to anything. Both the
/// `setUp` registration and the bridge's own streams are torn down
/// alongside the controller on [Ref.onDispose].

@ProviderFor(pipelineController)
final pipelineControllerProvider = PipelineControllerProvider._();

/// Owns the [PipelineController] for the app's lifetime; overridden in
/// provider/widget tests with a controller wired to `FakeGazerHostApi`.
///
/// The real controller is built on [gazerHostApiProvider]'s [GazerHostApi]
/// (the Pigeon default messenger) and a fresh [NativeEventBridge]. The
/// bridge is registered with [GazerFlutterApi.setUp] so Kotlin -> Dart
/// pushes on the real platform channel actually reach it — constructing a
/// `NativeEventBridge` alone does not wire it to anything. Both the
/// `setUp` registration and the bridge's own streams are torn down
/// alongside the controller on [Ref.onDispose].

final class PipelineControllerProvider
    extends
        $FunctionalProvider<
          PipelineController,
          PipelineController,
          PipelineController
        >
    with $Provider<PipelineController> {
  /// Owns the [PipelineController] for the app's lifetime; overridden in
  /// provider/widget tests with a controller wired to `FakeGazerHostApi`.
  ///
  /// The real controller is built on [gazerHostApiProvider]'s [GazerHostApi]
  /// (the Pigeon default messenger) and a fresh [NativeEventBridge]. The
  /// bridge is registered with [GazerFlutterApi.setUp] so Kotlin -> Dart
  /// pushes on the real platform channel actually reach it — constructing a
  /// `NativeEventBridge` alone does not wire it to anything. Both the
  /// `setUp` registration and the bridge's own streams are torn down
  /// alongside the controller on [Ref.onDispose].
  PipelineControllerProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'pipelineControllerProvider',
        isAutoDispose: false,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$pipelineControllerHash();

  @$internal
  @override
  $ProviderElement<PipelineController> $createElement(
    $ProviderPointer pointer,
  ) => $ProviderElement(pointer);

  @override
  PipelineController create(Ref ref) {
    return pipelineController(ref);
  }

  /// {@macro riverpod.override_with_value}
  Override overrideWithValue(PipelineController value) {
    return $ProviderOverride(
      origin: this,
      providerOverride: $SyncValueProvider<PipelineController>(value),
    );
  }
}

String _$pipelineControllerHash() =>
    r'25191eb497fca424269e3ca28f9e7f050aa8736a';

/// Live [PipelineState] stream, seeded with the controller's current
/// value so a new subscriber never waits for the next native event to
/// render — `PipelineController.state` alone does not replay past events.

@ProviderFor(pipelineState)
final pipelineStateProvider = PipelineStateProvider._();

/// Live [PipelineState] stream, seeded with the controller's current
/// value so a new subscriber never waits for the next native event to
/// render — `PipelineController.state` alone does not replay past events.

final class PipelineStateProvider
    extends
        $FunctionalProvider<
          AsyncValue<PipelineState>,
          PipelineState,
          Stream<PipelineState>
        >
    with $FutureModifier<PipelineState>, $StreamProvider<PipelineState> {
  /// Live [PipelineState] stream, seeded with the controller's current
  /// value so a new subscriber never waits for the next native event to
  /// render — `PipelineController.state` alone does not replay past events.
  PipelineStateProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'pipelineStateProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$pipelineStateHash();

  @$internal
  @override
  $StreamProviderElement<PipelineState> $createElement(
    $ProviderPointer pointer,
  ) => $StreamProviderElement(pointer);

  @override
  Stream<PipelineState> create(Ref ref) {
    return pipelineState(ref);
  }
}

String _$pipelineStateHash() => r'e420aee5b13ae8a59d5783d929ccd508a4522ce6';

/// Live [StreamStats] stream, seeded with the zero snapshot the same way
/// [pipelineState] is seeded with the controller's current state.

@ProviderFor(streamStats)
final streamStatsProvider = StreamStatsProvider._();

/// Live [StreamStats] stream, seeded with the zero snapshot the same way
/// [pipelineState] is seeded with the controller's current state.

final class StreamStatsProvider
    extends
        $FunctionalProvider<
          AsyncValue<StreamStats>,
          StreamStats,
          Stream<StreamStats>
        >
    with $FutureModifier<StreamStats>, $StreamProvider<StreamStats> {
  /// Live [StreamStats] stream, seeded with the zero snapshot the same way
  /// [pipelineState] is seeded with the controller's current state.
  StreamStatsProvider._()
    : super(
        from: null,
        argument: null,
        retry: null,
        name: r'streamStatsProvider',
        isAutoDispose: true,
        dependencies: null,
        $allTransitiveDependencies: null,
      );

  @override
  String debugGetCreateSourceHash() => _$streamStatsHash();

  @$internal
  @override
  $StreamProviderElement<StreamStats> $createElement(
    $ProviderPointer pointer,
  ) => $StreamProviderElement(pointer);

  @override
  Stream<StreamStats> create(Ref ref) {
    return streamStats(ref);
  }
}

String _$streamStatsHash() => r'25c93e8ee590c268dd6c67f235e25f66a3e70fa5';
