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
 *
 * Locking contract: `state`/`engine`/`bitrateAdapter`/`adaptiveBitrate` are mutated from both the
 * caller thread (prepare/start/stop/setVideoBitrate) and RootEncoder's own callback thread (the
 * ConnectChecker overrides), so every read/mutation of them is confined to a short
 * `synchronized(lock)` block. Engine calls (prepareVideo/Audio, startStream, stopStream, release,
 * setVideoBitrateOnFly, adaptBitrate) and every `PipelineListener`/`StatsSampler` call are always
 * made *after* leaving that block, never while the lock is held - RootEncoder's stopStream/release
 * can synchronously join its own internal thread, and that thread can turn around and deliver a
 * ConnectChecker callback that needs this same lock, so holding it across an engine call risks a
 * genuine deadlock. Because the lock is never held during a listener call, a `PipelineListener`
 * implementation may safely call back into this pipeline (e.g. `stop()` from within `onState`)
 * without risking deadlock or reentrant-lock surprises. `state` also carries `@Volatile` so a
 * plain read of `pipeline.state` from any thread, without going through the lock, still observes
 * the latest value.
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

    private val lock = Any()

    @Volatile
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
            emitError(GazerErrorCode.ENCODER_FAILED, validationError)
            return PrepareResult(ok = false, error = GazerErrorCode.ENCODER_FAILED, detail = validationError)
        }

        synchronized(lock) { state = NativePipelineState.PREPARING }
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
            runCatching { newEngine.release() }
            val detail = "prepareVideo failed for ${config.width}x${config.height}@${config.fps}"
            emitError(GazerErrorCode.ENCODER_FAILED, detail)
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
            runCatching { newEngine.release() }
            val detail = "prepareAudio failed for ${config.audioBitrateKbps}kbps"
            emitError(GazerErrorCode.AUDIO_SOURCE_FAILED, detail)
            return PrepareResult(ok = false, error = GazerErrorCode.AUDIO_SOURCE_FAILED, detail = detail)
        }

        newEngine.setReTries(0)
        val adaptive = config.adaptiveBitrate
        val adapter =
            if (adaptive) {
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
        synchronized(lock) {
            engine = newEngine
            bitrateAdapter = adapter
            adaptiveBitrate = adaptive
            state = NativePipelineState.READY
        }
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
        val snapshotState: NativePipelineState
        val currentEngine: StreamEngine?
        synchronized(lock) {
            snapshotState = state
            currentEngine = engine
            state =
                if (snapshotState == NativePipelineState.READY && currentEngine != null) {
                    NativePipelineState.CONNECTING
                } else {
                    NativePipelineState.ERROR
                }
        }
        val engineToUse = currentEngine
        if (snapshotState != NativePipelineState.READY || engineToUse == null) {
            listener.onState(NativePipelineState.ERROR, GazerErrorCode.UNKNOWN, "start() called from state=$snapshotState")
            return
        }
        engineToUse.setAuthorization(target.username, target.password)
        listener.onState(NativePipelineState.CONNECTING)
        statsSampler.start()
        engineToUse.startStream(target.url)
    }

    /** Stops streaming from any state, releasing the engine and returning to idle. */
    fun stop() {
        val currentEngine: StreamEngine?
        synchronized(lock) {
            currentEngine = engine
            engine = null
            bitrateAdapter = null
            state = NativePipelineState.STOPPING
        }
        listener.onState(NativePipelineState.STOPPING)
        statsSampler.stop()
        if (currentEngine != null) {
            runCatching { currentEngine.stopStream() }
            runCatching { currentEngine.release() }
        }
        synchronized(lock) { state = NativePipelineState.IDLE }
        listener.onState(NativePipelineState.IDLE)
    }

    /** Sets the live video bitrate, clamped to the supported 500..5000 kbps range. */
    fun setVideoBitrate(kbps: Int) {
        val clamped = kbps.coerceIn(MIN_BITRATE_KBPS, MAX_BITRATE_KBPS)
        val currentEngine = synchronized(lock) { engine }
        currentEngine?.setVideoBitrateOnFly(clamped * 1000)
    }

    private fun validate(config: StreamConfig): String? {
        if (config.width <= 0 || config.height <= 0) return "width/height must be positive"
        if (config.width % 2 != 0L || config.height % 2 != 0L) return "width/height must be divisible by 2"
        if (config.fps !in 1L..120L) return "fps out of range: ${config.fps}"
        if (config.videoBitrateKbps <= 0) return "videoBitrateKbps must be positive"
        if (config.audioBitrateKbps <= 0) return "audioBitrateKbps must be positive"
        return null
    }

    /** Transitions to ERROR under the lock, then notifies the listener outside it. */
    private fun emitError(
        error: GazerErrorCode,
        detail: String?,
    ) {
        synchronized(lock) { state = NativePipelineState.ERROR }
        listener.onState(NativePipelineState.ERROR, error, detail)
    }

    /**
     * Snapshots and clears the current engine under the lock while transitioning to ERROR, so the
     * caller can release()/notify outside the lock without a subsequent prepare() ever overwriting
     * a still-referenced, un-released engine. Used by the three RootEncoder callbacks that report
     * a terminal failure: onConnectionFailed, onDisconnect (streaming case), onAuthError.
     */
    private fun captureEngineForErrorRelease(): StreamEngine? {
        val captured: StreamEngine?
        synchronized(lock) {
            captured = engine
            engine = null
            bitrateAdapter = null
            state = NativePipelineState.ERROR
        }
        return captured
    }

    // ConnectChecker (RootEncoder callbacks) - see ErrorMapper for reason-string classification.
    // RootEncoder invokes these from its own internal thread(s), concurrently with caller-thread
    // prepare/start/stop/setVideoBitrate calls - see the class KDoc locking contract above.

    override fun onConnectionStarted(url: String) {
        synchronized(lock) { state = NativePipelineState.CONNECTING }
        listener.onState(NativePipelineState.CONNECTING)
    }

    override fun onConnectionSuccess() {
        synchronized(lock) { state = NativePipelineState.STREAMING }
        listener.onState(NativePipelineState.STREAMING)
    }

    override fun onConnectionFailed(reason: String) {
        val engineToRelease = captureEngineForErrorRelease()
        statsSampler.stop()
        runCatching { engineToRelease?.release() }
        listener.onState(NativePipelineState.ERROR, ErrorMapper.fromReason(reason), reason)
    }

    override fun onDisconnect() {
        val wasStreaming: Boolean
        val alreadyFailed: Boolean
        var engineToRelease: StreamEngine? = null
        synchronized(lock) {
            wasStreaming = state == NativePipelineState.STREAMING
            alreadyFailed = state == NativePipelineState.ERROR
            if (wasStreaming) {
                engineToRelease = engine
                engine = null
                bitrateAdapter = null
                state = NativePipelineState.ERROR
            } else if (!alreadyFailed) {
                state = NativePipelineState.IDLE
            }
        }
        statsSampler.stop()
        if (wasStreaming) {
            runCatching { engineToRelease?.release() }
            listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_DISCONNECTED, "RootEncoder onDisconnect while streaming")
        } else if (!alreadyFailed) {
            listener.onState(NativePipelineState.IDLE)
        }
        // alreadyFailed: RootEncoder always follows a terminal onConnectionFailed/onAuthError with
        // an onDisconnect as it tears the socket down. Reporting IDLE for that trailing callback
        // overwrites the failure the Dart side has already turned into ReconnectingState, so the
        // status chip drops back to "Idle" mid-reconnect and the Stop button - only rendered while
        // connecting/streaming/reconnecting - disappears, leaving no way to cancel the retry loop.
        // The failure was already reported by the callback that classified it; stay quiet here.
    }

    override fun onAuthError() {
        val engineToRelease = captureEngineForErrorRelease()
        statsSampler.stop()
        listener.onAuthResult(false)
        runCatching { engineToRelease?.release() }
        listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_AUTH_FAILED, "RootEncoder onAuthError")
    }

    override fun onAuthSuccess() {
        listener.onAuthResult(true)
    }

    override fun onNewBitrate(bitrate: Long) {
        statsSampler.onBitrate(bitrate)
        val shouldAdapt: Boolean
        val currentEngine: StreamEngine?
        val adapter: BitrateAdapter?
        synchronized(lock) {
            shouldAdapt = adaptiveBitrate
            currentEngine = engine
            adapter = bitrateAdapter
        }
        if (shouldAdapt && currentEngine != null) {
            adapter?.adaptBitrate(bitrate, currentEngine.hasCongestion(CONGESTION_THRESHOLD_PERCENT))
        }
    }
}
