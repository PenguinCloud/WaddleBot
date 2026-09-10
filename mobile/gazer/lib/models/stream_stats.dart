import 'package:freezed_annotation/freezed_annotation.dart';

part 'stream_stats.freezed.dart';

/// Dart-side aggregation of native 1Hz `StatsSample`s: rolling averages and
/// session totals shown in the status panel.
///
/// `PipelineController` owns the aggregation math (rolling average bitrate,
/// uptime clock, cumulative reconnect count); this class is the immutable
/// snapshot handed to the UI via `streamStatsProvider`. Not persisted, so
/// no JSON codegen is needed.
@freezed
abstract class StreamStats with _$StreamStats {
  const factory StreamStats({
    required int currentBitrateKbps,
    required int averageBitrateKbps,
    required double fps,
    required int droppedFrames,
    required int sentBytes,
    required Duration uptime,
    required int reconnectCount,
    required double congestionPercent,
  }) = _StreamStats;

  /// The all-zero snapshot shown before streaming starts and after a full
  /// stop (session totals reset).
  factory StreamStats.zero() => const StreamStats(
    currentBitrateKbps: 0,
    averageBitrateKbps: 0,
    fps: 0,
    droppedFrames: 0,
    sentBytes: 0,
    uptime: Duration.zero,
    reconnectCount: 0,
    congestionPercent: 0,
  );
}
