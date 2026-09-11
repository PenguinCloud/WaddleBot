package io.waddlebot.gazer.pipeline

import android.content.Context
import android.hardware.camera2.CameraManager
import io.mockk.every
import io.mockk.mockk
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Test

/**
 * buildStreamPipeline resolves its CameraManager and wires GazerPipeline from a plain [Context]
 * and [RelayPipelineListener] - no real StreamService instance needed - mirroring how
 * GazerFlutterBindings.install is tested, so this wiring is covered without Robolectric.
 */
class StreamPipelineFactoryTest {
    @Test
    fun `builds a GazerPipeline from a mocked context's CameraManager`() {
        val cameraManager = mockk<CameraManager>(relaxed = true)
        val context = mockk<Context>(relaxed = true)
        every { context.getSystemService(Context.CAMERA_SERVICE) } returns cameraManager

        val pipeline = buildStreamPipeline(context, RelayPipelineListener())

        assertNotNull(pipeline)
    }
}
