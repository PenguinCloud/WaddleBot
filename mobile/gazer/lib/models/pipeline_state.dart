// GazerErrorCode is Pigeon-generated (see pigeons/pipeline.dart) and is the
// single canonical source of truth for these 13 members (ruling R21: one
// enum, not a hand-written duplicate). It is imported here for local use in
// [GazerError] below, and re-exported so callers that already import this
// file for GazerErrorCode (predating the Pigeon contract) keep resolving it
// without changing their imports.
import 'package:gazer/pigeon/pipeline.g.dart';
export 'package:gazer/pigeon/pipeline.g.dart' show GazerErrorCode;

/// An error surfaced by the native pipeline, carried inside [ErrorState].
///
/// Immutable value type: two [GazerError]s with the same [code] and
/// [detail] compare equal so tests and UI can diff error states cheaply.
class GazerError {
  const GazerError({required this.code, this.detail});

  /// Machine-readable error classification from the native pipeline.
  final GazerErrorCode code;

  /// Optional human-readable detail forwarded from the native layer
  /// (never contains secrets; native never includes URLs/credentials).
  final String? detail;

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      (other is GazerError && other.code == code && other.detail == detail);

  @override
  int get hashCode => Object.hash(code, detail);

  @override
  String toString() => 'GazerError(code: $code, detail: $detail)';
}

/// Current state of the Gazer streaming pipeline.
///
/// Mirrors the native `NativePipelineState` machine but adds the
/// Dart-owned [ReconnectingState], which the native layer never emits —
/// `PipelineController` synthesizes it while a reconnect backoff is
/// in flight.
sealed class PipelineState {
  const PipelineState();
}

/// No source prepared, not streaming; the resting state.
class IdleState extends PipelineState {
  const IdleState();

  @override
  bool operator ==(Object other) => other is IdleState;

  @override
  int get hashCode => (IdleState).hashCode;

  @override
  String toString() => 'IdleState()';
}

/// Native pipeline is negotiating the video/audio source.
class PreparingState extends PipelineState {
  const PreparingState();

  @override
  bool operator ==(Object other) => other is PreparingState;

  @override
  int get hashCode => (PreparingState).hashCode;

  @override
  String toString() => 'PreparingState()';
}

/// Source prepared successfully; not yet connecting to the RTMP endpoint.
class ReadyState extends PipelineState {
  const ReadyState();

  @override
  bool operator ==(Object other) => other is ReadyState;

  @override
  int get hashCode => (ReadyState).hashCode;

  @override
  String toString() => 'ReadyState()';
}

/// TCP/RTMP handshake with the endpoint is in progress.
class ConnectingState extends PipelineState {
  const ConnectingState();

  @override
  bool operator ==(Object other) => other is ConnectingState;

  @override
  int get hashCode => (ConnectingState).hashCode;

  @override
  String toString() => 'ConnectingState()';
}

/// Actively encoding and publishing to the RTMP endpoint.
class StreamingState extends PipelineState {
  const StreamingState();

  @override
  bool operator ==(Object other) => other is StreamingState;

  @override
  int get hashCode => (StreamingState).hashCode;

  @override
  String toString() => 'StreamingState()';
}

/// Dart-owned backoff state: the connection dropped and
/// `PipelineController` will retry after [nextIn].
class ReconnectingState extends PipelineState {
  const ReconnectingState(this.attempt, this.nextIn);

  /// 1-based attempt number, matching `ReconnectPolicy.delayFor`.
  final int attempt;

  /// Time remaining before the next `start()` retry is issued.
  final Duration nextIn;

  @override
  bool operator ==(Object other) =>
      other is ReconnectingState &&
      other.attempt == attempt &&
      other.nextIn == nextIn;

  @override
  int get hashCode => Object.hash(attempt, nextIn);

  @override
  String toString() => 'ReconnectingState(attempt: $attempt, nextIn: $nextIn)';
}

/// User (or the controller) requested stop; native teardown in progress.
class StoppingState extends PipelineState {
  const StoppingState();

  @override
  bool operator ==(Object other) => other is StoppingState;

  @override
  int get hashCode => (StoppingState).hashCode;

  @override
  String toString() => 'StoppingState()';
}

/// Terminal (until the user retries manually) error state.
class ErrorState extends PipelineState {
  const ErrorState(this.error);

  /// The error that caused the pipeline to stop retrying automatically.
  final GazerError error;

  @override
  bool operator ==(Object other) => other is ErrorState && other.error == error;

  @override
  int get hashCode => error.hashCode;

  @override
  String toString() => 'ErrorState(error: $error)';
}
