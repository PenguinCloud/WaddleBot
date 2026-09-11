#!/usr/bin/env python3
"""Decode build/integration_response_data.json's embedded screenshots into
individual PNG files under build/integration_screenshots/.

`flutter test integration_test/<file>.dart -d <device>` writes this JSON
when the test binding is IntegrationTestWidgetsFlutterBinding; each
`binding.takeScreenshot(name)` call adds one entry under the top-level
"screenshots" key, with "screenshotName" and a raw (non-base64) "bytes"
array of PNG byte values. This script is additive: it never clears
build/integration_screenshots/, so re-running it after a second test run
(e.g. the tablet pass in Task 26) layers new files in without deleting
the first run's output.
"""
import json
import pathlib
import re
import sys

RESPONSE_PATH = pathlib.Path("build/integration_response_data.json")
OUT_DIR = pathlib.Path("build/integration_screenshots")

# Screenshot names come from `binding.takeScreenshot(name)` calls in test source
# under our control today, but this script still treats
# integration_response_data.json as untrusted input: it is JSON written by a
# separate process (the Flutter test runner) and parsed here before any name
# is used to build a filesystem path. A name outside this charset, or one
# containing "..", is rejected outright rather than risking a path-traversal
# write outside OUT_DIR (e.g. "../../etc/cron.d/x").
_VALID_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def main() -> int:
    if not RESPONSE_PATH.exists():
        print(f"ERROR: {RESPONSE_PATH} not found - did the integration test run?", file=sys.stderr)
        return 1

    data = json.loads(RESPONSE_PATH.read_text())
    screenshots = data.get("screenshots", [])
    if not screenshots:
        print("ERROR: zero screenshots found in integration_response_data.json", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for entry in screenshots:
        name = entry["screenshotName"]
        if not _VALID_NAME_RE.match(name) or ".." in name:
            print(
                f"ERROR: refusing unsafe screenshotName {name!r} "
                f"(must match {_VALID_NAME_RE.pattern} and not contain '..')",
                file=sys.stderr,
            )
            return 1
        out_path = OUT_DIR / f"{name}.png"
        out_path.write_bytes(bytes(entry["bytes"]))
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")

    print(f"decoded {len(screenshots)} screenshot(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
