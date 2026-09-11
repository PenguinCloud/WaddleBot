package io.waddlebot.gazer.pipeline

/** Thin seam over StreamService's binder so PigeonHostApiImplTest can fake the bound connection. */
interface PipelineHost {
    fun pipeline(): GazerPipeline
}
