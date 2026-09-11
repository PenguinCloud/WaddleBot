/// Test-facing re-export of the canonical mock fixtures.
///
/// The actual data lives in `lib/config/mock_targets.dart` — see that
/// file's doc comment for why: `lib/config/seed.dart` needs these values
/// too, and a relative import from a `lib/` file into `test/` does not
/// compile once the importing file is addressed via its `package:gazer/...`
/// URI (Dart clamps `..` traversal at the `lib/` boundary). Re-exporting
/// here keeps every existing `test/fixtures/mock_targets.dart` /
/// `../fixtures/mock_targets.dart` import working unchanged, with exactly
/// one copy of the data.
library;

export 'package:gazer/config/mock_targets.dart';
