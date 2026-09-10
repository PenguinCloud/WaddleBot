package io.waddlebot.gazer.pipeline.sources

import com.pedro.encoder.input.sources.audio.MicrophoneSource
import io.waddlebot.gazer.pigeon.AudioDeviceKind
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class AudioSourceFactoryTest {
    @Test
    fun `list returns mic and silence`() {
        val devices = AudioSourceFactory().list()

        assertEquals(2, devices.size)
        assertEquals("audio:mic", devices[0].id)
        assertEquals(AudioDeviceKind.MIC, devices[0].kind)
        assertEquals("audio:silence", devices[1].id)
        assertEquals(AudioDeviceKind.SILENCE, devices[1].kind)
    }

    @Test
    fun `create builds a MicrophoneSource for audio-mic`() {
        val source = AudioSourceFactory().create("audio:mic")

        assertTrue(source is MicrophoneSource)
    }

    @Test
    fun `create builds a SilenceAudioSource for audio-silence`() {
        val source = AudioSourceFactory().create("audio:silence")

        assertTrue(source is SilenceAudioSource)
    }

    @Test
    fun `create rejects an unknown device id`() {
        assertThrows(IllegalArgumentException::class.java) { AudioSourceFactory().create("audio:usb") }
    }
}
