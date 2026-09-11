import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/services/keepalive_scheduler.dart';

/// [Timer]-compatible fake that never runs on a real clock: the test
/// calls [tick] to invoke the scheduled callback manually.
class _ManualTimer implements Timer {
  _ManualTimer(this._onCancel);

  final void Function() _onCancel;
  bool _active = true;

  @override
  void cancel() {
    _active = false;
    _onCancel();
  }

  @override
  bool get isActive => _active;

  @override
  int get tick => 0;
}

/// Fake `Timer.periodic`-shaped factory: records the scheduled callback
/// instead of starting a real timer, and lets the test fire it via [tick].
class _ManualPeriodic {
  void Function(Timer)? _callback;
  _ManualTimer? _lastTimer;
  int cancelCount = 0;

  Timer call(Duration duration, void Function(Timer) callback) {
    _callback = callback;
    _lastTimer = _ManualTimer(() => cancelCount++);
    return _lastTimer!;
  }

  /// Manually fires the scheduled callback, as if [duration] had elapsed.
  void tick() {
    final cb = _callback;
    final timer = _lastTimer;
    if (cb != null && timer != null) cb(timer);
  }
}

void main() {
  late _ManualPeriodic periodic;
  late int pingCalls;
  late bool shouldFail;

  Future<void> ping() async {
    pingCalls++;
    if (shouldFail) throw StateError('ping failed');
  }

  setUp(() {
    periodic = _ManualPeriodic();
    pingCalls = 0;
    shouldFail = false;
  });

  KeepaliveScheduler buildScheduler() => KeepaliveScheduler(
    ping: ping,
    interval: const Duration(minutes: 5),
    periodic: periodic.call,
  );

  test('does not ping before start', () {
    buildScheduler();
    periodic.tick();
    expect(pingCalls, 0);
  });

  test('start begins ticking; stop cancels the timer', () {
    final scheduler = buildScheduler();
    scheduler.start();
    expect(scheduler.isRunning, isTrue);

    periodic.tick();
    expect(pingCalls, 1);

    scheduler.stop();
    expect(scheduler.isRunning, isFalse);
    expect(periodic.cancelCount, 1);
  });

  test('start is idempotent — a second call does not create a new timer', () {
    final scheduler = buildScheduler();
    scheduler.start();
    scheduler.start();
    periodic.tick();
    expect(pingCalls, 1);
  });

  test('stop is idempotent — a second call is a no-op', () {
    final scheduler = buildScheduler();
    scheduler.start();
    scheduler.stop();
    scheduler.stop();
    expect(periodic.cancelCount, 1);
  });

  test('onLifecycle starts on resumed and stops on paused/inactive/detached/hidden', () {
    final scheduler = buildScheduler();

    for (final state in <AppLifecycleState>[
      AppLifecycleState.paused,
      AppLifecycleState.inactive,
      AppLifecycleState.detached,
      AppLifecycleState.hidden,
    ]) {
      scheduler.onLifecycle(AppLifecycleState.resumed);
      expect(scheduler.isRunning, isTrue);
      scheduler.onLifecycle(state);
      expect(
        scheduler.isRunning,
        isFalse,
        reason: '$state must stop the scheduler',
      );
    }
  });

  test(
    'ping failures are swallowed and counted; the scheduler keeps running',
    () async {
      final scheduler = buildScheduler();
      shouldFail = true;
      scheduler.start();

      periodic.tick();
      await Future<void>.delayed(Duration.zero);

      expect(scheduler.failures, 1);
      expect(scheduler.isRunning, isTrue);
    },
  );

  test('an in-flight ping is never overlapped by the next tick', () async {
    var slowPingCalls = 0;
    final completer = Completer<void>();

    final scheduler = KeepaliveScheduler(
      ping: () async {
        slowPingCalls++;
        await completer.future;
      },
      interval: const Duration(minutes: 5),
      periodic: periodic.call,
    );
    scheduler.start();

    // First tick starts the slow ping and leaves it in flight.
    periodic.tick();
    await Future<void>.delayed(Duration.zero);
    expect(slowPingCalls, 1);

    // A second tick while the first ping is still pending must be dropped.
    periodic.tick();
    await Future<void>.delayed(Duration.zero);
    expect(slowPingCalls, 1);

    // Resolving the pending ping clears the in-flight guard.
    completer.complete();
    await Future<void>.delayed(Duration.zero);

    // A third tick, now that nothing is in flight, starts a new ping.
    periodic.tick();
    await Future<void>.delayed(Duration.zero);
    expect(slowPingCalls, 2);
  });
}
