import 'dart:async';

import 'package:flutter/widgets.dart';

/// Periodically pings the license server while the app is foregrounded.
///
/// Owns exactly one [Timer]: [start] is idempotent (a second call while
/// already running is a no-op), [stop] cancels it, and [onLifecycle]
/// wires both to `WidgetsBindingObserver.didChangeAppLifecycleState` —
/// [AppLifecycleState.resumed] starts it, every backgrounded state stops
/// it. [ping] failures are swallowed (never crash the app) and counted
/// in [failures] for diagnostics.
class KeepaliveScheduler {
  KeepaliveScheduler({
    required Future<void> Function() ping,
    required Duration interval,
    Timer Function(Duration, void Function(Timer)) periodic = Timer.periodic,
  }) : _ping = ping, // ignore: prefer_initializing_formals
       _interval = interval, // ignore: prefer_initializing_formals
       _periodic = periodic; // ignore: prefer_initializing_formals

  final Future<void> Function() _ping;
  final Duration _interval;
  final Timer Function(Duration, void Function(Timer)) _periodic;

  Timer? _timer;

  /// Number of [ping] calls that threw since this scheduler was created.
  int failures = 0;

  /// Whether the periodic timer is currently active.
  bool get isRunning => _timer != null;

  /// Starts the periodic ping if not already running.
  void start() {
    if (_timer != null) return;
    _timer = _periodic(_interval, (_) => _tick());
  }

  /// Cancels the periodic ping if running; safe to call when already
  /// stopped.
  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  /// Starts on [AppLifecycleState.resumed]; stops on every backgrounded
  /// state (paused/inactive/detached/hidden).
  void onLifecycle(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        start();
      case AppLifecycleState.paused:
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
      case AppLifecycleState.hidden:
        stop();
    }
  }

  Future<void> _tick() async {
    try {
      await _ping();
    } catch (_) {
      failures++;
    }
  }
}
