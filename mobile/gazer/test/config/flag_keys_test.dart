import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/config/flag_keys.dart';

void main() {
  test('flag keys match the PostHog {product}.{feature-name} convention', () {
    expect(FlagKeys.cameraStream, 'waddlebot.gazer.camera-stream');
    expect(FlagKeys.uvcCapture, 'waddlebot.gazer.uvc-capture');
    expect(FlagKeys.adaptiveBitrate, 'waddlebot.gazer.adaptive-bitrate');
    expect(FlagKeys.rtmpAuth, 'waddlebot.gazer.rtmp-auth');
  });

  test('all lists every flag key exactly once', () {
    expect(FlagKeys.all.length, 4);
    expect(FlagKeys.all.toSet().length, 4);
  });
}
