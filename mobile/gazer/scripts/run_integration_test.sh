#!/usr/bin/env bash
# Runs inside the gazer-toolchain container (the `docker run` invocation
# needs --device /dev/kvm and --network host). Boots a fresh phone AVD
# (gazer_ci), pre-builds and installs a debug APK so CAMERA/RECORD_AUDIO
# can be granted BEFORE the permission_handler dialog would otherwise block
# the Go Live tap, runs the go-live-unreachable integration_test, decodes
# its screenshot, then runs Task 20's instrumented StreamServiceTest
# against the same emulator.
#
# Local equivalent of the CI grant step: to drive this by hand against an
# already-running emulator/device instead, run
#   adb shell pm grant io.waddlebot.gazer android.permission.CAMERA
#   adb shell pm grant io.waddlebot.gazer android.permission.RECORD_AUDIO
#   adb shell pm grant io.waddlebot.gazer android.permission.POST_NOTIFICATIONS
set -euo pipefail

# The canonical PostHog keys from lib/config/flag_keys.dart, in full
# {product}.{feature-name} form. DebugOverrides matches these verbatim against
# FlagKeys.cameraStream etc, so the short "camera-stream" spellings silently
# match nothing: every flag stays OFF, HomeScreen's canGoLive stays false, and
# Go Live is a disabled button the test taps to no effect.
FLAGS_DEFINE="waddlebot.gazer.camera-stream,waddlebot.gazer.adaptive-bitrate,waddlebot.gazer.rtmp-auth,waddlebot.gazer.uvc-capture"

avdmanager --verbose create avd --force -n gazer_ci \
  -k "system-images;android-34;google_apis;x86_64" -d "pixel_6"

# The toolchain image installs the `emulator` package under
# $ANDROID_SDK_ROOT/emulator but only puts cmdline-tools/platform-tools/
# build-tools on PATH, so a bare `emulator` here is a command-not-found --
# resolve the binary explicitly, the same way CI resolves sdkmanager.
EMULATOR_BIN="${ANDROID_SDK_ROOT:-${ANDROID_HOME:?ANDROID_HOME/ANDROID_SDK_ROOT not set}}/emulator/emulator"
if [ ! -x "$EMULATOR_BIN" ]; then
  echo "ERROR: emulator binary not found at $EMULATOR_BIN" >&2
  exit 1
fi

# The emulator's gfxstream/Vulkan init dlopen()s libX11-xcb.so.1 even under
# -no-window and aborts ("Could not open libX11-xcb.so.1, give up") if it is
# missing. The toolchain image is a slim Debian base without libx11-xcb1, but
# the emulator package ships its own copy under lib64/qt/lib -- point the
# emulator process (and only it: this prefix applies to this one child, not to
# the flutter/gradle/java invocations below, whose own libfreetype/libjpeg must
# keep resolving from the system paths) at that directory.
LD_LIBRARY_PATH="${ANDROID_SDK_ROOT:-$ANDROID_HOME}/emulator/lib64/qt/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$EMULATOR_BIN" -avd gazer_ci -no-window -gpu swiftshader_indirect -no-audio \
  -no-boot-anim -no-snapshot -accel on \
  -camera-back emulated -camera-front emulated &
EMULATOR_PID=$!

# Bounded: if the emulator dies during startup (as it does when a dlopen it
# needs fails), a bare `adb wait-for-device` blocks forever and the failure
# only ever surfaces as a job-level timeout with no diagnosis.
if ! timeout 300 adb wait-for-device; then
  echo "ERROR: no emulator attached within 300s - it most likely exited during startup; see the emulator output above" >&2
  exit 1
fi

timeout=180
while [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; do
  timeout=$((timeout - 2))
  if [ "$timeout" -le 0 ]; then
    echo "ERROR: emulator boot timed out" >&2
    exit 1
  fi
  sleep 2
done

# --target builds the integration test's own entrypoint into the APK, and
# `flutter drive --use-application-binary` below then runs exactly this APK.
# That is required, not cosmetic: R23 locks :app's debug/profile/release
# {Runtime,Compile}Classpath, and a Gradle lock is strict both ways. `flutter
# build apk` resolves all three io.flutter:{armeabi_v7a,arm64_v8a,x86_64}_debug
# artifacts and satisfies the lock; `flutter drive` on its own passes
# -Ptarget-platform=android-x64 for the attached emulator, leaving the two arm
# artifacts unresolved and failing :app:mergeDebugAssets with "Did not resolve
# ... which is part of the dependency lock state".
flutter build apk --debug \
  --target=integration_test/go_live_unreachable_test.dart \
  --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE"
adb install -r build/app/outputs/flutter-apk/app-debug.apk
adb shell pm grant io.waddlebot.gazer android.permission.CAMERA
adb shell pm grant io.waddlebot.gazer android.permission.RECORD_AUDIO
# API 33+ made POST_NOTIFICATIONS a runtime permission, and PermissionHandlerGate
# requests it alongside camera/microphone whenever sdkInt >= 33 (this AVD is
# android-34). Without this grant, `permissions.request()` raises the system
# permission dialog -- which lives outside the Flutter view, so the integration
# test cannot dismiss it -- the gate resolves to `denied`, Go Live never starts
# the pipeline, and the ConnectingState assertion fails.
adb shell pm grant io.waddlebot.gazer android.permission.POST_NOTIFICATIONS

# `flutter drive`, not `flutter test`: only integrationDriver() (test_driver/
# integration_test.dart) writes build/integration_response_data.json, which is
# where binding.takeScreenshot()'s PNG bytes land and what decode_screenshots.py
# reads. `flutter test <integration_test/...> -d <device>` bridges only the
# package:test protocol and drops the binding's reportData entirely.
flutter drive \
  --driver=test_driver/integration_test.dart \
  --target=integration_test/go_live_unreachable_test.dart \
  --use-application-binary=build/app/outputs/flutter-apk/app-debug.apk \
  -d emulator-5554 \
  --timeout=900 \
  --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE" \
  | tee /tmp/flutter_integration.log

grep -qE '\+[1-9][0-9]*' /tmp/flutter_integration.log

python3 scripts/decode_screenshots.py

cd android
./gradlew connectedDebugAndroidTest | tee /tmp/gradle_connected.log
grep -q "BUILD SUCCESSFUL" /tmp/gradle_connected.log
cd ..

adb emu kill || echo "emulator already exited"
wait "$EMULATOR_PID" 2>/dev/null || echo "emulator process already reaped"

echo "integration test + connectedDebugAndroidTest complete"
