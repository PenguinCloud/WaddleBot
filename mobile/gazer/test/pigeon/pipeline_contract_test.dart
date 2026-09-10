import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/pigeon/pipeline.g.dart';

// Pigeon 28.0.0 generates each data class with a named-parameter constructor
// (required for non-nullable fields) rather than a no-arg constructor with
// `late` fields settable via cascade -- so these round-trip cases construct
// objects positionally-named rather than via `Type()..field = value`. The
// values and assertions below match the shared contract's intent exactly.
void main() {
  group(
    'Pigeon-generated data classes round-trip through encode()/decode()',
    () {
      test('VideoDevice', () {
        final original = VideoDevice(
          id: 'camera:back',
          kind: VideoDeviceKind.backCamera,
          name: 'Back Camera',
          vendorId: null,
          productId: null,
        );
        final restored = VideoDevice.decode(original.encode());
        expect(restored.id, original.id);
        expect(restored.kind, original.kind);
        expect(restored.name, original.name);
        expect(restored.vendorId, original.vendorId);
        expect(restored.productId, original.productId);
      });

      test('AudioDevice', () {
        final original = AudioDevice(
          id: 'audio:mic',
          kind: AudioDeviceKind.mic,
          name: 'Phone Microphone',
        );
        final restored = AudioDevice.decode(original.encode());
        expect(restored.id, original.id);
        expect(restored.kind, original.kind);
        expect(restored.name, original.name);
      });

      test('StreamConfig', () {
        final original = StreamConfig(
          videoDeviceId: 'camera:back',
          audioDeviceId: 'audio:mic',
          width: 960,
          height: 540,
          fps: 30,
          videoBitrateKbps: 2000,
          adaptiveBitrate: true,
          audioBitrateKbps: 128,
          orientation: OutputOrientation.landscape,
        );
        final restored = StreamConfig.decode(original.encode());
        expect(restored.videoDeviceId, original.videoDeviceId);
        expect(restored.audioDeviceId, original.audioDeviceId);
        expect(restored.width, original.width);
        expect(restored.height, original.height);
        expect(restored.fps, original.fps);
        expect(restored.videoBitrateKbps, original.videoBitrateKbps);
        expect(restored.adaptiveBitrate, original.adaptiveBitrate);
        expect(restored.audioBitrateKbps, original.audioBitrateKbps);
        expect(restored.orientation, original.orientation);
      });

      test('StreamTarget', () {
        final original = StreamTarget(
          url: 'rtmp://ingest-a.example.com/live/demo-key-0001',
          username: 'demo',
          password: 'secret',
        );
        final restored = StreamTarget.decode(original.encode());
        expect(restored.url, original.url);
        expect(restored.username, original.username);
        expect(restored.password, original.password);
      });

      test('PrepareResult', () {
        final original = PrepareResult(
          ok: false,
          error: GazerErrorCode.cameraUnavailable,
          detail: 'no back camera',
          negotiatedWidth: null,
          negotiatedHeight: null,
          negotiatedFps: null,
          negotiatedFormat: null,
        );
        final restored = PrepareResult.decode(original.encode());
        expect(restored.ok, original.ok);
        expect(restored.error, original.error);
        expect(restored.detail, original.detail);
      });

      test('StatsSample', () {
        final original = StatsSample(
          bitrateKbps: 2000,
          fps: 29.7,
          droppedVideoFrames: 3,
          sentBytes: 123456,
          congestionPercent: 12.5,
        );
        final restored = StatsSample.decode(original.encode());
        expect(restored.bitrateKbps, original.bitrateKbps);
        expect(restored.fps, original.fps);
        expect(restored.droppedVideoFrames, original.droppedVideoFrames);
        expect(restored.sentBytes, original.sentBytes);
        expect(restored.congestionPercent, original.congestionPercent);
      });

      test('StateEvent', () {
        final original = StateEvent(
          state: NativePipelineState.error,
          error: GazerErrorCode.rtmpAuthFailed,
          detail: '401 unauthorized',
        );
        final restored = StateEvent.decode(original.encode());
        expect(restored.state, original.state);
        expect(restored.error, original.error);
        expect(restored.detail, original.detail);
      });
    },
  );
}
