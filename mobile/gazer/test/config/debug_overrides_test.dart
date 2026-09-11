import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/config/debug_overrides.dart';

/// Covers DebugOverrides across however this file was invoked:
/// `make mobile-test` runs it with no define (flagsOverride == ''), and
/// Step 4 below runs it a second time with
/// `--dart-define=GAZER_FLAGS_OVERRIDE=camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture`
/// to exercise the non-empty parsing path. kDebugMode is always true
/// under `flutter test`, so `enabled` can only be proven to require BOTH
/// conditions by pairing this file's assertions with the release-build
/// code-review guard documented in Step 6 — it cannot be proven by a
/// single `flutter test` invocation alone.
void main() {
  test('kDebugMode is true under flutter test (sanity: proves the harness limitation, not a DebugOverrides property)', () {
    expect(kDebugMode, isTrue);
  });

  test('enabled is exactly flagsOverride.isNotEmpty given kDebugMode is always true here', () {
    expect(
      DebugOverrides.enabled,
      equals(DebugOverrides.flagsOverride.isNotEmpty),
    );
  });

  test('flags parses the currently-configured define into a trimmed, non-empty-only set', () {
    final Set<String> expected = DebugOverrides.flagsOverride
        .split(',')
        .map((s) => s.trim())
        .where((s) => s.isNotEmpty)
        .toSet();
    expect(DebugOverrides.flags, equals(expected));
  });

  test(
    'default invocation (no define) yields empty flags and enabled == false',
    () {
      if (DebugOverrides.flagsOverride.isEmpty) {
        expect(DebugOverrides.flags, isEmpty);
        expect(DebugOverrides.enabled, isFalse);
      }
    },
  );

  test(
    'the M1 integration define decodes to exactly the 4 flag keys used by CI',
    () {
      const String integrationDefine =
          'camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture';
      if (DebugOverrides.flagsOverride == integrationDefine) {
        expect(
          DebugOverrides.flags,
          equals(<String>{
            'camera-stream',
            'adaptive-bitrate',
            'rtmp-auth',
            'uvc-capture',
          }),
        );
        expect(DebugOverrides.enabled, isTrue);
      }
    },
  );
}
