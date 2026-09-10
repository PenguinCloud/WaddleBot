package io.waddlebot.gazer.pipeline.sources

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import io.mockk.every
import io.mockk.mockk
import io.waddlebot.gazer.pigeon.VideoDeviceKind
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test

/**
 * VideoSourceFactory covers list()/create() using a fake CameraIds, so no real CameraManager or
 * camera hardware is required. Camera2Source's actual capture behaviour is exercised only on an
 * emulator/device via Task 20's instrumented StreamServiceTest.
 */
class VideoSourceFactoryTest {
    private class FakeCameraIds(
        private val ids: Map<Int, String>,
    ) : CameraIds {
        override fun byFacing(facing: Int): String? = ids[facing]
    }

    /** Context stub satisfying Camera2ApiManager's constructor (Context.getSystemService(CAMERA_SERVICE) as CameraManager). */
    private fun fakeContext(): Context {
        val context = mockk<Context>()
        val cameraManager = mockk<CameraManager>(relaxed = true)
        every { context.getSystemService(Context.CAMERA_SERVICE) } returns cameraManager
        return context
    }

    @Test
    fun `list returns both cameras when both facings exist`() {
        val ids =
            FakeCameraIds(
                mapOf(
                    CameraCharacteristics.LENS_FACING_BACK to "0",
                    CameraCharacteristics.LENS_FACING_FRONT to "1",
                ),
            )
        val devices = VideoSourceFactory(fakeContext(), ids).list()

        assertEquals(2, devices.size)
        assertEquals("camera:back", devices[0].id)
        assertEquals(VideoDeviceKind.BACK_CAMERA, devices[0].kind)
        assertEquals("camera:front", devices[1].id)
        assertEquals(VideoDeviceKind.FRONT_CAMERA, devices[1].kind)
    }

    @Test
    fun `list omits front camera when hardware lacks it`() {
        val ids = FakeCameraIds(mapOf(CameraCharacteristics.LENS_FACING_BACK to "0"))
        val devices = VideoSourceFactory(fakeContext(), ids).list()

        assertEquals(1, devices.size)
        assertEquals("camera:back", devices[0].id)
    }

    @Test
    fun `list returns empty when the device has no camera`() {
        val devices = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap())).list()

        assertEquals(0, devices.size)
    }

    @Test
    fun `create builds a back camera source without throwing`() {
        val factory = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap()))

        val source = factory.create("camera:back")

        assertEquals(false, source.isRunning())
    }

    @Test
    fun `create builds a front camera source without throwing`() {
        val factory = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap()))

        val source = factory.create("camera:front")

        assertEquals(false, source.isRunning())
    }

    @Test
    fun `create rejects an unknown device id`() {
        val factory = VideoSourceFactory(fakeContext(), FakeCameraIds(emptyMap()))

        assertThrows(IllegalArgumentException::class.java) { factory.create("camera:external") }
    }
}
