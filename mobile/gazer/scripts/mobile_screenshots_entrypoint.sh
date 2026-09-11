#!/usr/bin/env bash
# Runs inside the gazer-toolchain container (the `docker run` invocation
# needs --device /dev/kvm and --network host). Boots the phone AVD
# (gazer_ci), builds+installs a debug APK targeting
# integration_test/screenshots_test.dart, drives it via
# test_driver/integration_test.dart for the phone shots, tears the
# emulator down, then boots the tablet AVD (gazer_tablet, Pixel Tablet
# profile, 2560x1600 skin -- avdmanager's device profile "pixel_tablet"
# supplies the base hardware definition; the skin override is an emulator
# launch flag, not an avdmanager create-time one), runs the same flow for
# the tablet shots, tears it down. scripts/decode_screenshots.py (Task 21)
# is additive across both runs.
#
# Mirrors scripts/run_integration_test.sh's proven boot/build/grant/drive
# sequence rather than `flutter test integration_test/...`: only
# `flutter drive --driver=test_driver/integration_test.dart` writes
# build/integration_response_data.json, which is where
# binding.takeScreenshot()'s PNG bytes land and what
# scripts/decode_screenshots.py reads -- `flutter test` bridges only the
# package:test protocol and drops that reportData entirely.
#
# Usage: mobile_screenshots_entrypoint.sh [phone|tablet]
#   No argument (the `make mobile-screenshots` invocation): runs both,
#   sequentially. emulator-5554 is the harness's one hardcoded device id
#   (see test_driver/integration_test.dart / run_integration_test.sh), so
#   only one AVD is ever booted at a time -- an explicit argument lets a
#   single form factor be re-run without waiting through the other.
set -euo pipefail

REQUESTED_FORM_FACTOR="${1:-both}"
case "$REQUESTED_FORM_FACTOR" in
  both|phone|tablet) ;;
  *)
    echo "usage: mobile_screenshots_entrypoint.sh [phone|tablet]" >&2
    exit 1
    ;;
esac

# The canonical PostHog keys from lib/config/flag_keys.dart, in full
# {product}.{feature-name} form. DebugOverrides (providers/license_provider.dart)
# matches these verbatim against FlagKeys.cameraStream etc, so a short
# "camera-stream" spelling would silently match nothing -- every flag stays
# OFF and Go Live stays a disabled button. Matches
# scripts/run_integration_test.sh's FLAGS_DEFINE exactly.
FLAGS_DEFINE="waddlebot.gazer.camera-stream,waddlebot.gazer.adaptive-bitrate,waddlebot.gazer.rtmp-auth,waddlebot.gazer.uvc-capture"

# The toolchain image installs the `emulator` package under
# $ANDROID_SDK_ROOT/emulator but only puts cmdline-tools/platform-tools/
# build-tools on PATH (see the Dockerfile), so a bare `emulator` here is a
# command-not-found -- resolve the binary explicitly, same as
# run_integration_test.sh.
EMULATOR_BIN="${ANDROID_SDK_ROOT:-${ANDROID_HOME:?ANDROID_HOME/ANDROID_SDK_ROOT not set}}/emulator/emulator"
if [ ! -x "$EMULATOR_BIN" ]; then
  echo "ERROR: emulator binary not found at $EMULATOR_BIN" >&2
  exit 1
fi

# emulator-5554 is the harness's one hardcoded device id. Another agent on
# this host may be mid-run against it (e.g. mobile-test-integration) --
# wait for the slot to free up rather than failing outright.
wait_for_emulator_slot() {
  local max_wait=1200
  local waited=0
  while adb devices 2>/dev/null | grep -q '^emulator-5554'; do
    if [ "$waited" -ge "$max_wait" ]; then
      echo "ERROR: emulator-5554 still occupied after ${max_wait}s -- giving up" >&2
      return 1
    fi
    echo "emulator-5554 busy (another run in progress?) -- waiting 30s (${waited}/${max_wait}s elapsed)"
    sleep 30
    waited=$((waited + 30))
  done
}

