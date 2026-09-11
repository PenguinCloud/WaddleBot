package io.waddlebot.gazer.pipeline

import io.mockk.mockk
import org.junit.jupiter.api.Assertions.assertSame
import org.junit.jupiter.api.Test

/**
 * StreamService.LocalBinder takes its pipeline/attach-listener dependencies as constructor
 * parameters rather than capturing an outer StreamService instance (`inner class`), specifically
 * so it can be constructed directly here without a real, Robolectric/instrumentation-backed
 * Service - this is also what lets PigeonHostApiImplTest drive the real onServiceConnected() cast
 * success path.
 */
class LocalBinderTest {
    @Test
    fun `pipeline delegates to the injected provider`() {
        val pipeline = mockk<GazerPipeline>(relaxed = true)
        val binder = StreamService.LocalBinder(pipelineProvider = { pipeline }, attachListener = {})

        assertSame(pipeline, binder.pipeline)
    }

    @Test
    fun `setListener delegates to the injected attach callback`() {
        var attached: PipelineListener? = null
        val binder =
            StreamService.LocalBinder(pipelineProvider = { mockk(relaxed = true) }, attachListener = { attached = it })
        val listener = mockk<PipelineListener>(relaxed = true)

        binder.setListener(listener)

        assertSame(listener, attached)
    }
}
