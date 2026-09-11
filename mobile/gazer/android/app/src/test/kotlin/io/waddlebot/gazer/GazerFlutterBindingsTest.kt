package io.waddlebot.gazer

import android.content.Context
import android.hardware.camera2.CameraManager
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.dart.DartExecutor
import io.flutter.plugin.common.BinaryMessenger
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Assertions.assertDoesNotThrow
import org.junit.jupiter.api.Test

/**
 * GazerFlutterBindings.install is the sole home for MainActivity's real Pigeon wiring (R11):
 * MainActivity itself stays an untestable, JaCoCo-excluded 3-line bridge (Activities need
 * Robolectric/instrumentation to construct), so this plain JVM test is the only coverage for
 * "does installing against a FlutterEngine resolve the CameraManager and register the
 * GazerHostApi channel handlers without throwing".
 */
class GazerFlutterBindingsTest {
    @Test
    fun `install resolves the CameraManager and wires GazerHostApi against the engine's messenger`() {
        val messenger = mockk<BinaryMessenger>(relaxed = true)
        val dartExecutor = mockk<DartExecutor>(relaxed = true)
        every { dartExecutor.binaryMessenger } returns messenger
        val flutterEngine = mockk<FlutterEngine>(relaxed = true)
        every { flutterEngine.dartExecutor } returns dartExecutor
        val cameraManager = mockk<CameraManager>(relaxed = true)
        val context = mockk<Context>(relaxed = true)
        every { context.getSystemService(Context.CAMERA_SERVICE) } returns cameraManager

        assertDoesNotThrow { GazerFlutterBindings.install(flutterEngine, context) }

        verify { context.getSystemService(Context.CAMERA_SERVICE) }
        verify { flutterEngine.dartExecutor }
    }

    @Test
    fun `uninstall detaches GazerHostApi and disposes the installed impl without throwing`() {
        val messenger = mockk<BinaryMessenger>(relaxed = true)
        val dartExecutor = mockk<DartExecutor>(relaxed = true)
        every { dartExecutor.binaryMessenger } returns messenger
        val flutterEngine = mockk<FlutterEngine>(relaxed = true)
        every { flutterEngine.dartExecutor } returns dartExecutor
        val cameraManager = mockk<CameraManager>(relaxed = true)
        val context = mockk<Context>(relaxed = true)
        every { context.getSystemService(Context.CAMERA_SERVICE) } returns cameraManager
        GazerFlutterBindings.install(flutterEngine, context)

        assertDoesNotThrow { GazerFlutterBindings.uninstall(flutterEngine) }

        // install + uninstall each read dartExecutor.binaryMessenger once.
        verify(exactly = 2) { flutterEngine.dartExecutor }
    }
}
