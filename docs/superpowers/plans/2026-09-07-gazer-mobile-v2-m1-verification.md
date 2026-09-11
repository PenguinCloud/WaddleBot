# Gazer Mobile 2.0 M1 — Verification Results

**Date:** 2026-09-11 | **HEAD:** `8d9a05c6954d315d3c4b642c427d4b372df1fc93` | **Branch:** `feature/gazer-mobile-v2` | **CI run A:** [`34654942280`](https://github.com/penguintechinc/waddlebot/actions/runs/34654942280) — **success**

Verification run against integration round 9 (the final M1 integration), per Task 26 brief Step 13. All automated gates below are green. One item — the manual physical-device stream/reconnect test — could not be performed in this automated agent environment (no physical phone or real RTMP endpoint available) and is recorded as **deferred**, not fabricated.

## Gate results

| Gate | Result |
|---|---|
| `make mobile-lint` | **PASS** (exit 0) — `flutter analyze`: No issues found (26.7s); `dart format --set-exit-if-changed .`: 120 files, 0 changed; `ktlintCheck` + gradle `lint`: BUILD SUCCESSFUL (35s) |
| `make mobile-test` | **PASS** — **246/246** Dart tests passed; lcov coverage **92.71%** (1424/1536 lines), **42 files examined** (56 total, 14 generated-file records excluded) — threshold 90% met |
| `make mobile-telemetry-check` | **PASS** — `telemetry sink received: logs=1 metrics=2 histograms=1 spans=1` — all four counts ≥1 |
| `make mobile-test-android` | **PASS** — **92/92** JUnit tests, 0 failures/errors (19 app-module `TEST-*.xml` files); JaCoCo **95.43%** (418/438 lines) — threshold 90% met |
| `make mobile-security` | **PASS** — osv-scanner: **156 packages** examined (`pubspec.lock`), **162 packages** examined (`android/app/gradle.lockfile`), 0 vulnerabilities either lockfile; semgrep: **465 rules** run on **146 files**, 0 findings; gitleaks: 0 leaks. See note below on the first run's false positives. |
| `make mobile-build` | **PASS** — all 3 split-per-ABI APKs and the AAB built, obfuscated, split debug info; sizes below |
| `make mobile-test-integration` | **PASS** — Dart integration test `00:30 +2: All tests passed!`; screenshot `build/integration_screenshots/go-live-unreachable.png` (53,477 bytes) decoded; `connectedDebugAndroidTest` BUILD SUCCESSFUL in 25s; emulator boot 74.9s |
| `make mobile-screenshots` | **PASS** — exactly 5 files in `docs/screenshots/gazer/`; all visually reviewed (no DEBUG ribbon, no error text, License row "Valid", Go Live enabled) |
| `make seed-mock-data-mobile` | **PASS** (bounded live smoke test — target is inherently interactive/non-terminating, not part of any automated gate) — debug APK built, package `io.waddlebot.gazer` installed, `flutter run`'s hot-reload REPL banner + DevTools URL printed, bounded 90s timeout ended the session cleanly, emulator torn down, no residual process |
| CI (`gazer-mobile.yml`, run `34654942280`) | **PASS** — every job success or correctly-skipped; table below |
| apksigner (CI-built APK) | **PASS (debug-signed, as expected)** — see below |
| Manual physical-device test | **DEFERRED** — see below, not fabricated |

### `mobile-security` — clean-tree note

The first `mobile-security` run (against a tree carrying `build/` output left over from prior local gates in this same session) reported 5 gitleaks "findings" — all `generic-api-key` matches against BouncyCastle class-path strings (e.g. `org/bouncycastle/crypto/AlphabetMapper`) inside `build/app/intermediates/incremental/debug-mergeJavaRes/zip-cache/...`. `build/` is gitignored (`mobile/gazer/.gitignore:33`) and CI's `security` job runs `gitleaks detect --source . --no-git -v` against a fresh `actions/checkout` that never has a `build/` directory — confirmed green in run `34654942280`. Ran `make mobile-clean` (removes `build/`, `.dart_tool/`) and reran `mobile-security` against the clean tree matching CI's actual scan surface: 0 leaks. Not a code defect, not a gate weakened — the local working tree had gained build cruft from the `mobile-test-android`/`mobile-test-integration`/`seed-mock-data-mobile`/`mobile-screenshots` gates run earlier in this same session.

### APK sizes (per ABI, all < 100MB)

| ABI | Size |
|---|---|
| `app-armeabi-v7a-release.apk` | 18,125,600 bytes (17.3 MB) |
| `app-arm64-v8a-release.apk` | 20,798,800 bytes (19.8 MB) |
| `app-x86_64-release.apk` | 22,282,572 bytes (21.3 MB) |
| `app-release.aab` (bundle) | ~52.9 MB |

### CI run `34654942280` — per-job results

| Job | Conclusion |
|---|---|
| Build toolchain image | success (cache hit — Dockerfile unchanged, tag stayed `a0a28722ac14`) |
| Dart analyze | success |
| Dart unit tests + coverage gate | success |
| Kotlin unit tests + JaCoCo gate | success |
| Build APK + AAB | success (includes CI's own "Verify APK is signed with exactly one certificate" step) |
| Security scans | success |
| Integration test (emulator) | success |
| GitHub Release | skipped (not a `gazer-v*` tag — correct) |

### apksigner check (CI-built `app-arm64-v8a-release.apk`, downloaded via `gh run download 34654942280 -n gazer-apk`)

```
Signer #1 certificate DN: C=US, O=Android, CN=Android Debug
Signer #1 certificate SHA-256 digest: 9cf82251185b60c23d9f70657ad3a56631c9cffa633528a97b056bf56a65d555
```

Exactly **1 signer**, certificate is the **Android debug certificate** (`CN=Android Debug`) — confirms this build is debug-signed, not release-signed. `GAZER_REQUIRE_SIGNING` only activates release signing on a `refs/tags/gazer-v*` push, and `ANDROID_UPLOAD_KEY_STORE_B64`/`ANDROID_UPLOAD_KEY_STORE_PASSWORD`/`ANDROID_UPLOAD_KEY_ALIAS`/`ANDROID_UPLOAD_KEY_ALIAS_PASSWORD` are not yet configured as repo secrets — release signing is correctly deferred, not silently skipped.

## Manual physical-device step — DEFERRED

Task 26 brief Step 13's manual step (install on a physical Pixel 8/9 or Galaxy S24, enter a real RTMP endpoint on-device, stream 5 minutes, disable Wi-Fi mid-stream, confirm bitrate/dropped-frame/reconnect behavior) requires physical hardware and a real RTMP ingest endpoint that this automated integration environment does not have. It was **not performed** and its results are **not fabricated** here. This step remains open and must be run by a human with access to a physical device and RTMP endpoint before the merge gate below can be called fully satisfied.

## Known deferred items (not blockers for this integration round, tracked for follow-up)

| Item | Status |
|---|---|
| Release signing (real upload keystore) | Waiting on the user's keystore + 4 GitHub secrets (`ANDROID_UPLOAD_KEY_STORE_B64` etc.); CI's `build` job already branches correctly on `steps.check_keystore.outputs.present` |
| Manual physical-device stream/reconnect test | Not run (see above) — needs a human with hardware + a real RTMP endpoint |
| Repo-wide "Security & Code Quality" workflow | Red (`34654942270`, same HEAD) on pre-existing Node audit findings outside `mobile/gazer` — out of scope for this app, confirmed still failing, not newly broken by this round |
| USB capture-card (UVC) input | M2/M3 scope, not M1 |
| iOS client | Later milestone, not M1 |

## Merge gate

Per the brief: merge to `release/v3.0.X` happens via PR once every gate is green **and** the manual physical-device test passes. All scripted/CI gates above are green. The manual physical-device step is the one remaining item before that gate is fully satisfied — flagged here rather than merged prematurely.
