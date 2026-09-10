package io.waddlebot.gazer.pipeline

import io.waddlebot.gazer.pigeon.GazerErrorCode
import io.waddlebot.gazer.pigeon.NativePipelineState
import io.waddlebot.gazer.pigeon.StatsSample

/**
 * Sink for GazerPipeline's native-side facts - state transitions, stats samples, and RTMP auth
 * results - so GazerPipeline never depends on Handler/Pigeon directly. PigeonHostApiImpl
 * (Task 20) implements this to post events to Dart on the main thread.
 */
interface PipelineListener {
    fun onState(
        state: NativePipelineState,
        error: GazerErrorCode? = null,
        detail: String? = null,
    )

    fun onStats(sample: StatsSample)

    fun onAuthResult(ok: Boolean)
}
