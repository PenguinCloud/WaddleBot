package io.waddlebot.gazer.pipeline.sources

import com.pedro.encoder.Frame
import com.pedro.encoder.input.audio.GetMicrophoneData
import com.pedro.encoder.input.sources.audio.AudioSource
import com.pedro.encoder.input.sources.audio.MicrophoneSource
import io.waddlebot.gazer.pigeon.AudioDevice
import io.waddlebot.gazer.pigeon.AudioDeviceKind
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Lists and creates RootEncoder [AudioSource]s for M1: phone mic or synthesized silence. USB
 * audio is out of scope until M2.
 */
class AudioSourceFactory {
    /** Lists the mic and silence audio devices - both always available. */
    fun list(): List<AudioDevice> =
        listOf(
            AudioDevice(id = "audio:mic", kind = AudioDeviceKind.MIC, name = "Phone microphone"),
            AudioDevice(id = "audio:silence", kind = AudioDeviceKind.SILENCE, name = "Silence"),
        )

    /** Builds the [AudioSource] for [deviceId]. */
    fun create(deviceId: String): AudioSource =
        when (deviceId) {
            "audio:mic" -> MicrophoneSource()
            "audio:silence" -> SilenceAudioSource()
            else -> throw IllegalArgumentException("Unknown audio device id: $deviceId")
        }
}

/**
 * [AudioSource] that feeds zeroed PCM16 frames at the configured sample rate instead of reading
 * a microphone - selected by the user for streams that should carry no live audio. Runs its own
 * daemon thread so it behaves like every other AudioSource: start() returns immediately and
 * frames arrive asynchronously via [GetMicrophoneData].
 */
class SilenceAudioSource : AudioSource() {
    private companion object {
        const val CHUNK_MILLIS = 20L
    }

    private val running = AtomicBoolean(false)
    private var thread: Thread? = null

    override fun create(
        sampleRate: Int,
        isStereo: Boolean,
        echoCanceler: Boolean,
        noiseSuppressor: Boolean,
    ): Boolean = true

    override fun start(getMicrophoneData: GetMicrophoneData) {
        this.getMicrophoneData = getMicrophoneData
        if (isRunning()) return
        running.set(true)
        val channels = if (isStereo) 2 else 1
        val samplesPerChunk = (sampleRate * CHUNK_MILLIS / 1000L).toInt().coerceAtLeast(1)
        val bufferSize = samplesPerChunk * channels * 2 // PCM16 = 2 bytes/sample
        val silence = ByteArray(bufferSize)
        val sink = getMicrophoneData
        thread =
            Thread({
                while (running.get()) {
                    sink.inputPCMData(Frame(silence, 0, silence.size, System.nanoTime() / 1000))
                    try {
                        Thread.sleep(CHUNK_MILLIS)
                    } catch (_: InterruptedException) {
                        return@Thread
                    }
                }
            }, "gazer-silence-audio").apply {
                isDaemon = true
                start()
            }
    }

    override fun stop() {
        running.set(false)
        thread?.interrupt()
        thread?.join(CHUNK_MILLIS * 2)
        thread = null
    }

    override fun isRunning(): Boolean = running.get()

    override fun release() = Unit
}
