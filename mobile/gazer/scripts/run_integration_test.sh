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