wait_for_boot() {
  local timeout=180
  while [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; do
    timeout=$((timeout - 2))
    if [ "$timeout" -le 0 ]; then
      echo "ERROR: emulator boot timed out" >&2
      return 1
    fi
    sleep 2
  done
}

run_form_factor() {
  local avd_name="$1"
  local emulator_flags="$2"
  local form_factor="$3"

  wait_for_emulator_slot

  # See run_integration_test.sh: the emulator's gfxstream/Vulkan init
  # dlopen()s libX11-xcb.so.1 and aborts under -no-window without it -- the
  # toolchain image is a slim Debian base missing libx11-xcb1, but the
  # emulator package ships its own copy under lib64/qt/lib. Scoped to this
  # one child process only: flutter/gradle/java below must keep resolving
  # their own libfreetype/libjpeg from the system paths.
  # shellcheck disable=SC2086
  LD_LIBRARY_PATH="${ANDROID_SDK_ROOT:-$ANDROID_HOME}/emulator/lib64/qt/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$EMULATOR_BIN" -avd "$avd_name" -no-window -gpu swiftshader_indirect -no-audio \
    -no-boot-anim -no-snapshot -accel on $emulator_flags &
  local emulator_pid=$!

  # Bounded: if the emulator dies during startup, a bare `adb wait-for-device`
  # blocks forever and the failure only ever surfaces as a job-level timeout.
  if ! timeout 300 adb wait-for-device; then
    echo "ERROR: no emulator attached within 300s for $form_factor -- it most likely exited during startup; see the emulator output above" >&2
    return 1
  fi
  wait_for_boot

  # --target builds the integration test's own entrypoint into the APK, and
  # `flutter drive --use-application-binary` below then runs exactly this
  # APK -- required, not cosmetic, per R23's locked :app dependency
  # configuration; see run_integration_test.sh for the full explanation.
  # All three defines are baked in at build time (dart-define values are
  # compile-time constants); passed again to `flutter drive` below purely
  # for consistency with the established convention.
  flutter build apk --debug \
    --target=integration_test/screenshots_test.dart \
    --dart-define=GAZER_SEED=true \
    --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE" \
    --dart-define=GAZER_SCREENSHOT_FORM_FACTOR="$form_factor"
  adb install -r build/app/outputs/flutter-apk/app-debug.apk
  adb shell pm grant io.waddlebot.gazer android.permission.CAMERA
  adb shell pm grant io.waddlebot.gazer android.permission.RECORD_AUDIO
  # API 33+ made POST_NOTIFICATIONS a runtime permission; without this grant
  # the system permission dialog blocks the test (it lives outside the
  # Flutter view and the test cannot dismiss it).
  adb shell pm grant io.waddlebot.gazer android.permission.POST_NOTIFICATIONS

  flutter drive \
    --driver=test_driver/integration_test.dart \
    --target=integration_test/screenshots_test.dart \
    --use-application-binary=build/app/outputs/flutter-apk/app-debug.apk \
    -d emulator-5554 \
    --timeout=900 \
    --dart-define=GAZER_SEED=true \
    --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE" \
    --dart-define=GAZER_SCREENSHOT_FORM_FACTOR="$form_factor" \
    | tee "/tmp/screenshots_${form_factor}.log"

  grep -qE '\+[1-9][0-9]*' "/tmp/screenshots_${form_factor}.log"

  python3 scripts/decode_screenshots.py

  adb emu kill || echo "emulator for $form_factor already exited"
  wait "$emulator_pid" 2>/dev/null || echo "emulator process for $form_factor already reaped"
}

if [ "$REQUESTED_FORM_FACTOR" = "both" ] || [ "$REQUESTED_FORM_FACTOR" = "phone" ]; then
  avdmanager --verbose create avd --force -n gazer_ci \
    -k "system-images;android-34;google_apis;x86_64" -d "pixel_6"
  run_form_factor "gazer_ci" "-camera-back emulated -camera-front emulated" "phone"
fi

if [ "$REQUESTED_FORM_FACTOR" = "both" ] || [ "$REQUESTED_FORM_FACTOR" = "tablet" ]; then
  avdmanager --verbose create avd --force -n gazer_tablet \
    -k "system-images;android-34;google_apis;x86_64" -d "pixel_tablet"
  run_form_factor "gazer_tablet" "-camera-back emulated -camera-front emulated -skin 2560x1600" "tablet"
fi

echo "screenshot capture complete for form factor(s): $REQUESTED_FORM_FACTOR"
