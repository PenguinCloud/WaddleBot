package io.waddlebot.gazer

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine

/**
 * Sole platform-channel entry point. Runtime permission requests (CAMERA, RECORD_AUDIO,
 * POST_NOTIFICATIONS) are handled entirely in Dart via permission_handler before Go Live is ever
 * called - this activity never requests permissions itself. All real Pigeon wiring (install and
 * uninstall) lives in GazerFlutterBindings (controller ruling R11): this class must stay a thin,
 * JaCoCo-excluded bridge, since Activities need Robolectric/instrumentation to construct and
 * cannot be exercised by a plain JVM unit test.
 */
class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        GazerFlutterBindings.install(flutterEngine, applicationContext)
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        GazerFlutterBindings.uninstall(flutterEngine)
        super.cleanUpFlutterEngine(flutterEngine)
    }
}
