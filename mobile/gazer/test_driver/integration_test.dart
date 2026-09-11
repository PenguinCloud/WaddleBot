import 'package:integration_test/integration_test_driver.dart';

/// Host-side `flutter drive` driver for every test under `integration_test/`.
///
/// `integrationDriver()` collects the on-device results and writes the test
/// binding's `reportData` -- which is where each `binding.takeScreenshot(name)`
/// call accumulates its PNG bytes -- to `build/integration_response_data.json`,
/// the file `scripts/decode_screenshots.py` decodes into per-screenshot PNGs.
/// `flutter test <integration_test/...> -d <device>` cannot produce that file:
/// the tool bridges only the package:test protocol (see flutter_tools'
/// test/flutter_platform.dart) and drops `reportData` entirely, so the
/// screenshot artifact requires this driver.
Future<void> main() => integrationDriver();
