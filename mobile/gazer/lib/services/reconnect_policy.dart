import 'dart:math';

import 'package:gazer/models/pipeline_state.dart';

/// Reconnection policy for the streaming pipeline: which errors to retry,
/// how long to wait between attempts, and when to give up.
///
/// Retryable errors (temporary, infrastructure-level) trigger exponential
/// backoff with configurable base, cap, and jitter; non-retryable errors
/// (permanent, user-level) are terminal. [shouldRetry] implements the
/// decision table; [delayFor] computes backoff durations (null when exhausted).
class ReconnectPolicy {
  /// Maximum number of reconnection attempts before giving up.
  /// Attempts beyond this return null from [delayFor].
  final int maxAttempts;

  /// Exponential backoff base (default 1 second): delay = base * 2^(attempt-1).
  final Duration base;

  /// Maximum delay cap (default 30 seconds); delays never exceed this value.
  final Duration cap;

  /// Jitter fraction as a decimal (default 0.2 = ±20%): applied as
  /// ±jitter after capping to randomize retry timing and prevent
  /// thundering herd.
  final double jitter;

  /// Injected Random for deterministic testing; if null, uses platform Random.
  final Random? _random;

  /// Constructs a reconnect policy with configurable backoff parameters.
  ///
  /// All parameters are optional:
  /// - [maxAttempts]: max retry count (default 10)
  /// - [base]: exponential backoff base duration (default 1 second)
  /// - [cap]: maximum delay allowed (default 30 seconds)
  /// - [jitter]: jitter fraction ±0.0–1.0 (default 0.2 = ±20%)
  /// - [random]: injected Random for deterministic tests (default null = platform Random)
  ReconnectPolicy({
    this.maxAttempts = 10,
    this.base = const Duration(seconds: 1),
    this.cap = const Duration(seconds: 30),
    this.jitter = 0.2,
    Random? random,
  }) : _random = random; // ignore: prefer_initializing_formals

  /// Determines whether a given error code should trigger automatic reconnection.
  ///
  /// Returns true only for transient, infrastructure-level errors:
  /// - RTMP connection failures
  /// - RTMP disconnection
  ///
  /// Returns false for permanent, user-level errors that require manual action.
  bool shouldRetry(GazerErrorCode code) {
    return switch (code) {
      // Retryable: transient RTMP/network errors
      GazerErrorCode.rtmpConnectFailed => true,
      GazerErrorCode.rtmpDisconnected => true,

      // Non-retryable: permanent device/permission/auth errors
      GazerErrorCode.usbPermissionDenied => false,
      GazerErrorCode.uvcNoUsableFormat => false,
      GazerErrorCode.uvcOpenFailed => false,
      GazerErrorCode.cameraUnavailable => false,
      GazerErrorCode.cameraInUse => false,
      GazerErrorCode.encoderFailed => false,
      GazerErrorCode.audioSourceFailed => false,
      GazerErrorCode.rtmpAuthFailed => false,
      GazerErrorCode.usbDetached => false,
      GazerErrorCode.serviceStartDenied => false,
      GazerErrorCode.unknown => false,
    };
  }

  /// Computes the delay before the N-th reconnection attempt.
  ///
  /// Implements exponential backoff: [base] * 2^(attempt-1), capped at [cap],
  /// with ±[jitter] fraction applied to randomize retry timing.
  ///
  /// Parameters:
  /// - [attempt]: 1-based attempt number
  ///
  /// Returns a Duration, or null if attempt exceeds [maxAttempts].
  /// Jitter is applied as ±fraction of the final (capped) delay.
  Duration? delayFor(int attempt) {
    if (attempt > maxAttempts) {
      return null;
    }

    // Exponential backoff: base * 2^(attempt-1)
    final exponential =
        base.inMilliseconds * (1 << (attempt - 1)); // 2^(attempt-1)

    // Cap at maximum delay
    final capped = exponential > cap.inMilliseconds
        ? cap.inMilliseconds
        : exponential;

    // Apply ±jitter (fraction) to the capped value
    final rng = _random ?? Random();
    final jitterRange = capped * jitter;
    final jitterValue =
        jitterRange * (2 * rng.nextDouble() - 1); // -jitterRange..+jitterRange
    final finalMs = (capped + jitterValue).toInt();

    return Duration(milliseconds: finalMs);
  }
}
