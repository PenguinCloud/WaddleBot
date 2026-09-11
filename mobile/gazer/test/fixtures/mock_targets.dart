/// The 4 seeded stream-target presets and 2 quality presets used across
/// widget tests, the integration tests, and `make mobile-screenshots`
/// capture runs. Mirrors the spec's Mock Data section verbatim — do not
/// add or remove entries without updating that section too.
library;

import 'package:gazer/models/quality.dart';
import 'package:gazer/models/stream_target_settings.dart';

/// Target 1: plain RTMP, key auto-appended, no auth.
final StreamTargetSettings mockTargetPlainRtmp = StreamTargetSettings(
  url: 'rtmp://ingest-a.example.com/live',
  streamKey: 'demo-key-0001',
);

/// Target 2: RTMPS with username/password auth.
final StreamTargetSettings mockTargetRtmpsAuth = StreamTargetSettings(
  url: 'rtmps://ingest-b.example.com/app',
  streamKey: 'demo-key-0002',
  username: 'demo',
  password: 'demo-password-0002',
);

/// Target 3: emulator host loopback — nothing listens here. Used by the
/// go-live-unreachable integration test and offline-behaviour widget tests.
final StreamTargetSettings mockTargetEmulatorLoopback = StreamTargetSettings(
  url: 'rtmp://10.0.2.2:1935/live',
);

/// Target 4: invalid scheme (`http`, not `rtmp`/`rtmps`) — used by
/// TargetValidator tests asserting the scheme-validation issue fires.
final StreamTargetSettings mockTargetInvalidScheme = StreamTargetSettings(
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
final QualitySettings mockQualityLowBandwidth = QualitySettings(
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
