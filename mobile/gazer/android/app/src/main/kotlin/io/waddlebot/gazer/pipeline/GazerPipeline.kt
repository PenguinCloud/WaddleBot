package io.waddlebot.gazer.pipeline

import com.pedro.common.ConnectChecker
import com.pedro.encoder.input.sources.audio.AudioSource
import com.pedro.encoder.input.sources.video.VideoSource
import com.pedro.library.util.BitrateAdapter
import io.waddlebot.gazer.pigeon.GazerErrorCode
import io.waddlebot.gazer.pigeon.NativePipelineState
import io.waddlebot.gazer.pigeon.OutputOrientation
import io.waddlebot.gazer.pigeon.PrepareResult
import io.waddlebot.gazer.pigeon.StreamConfig
import io.waddlebot.gazer.pigeon.StreamTarget
import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory

/**
 * Owns the native streaming state machine: builds sources and a StreamEngine from a
 * StreamConfig, drives RootEncoder's ConnectChecker callbacks into Pigeon
 * NativePipelineState/GazerErrorCode events, and wires BitrateAdapter only when the config asks
 * for adaptive bitrate. Every decision beyond "is this config well-formed" belongs to Dart
 * (ReconnectPolicy, source selection) - this class only reports facts and executes commands.
 */
class GazerPipeline(
    private val engineFactory: (ConnectChecker, VideoSource, AudioSource) -> StreamEngine,
    private val videoSources: VideoSourceFactory,
    private val audioSources: AudioSourceFactory,
    private val listener: PipelineListener,
    private val statsSampler: StatsSampler,
) : ConnectChecker {
    private companion object {
        const val CONGESTION_THRESHOLD_PERCENT = 20f
        const val MIN_BITRATE_KBPS = 500
        const val MAX_BITRATE_KBPS = 5000
        const val AUDIO_SAMPLE_RATE = 48000
    }

    var state: NativePipelineState = NativePipelineState.IDLE
        private set

    private var engine: StreamEngine? = null
    private var bitrateAdapter: BitrateAdapter? = null
    private var adaptiveBitrate = false

    /**
     * Validates [config], builds the video/audio sources and a fresh StreamEngine, and
     * prepares both the video and audio pipelines. Returns a failed PrepareResult (never
     * throws) if the config is out of range or RootEncoder rejects it.
     */
    fun prepare(config: StreamConfig): PrepareResult {
        val validationError = validate(config)
        if (validationError != null) {
            transitionToError(GazerErrorCode.ENCODER_FAILED, validationError)
            return PrepareResult(ok = false, error = GazerErrorCode.ENCODER_FAILED, detail = validationError)
        }

        state = NativePipelineState.PREPARING
        listener.onState(NativePipelineState.PREPARING)

        val videoSource = videoSources.create(config.videoDeviceId)
        val audioSource = audioSources.create(config.audioDeviceId)
        val newEngine = engineFactory(this, videoSource, audioSource)

        val rotation = if (config.orientation == OutputOrientation.PORTRAIT) 90 else 0
        val videoOk =
            runCatching {
                newEngine.prepareVideo(
                    width = config.width.toInt(),
                    height = config.height.toInt(),
                    bitrateBps = (config.videoBitrateKbps * 1000).toInt(),
                    fps = config.fps.toInt(),
                    rotation = rotation,
                )
            }.getOrElse { false }
        if (!videoOk) {
            newEngine.release()
            val detail = "prepareVideo failed for ${config.width}x${config.height}@${config.fps}"
            transitionToError(GazerErrorCode.ENCODER_FAILED, detail)
            return PrepareResult(ok = false, error = GazerErrorCode.ENCODER_FAILED, detail = detail)
        }

        val audioOk =
            runCatching {
                newEngine.prepareAudio(
                    sampleRate = AUDIO_SAMPLE_RATE,
                    stereo = true,
                    bitrateBps = (config.audioBitrateKbps * 1000).toInt(),
                )
            }.getOrElse { false }
        if (!audioOk) {
            newEngine.release()
            val detail = "prepareAudio failed for ${config.audioBitrateKbps}kbps"
            transitionToError(GazerErrorCode.AUDIO_SOURCE_FAILED, detail)
            return PrepareResult(ok = false, error = GazerErrorCode.AUDIO_SOURCE_FAILED, detail = detail)
        }

        newEngine.setReTries(0)
        adaptiveBitrate = config.adaptiveBitrate
        bitrateAdapter =
            if (config.adaptiveBitrate) {
                // VERIFIED (RootEncoder 2.8.1): BitrateAdapter.adaptBitrate only invokes the
                // listener once maxBitrate != 0 (guard in getBitrateAdapted) and its internal
                // sample counter reaches 5 - setMaxBitrate is required here or adaptive bitrate
                // would silently never adapt regardless of how many onNewBitrate ticks arrive.
                BitrateAdapter { adapted -> newEngine.setVideoBitrateOnFly(adapted) }.apply {
                    setMaxBitrate((config.videoBitrateKbps * 1000).toInt())
                }
            } else {
                null
            }
        engine = newEngine
        state = NativePipelineState.READY
        listener.onState(NativePipelineState.READY)
        return PrepareResult(
            ok = true,
            negotiatedWidth = config.width,
            negotiatedHeight = config.height,
            negotiatedFps = config.fps,
            negotiatedFormat = "H264/AAC",
        )
    }

    /** Starts streaming to [target]; only valid from state=READY, otherwise reports GazerErrorCode.UNKNOWN. */
    fun start(target: StreamTarget) {
        val currentEngine = engine
        if (state != NativePipelineState.READY || currentEngine == null) {
            transitionToError(GazerErrorCode.UNKNOWN, "start() called from state=$state")
            return
        }
        currentEngine.setAuthorization(target.username, target.password)
        state = NativePipelineState.CONNECTING
        listener.onState(NativePipelineState.CONNECTING)
        statsSampler.start()
        currentEngine.startStream(target.url)
    }

    /** Stops streaming from any state, releasing the engine and returning to idle. */
    fun stop() {
        state = NativePipelineState.STOPPING
        listener.onState(NativePipelineState.STOPPING)
        statsSampler.stop()
        val currentEngine = engine
        if (currentEngine != null) {
            runCatching { currentEngine.stopStream() }
            runCatching { currentEngine.release() }
        }
        engine = null
        bitrateAdapter = null
        state = NativePipelineState.IDLE
        listener.onState(NativePipelineState.IDLE)
    }

    /** Sets the live video bitrate, clamped to the supported 500..5000 kbps range. */
    fun setVideoBitrate(kbps: Int) {
        val clamped = kbps.coerceIn(MIN_BITRATE_KBPS, MAX_BITRATE_KBPS)
        engine?.setVideoBitrateOnFly(clamped * 1000)
    }

    private fun validate(config: StreamConfig): String? {
        if (config.width <= 0 || config.height <= 0) return "width/height must be positive"
        if (config.width % 2 != 0L || config.height % 2 != 0L) return "width/height must be divisible by 2"
        if (config.fps !in 1L..120L) return "fps out of range: ${config.fps}"
        if (config.videoBitrateKbps <= 0) return "videoBitrateKbps must be positive"
        if (config.audioBitrateKbps <= 0) return "audioBitrateKbps must be positive"
        return null
    }

    private fun transitionToError(
        error: GazerErrorCode,
        detail: String?,
    ) {
        state = NativePipelineState.ERROR
        listener.onState(NativePipelineState.ERROR, error, detail)
    }

    // ConnectChecker (RootEncoder callbacks) - see ErrorMapper for reason-string classification.

    override fun onConnectionStarted(url: String) {
        state = NativePipelineState.CONNECTING
        listener.onState(NativePipelineState.CONNECTING)
    }

    override fun onConnectionSuccess() {
        state = NativePipelineState.STREAMING
        listener.onState(NativePipelineState.STREAMING)
    }

    override fun onConnectionFailed(reason: String) {
        statsSampler.stop()
        transitionToError(ErrorMapper.fromReason(reason), reason)
    }

    override fun onDisconnect() {
        statsSampler.stop()
        if (state == NativePipelineState.STREAMING) {
            transitionToError(GazerErrorCode.RTMP_DISCONNECTED, "RootEncoder onDisconnect while streaming")
        } else {
            state = NativePipelineState.IDLE
            listener.onState(NativePipelineState.IDLE)
        }
    }

    override fun onAuthError() {
        listener.onAuthResult(false)
        transitionToError(GazerErrorCode.RTMP_AUTH_FAILED, "RootEncoder onAuthError")
    }

    override fun onAuthSuccess() {
        listener.onAuthResult(true)
    }

    override fun onNewBitrate(bitrate: Long) {
        statsSampler.onBitrate(bitrate)
        if (adaptiveBitrate) {
            val currentEngine = engine ?: return
            bitrateAdapter?.adaptBitrate(bitrate, currentEngine.hasCongestion(CONGESTION_THRESHOLD_PERCENT))
        }
    }
}
