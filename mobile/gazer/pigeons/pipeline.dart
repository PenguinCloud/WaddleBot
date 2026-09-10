@ConfigurePigeon(
  PigeonOptions(
    dartOut: 'lib/pigeon/pipeline.g.dart',
    // Pigeon 28.0.0 deprecated dartTestOut in favor of mocking the generated API
    // directly, but this test-mock scaffold file (test/pigeon/pipeline_test.g.dart)
    // is still generated correctly and is an explicit, committed deliverable of
    // this contract -- see the Task 6 brief.
    // ignore: deprecated_member_use
    dartTestOut: 'test/pigeon/pipeline_test.g.dart',
    dartPackageName: 'gazer',
    kotlinOut:
        'android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/Pipeline.g.kt',
    kotlinOptions: KotlinOptions(package: 'io.waddlebot.gazer.pigeon'),
  ),
)
library;

import 'package:pigeon/pigeon.dart';

/// Kind of video source a device entry represents.
enum VideoDeviceKind { backCamera, frontCamera, uvcCamera2, uvcLibuvc }

/// Kind of audio source a device entry represents.
enum AudioDeviceKind { mic, usbAudio, silence }

/// Native pipeline state machine, as reported by the Kotlin side. Dart adds
/// the `reconnecting` state on top of this (see the Dart `PipelineState`).
enum NativePipelineState {
  idle,
  preparing,
  ready,
  connecting,
  streaming,
  stopping,
  error,
}

/// Error classification for every failure the native pipeline can report.
enum GazerErrorCode {
  usbPermissionDenied,
  uvcNoUsableFormat,
  uvcOpenFailed,
  cameraUnavailable,
  cameraInUse,
  encoderFailed,
  audioSourceFailed,
  rtmpAuthFailed,
  rtmpConnectFailed,
  rtmpDisconnected,
  usbDetached,
  serviceStartDenied,
  unknown,
}

/// Requested output orientation for the encoded video (camera path only;
/// UVC is always landscape).
enum OutputOrientation { landscape, portrait }

/// One enumerable video source (a camera or an attached UVC device).
class VideoDevice {
  late String id;
  late VideoDeviceKind kind;
  late String name;
  int? vendorId;
  int? productId;
}

/// One enumerable audio source.
class AudioDevice {
  late String id;
  late AudioDeviceKind kind;
  late String name;
}

/// Parameters for `GazerHostApi.prepare` describing the encoder/source setup.
class StreamConfig {
  late String videoDeviceId;
  late String audioDeviceId;
  late int width;
  late int height;
  late int fps;
  late int videoBitrateKbps;
  late bool adaptiveBitrate;
  late int audioBitrateKbps;
  late OutputOrientation orientation;
}

/// RTMP/RTMPS destination passed to `GazerHostApi.start`. `url` already has
/// the stream key folded in by `TargetValidator.effectiveUrl` on the Dart
/// side — Kotlin never appends a key itself.
class StreamTarget {
  late String url;
  String? username;
  String? password;
}

/// Result of `GazerHostApi.prepare`: whether the source/encoder negotiated
/// successfully and, if so, what was actually negotiated.
class PrepareResult {
  late bool ok;
  GazerErrorCode? error;
  String? detail;
  int? negotiatedWidth;
  int? negotiatedHeight;
  int? negotiatedFps;
  String? negotiatedFormat;
}

/// One 1Hz statistics sample emitted by the native encoder/publisher.
class StatsSample {
  late int bitrateKbps;
  late double fps;
  late int droppedVideoFrames;
  late int sentBytes;
  late double congestionPercent;
}

/// A native pipeline state transition, optionally carrying an error.
class StateEvent {
  late NativePipelineState state;
  GazerErrorCode? error;
  String? detail;
}

/// Commands Dart issues to the native pipeline (Dart -> Kotlin).
@HostApi()
abstract class GazerHostApi {
  /// Enumerates available video sources (back/front camera; UVC devices
  /// attached at call time).
  List<VideoDevice> listVideoDevices();

  /// Enumerates available audio sources.
  List<AudioDevice> listAudioDevices();

  /// Requests OS-level USB permission for [deviceId]. M1 always returns
  /// false: no UVC devices are ever listed, so this is never actually
  /// invoked with a real device in this milestone.
  @async
  bool requestUsbPermission(String deviceId);

  /// Negotiates the source/encoder for [config]; must succeed before `start`.
  @async
  PrepareResult prepare(StreamConfig config);

  /// Begins publishing to [target]; only valid after a successful `prepare`.
  @async
  void start(StreamTarget target);

  /// Stops publishing and tears down the source/encoder.
  @async
  void stop();

  /// Adjusts the live video bitrate without a full restart (used by the
  /// native `BitrateAdapter` and by Dart-driven manual overrides).
  void setVideoBitrate(int kbps);

  /// Returns the native pipeline's current state synchronously.
  NativePipelineState getState();
}

/// Events the native pipeline pushes to Dart (Kotlin -> Dart).
@FlutterApi()
abstract class GazerFlutterApi {
  /// Fired on every native state transition.
  void onStateChanged(StateEvent event);

  /// Fired at 1Hz while prepared/streaming.
  void onStats(StatsSample sample);

  /// Fired when a UVC device is physically attached (M1: never fired).
  void onUsbAttached(VideoDevice device);

  /// Fired when a UVC device is physically detached (M1: never fired).
  void onUsbDetached(String deviceId);

  /// Fired after an RTMP auth attempt resolves.
  void onAuthResult(bool ok);
}
