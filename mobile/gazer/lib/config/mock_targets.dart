/// The 4 seeded stream-target presets and 2 quality presets used across
/// widget tests, the integration tests, `make mobile-screenshots` capture
/// runs, and [applySeedIfRequested]. Mirrors the spec's Mock Data section
/// verbatim — do not add or remove entries without updating that section
/// too.
///
/// Lives under `lib/`, not `test/`, so [applySeedIfRequested] (also under
/// `lib/`) can import it with a normal same-package relative import.
/// `test/fixtures/mock_targets.dart` re-exports this file verbatim: once a
/// Dart file under `lib/` is addressed via its `package:gazer/...` URI (as
/// this one is, from every other `lib/` importer), the compiler resolves
/// its own relative imports in package-URI space and clamps `..`
/// traversal at the `lib/` boundary — a relative import reaching from
/// `lib/` into `test/` does not compile under that resolution, however
/// tempting it looks on paper. Keeping the single source of truth here and
/// re-exporting it into `test/fixtures/` (a plain file-addressed location,
/// no such clamping) satisfies both directions without duplicating data.
library;

import '../models/quality.dart';
import '../models/stream_target_settings.dart';

/// Target 1: plain RTMP, key auto-appended, no auth.
final StreamTargetSettings mockTargetPlainRtmp = const StreamTargetSettings(
  url: 'rtmp://ingest-a.example.com/live',
  streamKey: 'demo-key-0001',
);

/// Target 2: RTMPS with username/password auth.
final StreamTargetSettings mockTargetRtmpsAuth = const StreamTargetSettings(
  url: 'rtmps://ingest-b.example.com/app',
  streamKey: 'demo-key-0002',
  username: 'demo',
  password: 'demo-password-0002',
);

/// Target 3: emulator host loopback — nothing listens here. Used by the
/// go-live-unreachable integration test and offline-behaviour widget tests.
final StreamTargetSettings mockTargetEmulatorLoopback =
    const StreamTargetSettings(url: 'rtmp://10.0.2.2:1935/live');

/// Target 4: invalid scheme (`http`, not `rtmp`/`rtmps`) — used by
/// TargetValidator tests asserting the scheme-validation issue fires.
final StreamTargetSettings mockTargetInvalidScheme = const StreamTargetSettings(
  url: 'http://bad.example.com',
);

/// All 4 mock targets, in spec order.
final List<StreamTargetSettings> mockTargets = <StreamTargetSettings>[
  mockTargetPlainRtmp,
  mockTargetRtmpsAuth,
  mockTargetEmulatorLoopback,
  mockTargetInvalidScheme,
];

/// Preset A: default quality — the seeded default and the "happy path"
/// widget/screenshot fixture.
final QualitySettings mockQualityDefault = QualitySettings.defaults();

/// Preset B: low-bandwidth — exercises the resolution/fps/bitrate pickers
/// away from their defaults in widget tests and goldens.
final QualitySettings mockQualityLowBandwidth = const QualitySettings(
  resolution: Resolution.p360,
  frameRate: FrameRate.fps15,
  videoBitrateKbps: 800,
  adaptiveBitrate: false,
);

/// Both quality presets, in spec order.
final List<QualitySettings> mockQualityPresets = <QualitySettings>[
  mockQualityDefault,
  mockQualityLowBandwidth,
];
