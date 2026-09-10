package io.waddlebot.gazer.pipeline

import io.mockk.every
import io.mockk.mockk
import io.waddlebot.gazer.pigeon.StatsSample
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

private class FakeTicker : Ticker {
    var scheduledTask: (() -> Unit)? = null
    var cancelled = false

    override fun schedule(
        periodMs: Long,
        task: () -> Unit,
    ): TickerHandle {
        scheduledTask = task
        return object : TickerHandle {
            override fun cancel() {
                cancelled = true
            }
        }
    }

    fun fireTick() = scheduledTask?.invoke()
}

class StatsSamplerTest {
    @Test
    fun `computes fps from the sentVideoFrames delta between ticks`() {
        val engine = mockk<StreamEngine>(relaxed = true)
        every { engine.sentVideoFrames() } returnsMany listOf(30L, 60L)
        every { engine.droppedVideoFrames() } returns 0L
        every { engine.hasCongestion(20f) } returns false
        val ticker = FakeTicker()
        val samples = mutableListOf<StatsSample>()
        val sampler = StatsSampler(engine = { engine }, ticker = ticker, intervalMs = 1000) { samples.add(it) }

        sampler.start()
        ticker.fireTick()
        ticker.fireTick()

        assertEquals(2, samples.size)
        assertEquals(30.0, samples[0].fps)
        assertEquals(30.0, samples[1].fps)
    }

    @Test
    fun `reports dropped frames from the engine`() {
        val engine = mockk<StreamEngine>(relaxed = true)
        every { engine.sentVideoFrames() } returns 0L
        every { engine.droppedVideoFrames() } returns 7L
        every { engine.hasCongestion(20f) } returns false
        val ticker = FakeTicker()
        val samples = mutableListOf<StatsSample>()
        val sampler = StatsSampler(engine = { engine }, ticker = ticker) { samples.add(it) }

        sampler.start()
        ticker.fireTick()

        assertEquals(7L, samples.single().droppedVideoFrames)
    }

    @Test
    fun `bitrateKbps reflects the latest onBitrate value in kbps`() {
        val engine = mockk<StreamEngine>(relaxed = true)
        every { engine.sentVideoFrames() } returns 0L
        every { engine.droppedVideoFrames() } returns 0L
        every { engine.hasCongestion(20f) } returns false
        val ticker = FakeTicker()
        val samples = mutableListOf<StatsSample>()
        val sampler = StatsSampler(engine = { engine }, ticker = ticker) { samples.add(it) }
        sampler.start()

        sampler.onBitrate(2_048_000L)
        ticker.fireTick()

        assertEquals(2048L, samples.single().bitrateKbps)
    }

    @Test
    fun `congestionPercent is 100 when the engine reports congestion else 0`() {
        val engine = mockk<StreamEngine>(relaxed = true)
        every { engine.sentVideoFrames() } returns 0L
        every { engine.droppedVideoFrames() } returns 0L
        every { engine.hasCongestion(20f) } returns true
        val ticker = FakeTicker()
        val samples = mutableListOf<StatsSample>()
        val sampler = StatsSampler(engine = { engine }, ticker = ticker) { samples.add(it) }
        sampler.start()

        ticker.fireTick()

        assertEquals(100.0, samples.single().congestionPercent)
    }

    @Test
    fun `stop cancels the ticker`() {
        val ticker = FakeTicker()
        val sampler = StatsSampler(engine = { null }, ticker = ticker) { }
        sampler.start()

        sampler.stop()

        assertEquals(true, ticker.cancelled)
    }

    @Test
    fun `tick is a no-op when the engine is not yet available`() {
        val ticker = FakeTicker()
        val samples = mutableListOf<StatsSample>()
        val sampler = StatsSampler(engine = { null }, ticker = ticker) { samples.add(it) }
        sampler.start()

        ticker.fireTick()

        assertEquals(0, samples.size)
    }
}
