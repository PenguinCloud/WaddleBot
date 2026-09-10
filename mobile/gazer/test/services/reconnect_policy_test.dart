import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/pipeline_state.dart';
import 'package:gazer/services/reconnect_policy.dart';

void main() {
  group('ReconnectPolicy.shouldRetry', () {
    test('returns true for retryable errors (RTMP only)', () {
      final policy = ReconnectPolicy();
      expect(policy.shouldRetry(GazerErrorCode.rtmpConnectFailed), isTrue);
      expect(policy.shouldRetry(GazerErrorCode.rtmpDisconnected), isTrue);
    });

    test('returns false for non-retryable errors', () {
      final policy = ReconnectPolicy();
      expect(policy.shouldRetry(GazerErrorCode.usbPermissionDenied), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.uvcNoUsableFormat), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.uvcOpenFailed), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.cameraUnavailable), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.cameraInUse), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.encoderFailed), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.audioSourceFailed), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.rtmpAuthFailed), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.usbDetached), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.serviceStartDenied), isFalse);
      expect(policy.shouldRetry(GazerErrorCode.unknown), isFalse);
    });

    test('decision table covers all 13 error codes', () {
      final policy = ReconnectPolicy();
      for (final code in GazerErrorCode.values) {
        policy.shouldRetry(code); // Verify no crash
      }
    });
  });

  group('ReconnectPolicy.delayFor', () {
    test('uses injected Random for deterministic delays', () {
      final policy1 = ReconnectPolicy(random: Random(42));
      final policy2 = ReconnectPolicy(random: Random(42));

      final delay1 = policy1.delayFor(1);
      final delay2 = policy2.delayFor(1);

      expect(delay1, delay2);
    });

    test('exponential backoff sequence: 1,2,4,8,16,30,30,30,30,30 seconds', () {
      // With nextDouble() == 0.5, jitter is exactly zero
      final rng = _FakeRandom(0.5); // Zero jitter
      final policy = ReconnectPolicy(random: rng);

      final expected = [
        1, // 1 * 2^0 = 1
        2, // 1 * 2^1 = 2
        4, // 1 * 2^2 = 4
        8, // 1 * 2^3 = 8
        16, // 1 * 2^4 = 16
        30, // capped at 30
        30, // capped at 30
        30, // capped at 30
        30, // capped at 30
        30, // capped at 30
      ];

      for (int attempt = 1; attempt <= 10; attempt++) {
        final delay = policy.delayFor(attempt);
        expect(delay!.inSeconds, expected[attempt - 1]);
      }
    });

    test('delayFor(11) returns null (exhaustion)', () {
      final policy = ReconnectPolicy(maxAttempts: 10);
      expect(policy.delayFor(11), isNull);
      expect(policy.delayFor(100), isNull);
    });

    test('delayFor(0) returns null (attempts are 1-based)', () {
      final policy = ReconnectPolicy();
      expect(policy.delayFor(0), isNull);
      expect(policy.delayFor(-1), isNull);
      expect(policy.delayFor(-100), isNull);
    });

    test('jitter bounds: ±20% applied to capped delay', () {
      // nextDouble() == 0.0 => jitter = -20%, lowest value
      final policyMin = ReconnectPolicy(random: _FakeRandom(0.0));
      final delayMin = policyMin.delayFor(1); // 1 sec cap not hit; 1*2^0=1
      expect(
        delayMin!.inMilliseconds,
        closeTo(800, 1), // 1000ms * (1 - 0.2) = 800ms
      );

      // nextDouble() == 1.0 => jitter = +20%, highest value
      final policyMax = ReconnectPolicy(random: _FakeRandom(1.0));
      final delayMax = policyMax.delayFor(1);
      expect(
        delayMax!.inMilliseconds,
        closeTo(1200, 1), // 1000ms * (1 + 0.2) = 1200ms
      );

      // nextDouble() == 0.5 => jitter = 0%, middle
      final policyMid = ReconnectPolicy(random: _FakeRandom(0.5));
      final delayMid = policyMid.delayFor(1);
      expect(delayMid!.inMilliseconds, closeTo(1000, 1)); // No jitter
    });

    test('jitter at cap boundary: ±20% of 30 seconds', () {
      // Attempt 6 would be 32 seconds, capped at 30
      // nextDouble() == 0.0 => minimum: 30 * (1 - 0.2) = 24 seconds
      final policyMin = ReconnectPolicy(random: _FakeRandom(0.0));
      final delayMin = policyMin.delayFor(6);
      expect(delayMin!.inSeconds, 24);

      // nextDouble() == 1.0 => maximum: 30 * (1 + 0.2) = 36 seconds
      final policyMax = ReconnectPolicy(random: _FakeRandom(1.0));
      final delayMax = policyMax.delayFor(6);
      expect(delayMax!.inSeconds, 36);

      // nextDouble() == 0.5 => no jitter: 30 seconds
      final policyMid = ReconnectPolicy(random: _FakeRandom(0.5));
      final delayMid = policyMid.delayFor(6);
      expect(delayMid!.inSeconds, 30);
    });

    test('custom parameters override defaults', () {
      final policy = ReconnectPolicy(
        maxAttempts: 5,
        base: const Duration(milliseconds: 500),
        cap: const Duration(seconds: 10),
        jitter: 0.1,
      );

      // Attempt 1: 500ms * 2^0 = 500ms, no cap needed
      final delay1 = policy.delayFor(1);
      expect(delay1, isNotNull);
      expect(delay1!.inMilliseconds, lessThanOrEqualTo(550)); // With jitter

      // Attempt 6 (> maxAttempts) returns null
      expect(policy.delayFor(6), isNull);
    });

    test('returns positive Duration within bounds', () {
      final policy = ReconnectPolicy();
      for (int attempt = 1; attempt <= 10; attempt++) {
        final delay = policy.delayFor(attempt);
        expect(delay, isNotNull);
        expect(delay!.inMilliseconds, greaterThan(0));
        expect(
          delay.inMilliseconds,
          lessThanOrEqualTo(
            (30 * 1000 * 1.2).toInt(), // cap + max jitter
          ),
        );
      }
    });
  });

  group('ReconnectPolicy integration', () {
    test('shouldRetry + delayFor for complete retry flow', () {
      final policy = ReconnectPolicy();
      const code = GazerErrorCode.rtmpDisconnected;

      if (policy.shouldRetry(code)) {
        for (int attempt = 1; attempt <= 3; attempt++) {
          final delay = policy.delayFor(attempt);
          expect(delay, isNotNull);
        }
      }
    });

    test('non-retryable error never retries', () {
      final policy = ReconnectPolicy();
      const code = GazerErrorCode.usbPermissionDenied;

      expect(policy.shouldRetry(code), isFalse);
      // delayFor still computes (up to maxAttempts) but caller ignores it
      expect(policy.delayFor(1), isNotNull);
    });
  });
}

/// Fake Random that always returns a fixed value.
class _FakeRandom implements Random {
  final double _fixedValue;

  _FakeRandom(this._fixedValue);

  @override
  double nextDouble() => _fixedValue;

  @override
  int nextInt(int max) => (_fixedValue * max).toInt();

  @override
  bool nextBool() => _fixedValue > 0.5;
}
