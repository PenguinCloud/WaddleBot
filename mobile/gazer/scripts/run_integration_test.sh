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
set -euo pipefail

FLAGS_DEFINE="camera-stream,adaptive-bitrate,rtmp-auth,uvc-capture"

avdmanager --verbose create avd --force -n gazer_ci \
  -k "system-images;android-34;google_apis;x86_64" -d "pixel_6"

emulator -avd gazer_ci -no-window -gpu swiftshader_indirect -no-audio \
  -no-boot-anim -no-snapshot -accel on \
  -camera-back emulated -camera-front emulated &
EMULATOR_PID=$!

adb wait-for-device

timeout=180
while [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; do
  timeout=$((timeout - 2))
  if [ "$timeout" -le 0 ]; then
    echo "ERROR: emulator boot timed out" >&2
    exit 1
  fi
  sleep 2
done

flutter build apk --debug --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE"
adb install -r build/app/outputs/flutter-apk/app-debug.apk
adb shell pm grant io.waddlebot.gazer android.permission.CAMERA
adb shell pm grant io.waddlebot.gazer android.permission.RECORD_AUDIO

flutter test integration_test/go_live_unreachable_test.dart -d emulator-5554 \
  --dart-define=GAZER_FLAGS_OVERRIDE="$FLAGS_DEFINE" \
  | tee /tmp/integration_test.log

grep -qE '\+[1-9][0-9]*' /tmp/integration_test.log

python3 scripts/decode_screenshots.py

cd android
./gradlew connectedDebugAndroidTest | tee /tmp/gradle_connected.log
grep -q "BUILD SUCCESSFUL" /tmp/gradle_connected.log
cd ..

adb emu kill || echo "emulator already exited"
wait "$EMULATOR_PID" 2>/dev/null || echo "emulator process already reaped"

echo "integration test + connectedDebugAndroidTest complete"
