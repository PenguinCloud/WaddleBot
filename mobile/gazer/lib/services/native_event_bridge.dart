import 'dart:async';

import '../pigeon/pipeline.g.dart';

/// Concrete [GazerFlutterApi] implementation: turns Pigeon-delivered
/// Kotlin -> Dart calls into broadcast streams the rest of the app
/// listens to.
///
/// Pigeon's codegen calls these override methods directly when a message
/// arrives on the platform channel; nothing else in the app calls them
/// except tests, which push events straight through to simulate native
/// callbacks.
class NativeEventBridge implements GazerFlutterApi {
  final StreamController<StateEvent> _stateController =
      StreamController<StateEvent>.broadcast();
  final StreamController<StatsSample> _statsController =
      StreamController<StatsSample>.broadcast();
  final StreamController<VideoDevice> _usbAttachedController =
      StreamController<VideoDevice>.broadcast();
  final StreamController<String> _usbDetachedController =
      StreamController<String>.broadcast();
  final StreamController<bool> _authResultController =
      StreamController<bool>.broadcast();

  /// Every native pipeline state transition.
  Stream<StateEvent> get stateEvents => _stateController.stream;

  /// Every 1Hz native statistics sample.
  Stream<StatsSample> get stats => _statsController.stream;

  /// Every UVC device attach event (M1: never fired).
  Stream<VideoDevice> get usbAttached => _usbAttachedController.stream;

  /// Every UVC device detach event (M1: never fired), by device id.
  Stream<String> get usbDetached => _usbDetachedController.stream;

  /// Every RTMP auth attempt result.
  Stream<bool> get authResults => _authResultController.stream;

  @override
  void onStateChanged(StateEvent event) => _stateController.add(event);

  @override
  void onStats(StatsSample sample) => _statsController.add(sample);

  @override
  void onUsbAttached(VideoDevice device) => _usbAttachedController.add(device);

  @override
  void onUsbDetached(String deviceId) => _usbDetachedController.add(deviceId);

  @override
  void onAuthResult(bool ok) => _authResultController.add(ok);

  /// Closes every underlying stream; call once, when the owner (typically
  /// `pipelineControllerProvider`) is disposed.
  void dispose() {
    _stateController.close();
    _statsController.close();
    _usbAttachedController.close();
    _usbDetachedController.close();
    _authResultController.close();
  }
}
