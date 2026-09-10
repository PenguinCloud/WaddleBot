package io.waddlebot.gazer.pipeline

import android.content.Context
import com.pedro.common.ConnectChecker
import com.pedro.encoder.input.sources.audio.AudioSource
import com.pedro.encoder.input.sources.video.VideoSource
import com.pedro.library.generic.GenericStream

/**
 * Bridge between GazerPipeline and whatever RTMP/H.264 implementation backs it. Exists so
 * GazerPipeline's state machine and tests never touch RootEncoder types directly - only this
 * narrow surface, verified against RootEncoder 2.8.1's StreamBase and GenericStreamClient.
 */
interface StreamEngine {
    fun prepareVideo(
        width: Int,
        height: Int,
        bitrateBps: Int,
        fps: Int,
        rotation: Int,
    ): Boolean

    fun prepareAudio(
        sampleRate: Int,
        stereo: Boolean,
        bitrateBps: Int,
    ): Boolean

    fun startStream(url: String)

    fun stopStream(): Boolean

    fun setVideoBitrateOnFly(bitrateBps: Int)

    fun setAuthorization(
        user: String?,
        password: String?,
    )

    fun setReTries(n: Int)

    fun setTlsHostVerification(enabled: Boolean)

    fun sentVideoFrames(): Long

    fun droppedVideoFrames(): Long

    fun hasCongestion(percentUsed: Float): Boolean

    fun release()
}

/**
 * Wraps RootEncoder's GenericStream (Camera2/Mic -> MediaCodec H.264/AAC -> RTMP/RTMPS) behind
 * StreamEngine. Deliberately thin: every method is a 1:1 forward to a verified RootEncoder 2.8.1
 * API, so GazerPipelineTest exercises this class only indirectly via a fake StreamEngine -
 * RootEncoderEngine itself is exercised by the instrumented StreamServiceTest in Task 20, the
 * only place a real Camera2/MediaCodec/socket stack can run.
 */
class RootEncoderEngine(
    context: Context,
    connectChecker: ConnectChecker,
    videoSource: VideoSource,
    audioSource: AudioSource,
) : StreamEngine {
    private val stream = GenericStream(context, connectChecker, videoSource, audioSource)

    override fun prepareVideo(
        width: Int,
        height: Int,
        bitrateBps: Int,
        fps: Int,
        rotation: Int,
    ): Boolean = stream.prepareVideo(width, height, bitrateBps, fps, rotation = rotation)

    override fun prepareAudio(
        sampleRate: Int,
        stereo: Boolean,
        bitrateBps: Int,
    ): Boolean = stream.prepareAudio(sampleRate, stereo, bitrateBps)

    override fun startStream(url: String) {
        stream.startStream(url)
    }

    override fun stopStream(): Boolean = stream.stopStream()

    override fun setVideoBitrateOnFly(bitrateBps: Int) {
        stream.setVideoBitrateOnFly(bitrateBps)
    }

    override fun setAuthorization(
        user: String?,
        password: String?,
    ) {
        stream.getStreamClient().setAuthorization(user, password)
    }

    override fun setReTries(n: Int) {
        stream.getStreamClient().setReTries(n)
    }

    /**
     * VERIFIED GAP (RootEncoder 2.8.1): `GenericStreamClient` — the type returned by
     * `GenericStream.getStreamClient()` — does not declare `setTlsHostVerification`; only the
     * protocol-specific `RtmpStreamClient` does, and `GenericStreamClient` does not expose its
     * wrapped `RtmpStreamClient`. [enabled] is therefore accepted but otherwise unused;
     * `addCertificates(null)` (system trust) is the closest control available on the generic
     * client, so this override is a documented no-op beyond that — the [StreamEngine] interface
     * keeps the method (it is part of the shared contract every engine implements), only this
     * RootEncoder-backed implementation cannot honor it fully in 2.8.1.
     */
    override fun setTlsHostVerification(enabled: Boolean) {
        stream.getStreamClient().addCertificates(null)
    }

    override fun sentVideoFrames(): Long = stream.getStreamClient().getSentVideoFrames()

    override fun droppedVideoFrames(): Long = stream.getStreamClient().getDroppedVideoFrames()

    override fun hasCongestion(percentUsed: Float): Boolean = stream.getStreamClient().hasCongestion(percentUsed)

    override fun release() {
        stream.release()
    }
}
