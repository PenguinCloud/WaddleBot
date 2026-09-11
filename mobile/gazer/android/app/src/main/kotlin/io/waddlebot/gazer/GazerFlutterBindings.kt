package io.waddlebot.gazer

import android.content.Context
import android.hardware.camera2.CameraManager
import io.flutter.embedding.engine.FlutterEngine
import io.waddlebot.gazer.pigeon.GazerFlutterApi
import io.waddlebot.gazer.pigeon.GazerHostApi
import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
import io.waddlebot.gazer.pipeline.sources.CameraManagerIds
import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory

/**
 * Builds a PigeonHostApiImpl for [flutterEngine]'s Dart<->platform channel and registers it as
 * the GazerHostApi. Extracted out of MainActivity (controller ruling R11) so this wiring is
 * covered by a plain JVM unit test: MainActivity itself needs Robolectric/instrumentation to
 * construct and is excluded from JaCoCo (see app/build.gradle.kts), so it must stay a thin
 * bridge that only calls into this object - all real logic lives here instead.
 */
object GazerFlutterBindings {
    /** Wires PigeonHostApiImpl into [flutterEngine] for [context]; safe to call once per engine attach. */
    fun install(
        flutterEngine: FlutterEngine,
        context: Context,
    ) {
        val messenger = flutterEngine.dartExecutor.binaryMessenger
        val flutterApi = GazerFlutterApi(messenger)
        val cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val impl =
            PigeonHostApiImpl(
                context = context,
                flutterApi = flutterApi,
                videoDevices = { VideoSourceFactory(context, CameraManagerIds(cameraManager)).list() },
                audioDevices = { AudioSourceFactory().list() },
            )
        GazerHostApi.setUp(messenger, impl)
    }
}
