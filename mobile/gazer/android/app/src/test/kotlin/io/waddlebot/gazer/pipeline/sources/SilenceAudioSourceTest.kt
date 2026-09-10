package io.waddlebot.gazer.pipeline.sources

import com.pedro.encoder.Frame
import com.pedro.encoder.input.audio.GetMicrophoneData
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * SilenceAudioSource must behave like any other RootEncoder AudioSource: start() returns
 * immediately and frames arrive asynchronously via GetMicrophoneData, sized for the sample
 * rate and channel count passed to init().
 */
class SilenceAudioSourceTest {
    @Test
    fun `delivers zeroed PCM16 frames of the expected byte length within 200ms`() {
        val sampleRate = 48000
        val isStereo = true
        val expectedBytes = (sampleRate * 20 / 1000) * 2 * 2 // 20ms chunk * stereo * PCM16

        val received = CopyOnWriteArrayList<Frame>()
        val latch = CountDownLatch(1)
        val sink =
            object : GetMicrophoneData {
                override fun inputPCMData(frame: Frame) {
                    received.add(frame)
                    latch.countDown()
                }
            }

        val source = SilenceAudioSource()
        assertTrue(source.init(sampleRate, isStereo, echoCanceler = false, noiseSuppressor = false))
        source.start(sink)

        assertTrue(latch.await(200, TimeUnit.MILLISECONDS), "no frame delivered within 200ms")
        assertEquals(expectedBytes, received.first().size)
        assertTrue(received.first().buffer.all { it == 0.toByte() })

        source.stop()
        assertFalse(source.isRunning())
    }

    @Test
    fun `isRunning reflects start and stop`() {
        val source = SilenceAudioSource()
        source.init(48000, isStereo = false, echoCanceler = false, noiseSuppressor = false)
        assertFalse(source.isRunning())

        source.start(
            object : GetMicrophoneData {
                override fun inputPCMData(frame: Frame) = Unit
            },
        )
        assertTrue(source.isRunning())

        source.stop()
        assertFalse(source.isRunning())
    }
}
