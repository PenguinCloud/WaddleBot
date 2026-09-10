package io.waddlebot.gazer.pipeline

import io.waddlebot.gazer.pigeon.StatsSample
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Schedules periodic StreamEngine polling. Ticking is indirected behind Ticker so
 * StatsSamplerTest/GazerPipelineTest can fire samples deterministically instead of racing a
 * real 1Hz timer.
 */
interface Ticker {
    /** Schedules [task] to run every [periodMs] ms; returns a handle to cancel it. */
    fun schedule(
        periodMs: Long,
        task: () -> Unit,
    ): TickerHandle
}

/** Cancels a scheduled [Ticker] task. */
interface TickerHandle {
    fun cancel()
}

/** Production Ticker backed by a single-thread ScheduledExecutorService. */
class ScheduledExecutorTicker(
    private val executor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor(),
) : Ticker {
    override fun schedule(
        periodMs: Long,
        task: () -> Unit,
    ): TickerHandle {
        val future: ScheduledFuture<*> = executor.scheduleAtFixedRate(task, periodMs, periodMs, TimeUnit.MILLISECONDS)
        return object : TickerHandle {
            override fun cancel() {
                future.cancel(false)
            }
        }
    }
}

/**
 * Polls a StreamEngine at [intervalMs] and emits StatsSample values via [onSample]: bitrate
 * from the most recent ConnectChecker.onNewBitrate value (fed through onBitrate), fps from the
 * delta of sentVideoFrames() between ticks, dropped frames and cumulative sent bytes from the
 * engine's counters, and congestion as 0/100 from StreamEngine.hasCongestion(20f).
 */
class StatsSampler(
    private val engine: () -> StreamEngine?,
    private val ticker: Ticker = ScheduledExecutorTicker(),
    private val intervalMs: Long = 1000,
    private val onSample: (StatsSample) -> Unit,
) {
    private companion object {
        const val CONGESTION_THRESHOLD_PERCENT = 20f
    }

    private var handle: TickerHandle? = null
    private var lastBitrateBps: Long = 0
    private var lastSentVideoFrames: Long = 0
    private var sentBytesAccumulator: Long = 0

    /** Feeds the latest ConnectChecker.onNewBitrate(bitrate) value in bits per second. */
    fun onBitrate(bps: Long) {
        lastBitrateBps = bps
    }

    /** Starts periodic sampling; call once per streaming session. */
    fun start() {
        stop()
        lastSentVideoFrames = 0
        sentBytesAccumulator = 0
        handle = ticker.schedule(intervalMs) { tick() }
    }

    /** Stops periodic sampling; safe to call repeatedly. */
    fun stop() {
        handle?.cancel()
        handle = null
    }

    /** Computes and emits one StatsSample from the current engine state; exposed so tests can call ticks manually. */
    fun tick() {
        val current = engine() ?: return
        val sentVideoFrames = current.sentVideoFrames()
        val deltaFrames = (sentVideoFrames - lastSentVideoFrames).coerceAtLeast(0)
        lastSentVideoFrames = sentVideoFrames
        val fps = deltaFrames * 1000.0 / intervalMs
        val droppedVideoFrames = current.droppedVideoFrames()
        val bitrateKbps = lastBitrateBps / 1000
        sentBytesAccumulator += (lastBitrateBps / 8.0 * (intervalMs / 1000.0)).toLong()
        val congestionPercent = if (current.hasCongestion(CONGESTION_THRESHOLD_PERCENT)) 100.0 else 0.0
        onSample(
            StatsSample(
                bitrateKbps = bitrateKbps,
                fps = fps,
                droppedVideoFrames = droppedVideoFrames,
                sentBytes = sentBytesAccumulator,
                congestionPercent = congestionPercent,
            ),
        )
    }
}
