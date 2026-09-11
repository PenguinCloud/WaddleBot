package io.waddlebot.gazer.pipeline

import io.waddlebot.gazer.pigeon.NativePipelineState
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/**
 * WakeLockController's acquire/release decision is injected as plain lambdas (never a real
 * PowerManager), so this pure decision table is fully covered here without StreamService's own
 * Android-framework-bound plumbing.
 */
class WakeLockControllerTest {
    @Test
    fun `STREAMING acquires the wake lock`() {
        var acquired = 0
        var released = 0
        val controller = WakeLockController(acquire = { acquired++ }, release = { released++ })

        controller.onState(NativePipelineState.STREAMING)

        assertEquals(1, acquired)
        assertEquals(0, released)
    }

    @Test
    fun `IDLE releases the wake lock`() {
        var acquired = 0
        var released = 0
        val controller = WakeLockController(acquire = { acquired++ }, release = { released++ })

        controller.onState(NativePipelineState.IDLE)

        assertEquals(0, acquired)
        assertEquals(1, released)
    }

    @Test
    fun `every other state is a no-op`() {
        var acquired = 0
        var released = 0
        val controller = WakeLockController(acquire = { acquired++ }, release = { released++ })

        NativePipelineState.entries
            .filter { it != NativePipelineState.STREAMING && it != NativePipelineState.IDLE }
            .forEach { controller.onState(it) }

        assertEquals(0, acquired)
        assertEquals(0, released)
    }
}
