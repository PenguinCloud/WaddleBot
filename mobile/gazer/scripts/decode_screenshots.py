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
import sys

RESPONSE_PATH = pathlib.Path("build/integration_response_data.json")
OUT_DIR = pathlib.Path("build/integration_screenshots")


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
        out_path = OUT_DIR / f"{name}.png"
        out_path.write_bytes(bytes(entry["bytes"]))
        print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")

    print(f"decoded {len(screenshots)} screenshot(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
