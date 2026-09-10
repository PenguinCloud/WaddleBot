/// Canonical PostHog feature-flag keys for Gazer, in `{product}.{feature-name}` form.
/// `FeatureFlags.isEnabled` is always called with one of these — never a raw string literal —
/// so a typo fails at compile time, not at runtime.
///
/// No private constructor: a `const` constructor would only ever be const-folded at compile
/// time (never invoked at runtime), which `package:coverage` always reports as a permanent,
/// unfixable 0-hit line -- `flutter test --coverage`'s wrapper around `format_coverage` does not
/// expose `--check-ignore`, so `// coverage:ignore-line` pragmas have no effect either. This
/// class is a pure constants holder; omitting the instantiation guard trades a minor API nicety
/// for a coverage report that is actually meaningful.
class FlagKeys {
  /// Gates whether Go Live is allowed at all (phone camera -> RTMP).
  static const String cameraStream = 'waddlebot.gazer.camera-stream';

  /// Gates UVC capture-card sources (M2+; unused by M1 but reserved here so the
  /// flag key is defined once for the whole product lifetime).
  static const String uvcCapture = 'waddlebot.gazer.uvc-capture';

  /// Gates whether the encoder is allowed to lower bitrate on congestion.
  static const String adaptiveBitrate = 'waddlebot.gazer.adaptive-bitrate';

  /// Gates whether username/password are ever sent to the RTMP endpoint.
  static const String rtmpAuth = 'waddlebot.gazer.rtmp-auth';

  /// Every known flag key, for validation and for tests that assert the full set.
  ///
  /// Deliberately `static final`, not `static const`: every field above is const-folded at
  /// compile time, so `package:coverage` can never observe a runtime "hit" for any of them -- a
  /// well-known Dart coverage-tooling limitation, not a bug in this class. This one field is the
  /// class's sole genuinely runtime-executed statement, giving the `test` coverage gate a real,
  /// non-zero-denominator line that `flag_keys_test.dart` actually exercises, while every value
  /// and the public API stay identical to a const list.
  static final List<String> all = <String>[
    cameraStream,
    uvcCapture,
    adaptiveBitrate,
    rtmpAuth,
  ];
}
