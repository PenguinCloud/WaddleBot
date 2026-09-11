package io.waddlebot.gazer.pipeline

import io.waddlebot.gazer.pigeon.GazerErrorCode
import io.waddlebot.gazer.pigeon.NativePipelineState
import io.waddlebot.gazer.pigeon.StatsSample
import org.junit.jupiter.api.Assertions.assertDoesNotThrow
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/**
 * RelayPipelineListener has no Android framework dependency of its own - it only fans a call out
 * to every attached [PipelineListener] - so it is exercised directly here rather than only
 * indirectly through StreamService (which needs Robolectric/instrumentation to construct).
 */
class RelayPipelineListenerTest {
    private class RecordingListener : PipelineListener {
        val states = mutableListOf<NativePipelineState>()
        val stats = mutableListOf<StatsSample>()
        val authResults = mutableListOf<Boolean>()

        override fun onState(
            state: NativePipelineState,
            error: GazerErrorCode?,
            detail: String?,
        ) {
            states.add(state)
        }

        override fun onStats(sample: StatsSample) {
            stats.add(sample)
        }

        override fun onAuthResult(ok: Boolean) {
            authResults.add(ok)
        }
    }

    @Test
    fun `onState fans out to every attached listener`() {
        val relay = RelayPipelineListener()
        val first = RecordingListener()
        val second = RecordingListener()
        relay.attach(first)
        relay.attach(second)

        relay.onState(NativePipelineState.STREAMING, null, null)

        assertEquals(listOf(NativePipelineState.STREAMING), first.states)
        assertEquals(listOf(NativePipelineState.STREAMING), second.states)
    }

    @Test
    fun `onStats fans out to every attached listener`() {
        val relay = RelayPipelineListener()
        val listener = RecordingListener()
        relay.attach(listener)
        val sample =
            StatsSample(
                bitrateKbps = 1000L,
                fps = 30.0,
                droppedVideoFrames = 0L,
                sentBytes = 0L,
                congestionPercent = 0.0,
            )

        relay.onStats(sample)

        assertEquals(listOf(sample), listener.stats)
    }

    @Test
    fun `onAuthResult fans out to every attached listener`() {
        val relay = RelayPipelineListener()
        val listener = RecordingListener()
        relay.attach(listener)

        relay.onAuthResult(true)

        assertEquals(listOf(true), listener.authResults)
    }

    @Test
    fun `detach stops a listener from receiving further calls`() {
        val relay = RelayPipelineListener()
        val listener = RecordingListener()
        relay.attach(listener)
        relay.detach(listener)

        relay.onState(NativePipelineState.IDLE, null, null)

        assertEquals(emptyList<NativePipelineState>(), listener.states)
    }

    @Test
    fun `attaching a new listener during onState iteration does not throw`() {
        val relay = RelayPipelineListener()
        val lateJoiner = RecordingListener()
        var alreadyAttached = false
        val selfAttachingListener =
            object : PipelineListener {
                override fun onState(
                    state: NativePipelineState,
                    error: GazerErrorCode?,
                    detail: String?,
                ) {
                    if (!alreadyAttached) {
                        alreadyAttached = true
                        relay.attach(lateJoiner)
                    }
                }

                override fun onStats(sample: StatsSample) = Unit

                override fun onAuthResult(ok: Boolean) = Unit
            }
        relay.attach(selfAttachingListener)

        assertDoesNotThrow { relay.onState(NativePipelineState.STREAMING, null, null) }

        // CopyOnWriteArrayList's iterator is a point-in-time snapshot: the listener attached
        // mid-iteration above never sees that call, but does see every call after it.
        assertEquals(emptyList<NativePipelineState>(), lateJoiner.states)
        relay.onState(NativePipelineState.IDLE, null, null)
        assertEquals(listOf(NativePipelineState.IDLE), lateJoiner.states)
    }
}
