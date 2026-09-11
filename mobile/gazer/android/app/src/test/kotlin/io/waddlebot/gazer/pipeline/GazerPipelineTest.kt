package io.waddlebot.gazer.pipeline

import com.pedro.encoder.input.sources.audio.AudioSource
import com.pedro.encoder.input.sources.video.VideoSource
import io.mockk.clearMocks
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import io.waddlebot.gazer.pigeon.GazerErrorCode
import io.waddlebot.gazer.pigeon.NativePipelineState
import io.waddlebot.gazer.pigeon.OutputOrientation
import io.waddlebot.gazer.pigeon.StreamConfig
import io.waddlebot.gazer.pigeon.StreamTarget
import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

class GazerPipelineTest {
    private lateinit var engine: StreamEngine
    private lateinit var videoSources: VideoSourceFactory
    private lateinit var audioSources: AudioSourceFactory
    private lateinit var listener: PipelineListener
    private lateinit var statsSampler: StatsSampler
    private lateinit var pipeline: GazerPipeline

    private val validConfig =
        StreamConfig(
            videoDeviceId = "camera:back",
            audioDeviceId = "audio:mic",
            width = 1280L,
            height = 720L,
            fps = 30L,
            videoBitrateKbps = 2000L,
            adaptiveBitrate = false,
            audioBitrateKbps = 128L,
            orientation = OutputOrientation.LANDSCAPE,
        )

    @BeforeEach
    fun setUp() {
        engine = mockk(relaxed = true)
        every { engine.prepareVideo(any(), any(), any(), any(), any()) } returns true
        every { engine.prepareAudio(any(), any(), any()) } returns true
        every { engine.hasCongestion(20f) } returns false
        videoSources = mockk(relaxed = true)
        every { videoSources.create(any()) } returns mockk<VideoSource>(relaxed = true)
        audioSources = mockk(relaxed = true)
        every { audioSources.create(any()) } returns mockk<AudioSource>(relaxed = true)
        listener = mockk(relaxed = true)
        statsSampler = mockk(relaxed = true)
        pipeline =
            GazerPipeline(
                engineFactory = { _, _, _ -> engine },
                videoSources = videoSources,
                audioSources = audioSources,
                listener = listener,
                statsSampler = statsSampler,
            )
    }

    @Test
    fun `happy path from prepare through start to streaming`() {
        val result = pipeline.prepare(validConfig)
        assertTrue(result.ok)
        assertEquals(NativePipelineState.READY, pipeline.state)

        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        assertEquals(NativePipelineState.CONNECTING, pipeline.state)

        pipeline.onConnectionSuccess()
        assertEquals(NativePipelineState.STREAMING, pipeline.state)
        verify { listener.onState(NativePipelineState.STREAMING) }
    }

    @Test
    fun `connect failed maps the reason to a GazerErrorCode, reports it, and releases the engine`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

        pipeline.onConnectionFailed("Connection timeout")

        assertEquals(NativePipelineState.ERROR, pipeline.state)
        verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_CONNECT_FAILED, "Connection timeout") }
        verify(exactly = 1) { engine.release() }
    }

    @Test
    fun `disconnect while streaming reports rtmpDisconnected and releases the engine`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        pipeline.onConnectionSuccess()

        pipeline.onDisconnect()

        assertEquals(NativePipelineState.ERROR, pipeline.state)
        verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_DISCONNECTED, any()) }
        verify(exactly = 1) { engine.release() }
    }

    @Test
    fun `disconnect while connecting goes back to idle`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

        pipeline.onDisconnect()

        assertEquals(NativePipelineState.IDLE, pipeline.state)
        verify { listener.onState(NativePipelineState.IDLE) }
    }

    @Test
    fun `the trailing disconnect after a failed connect keeps the error and never reports idle`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        pipeline.onConnectionFailed("Connection refused")
        clearMocks(listener, answers = false)

        // RootEncoder always follows a terminal onConnectionFailed with onDisconnect as it tears
        // the socket down. Reporting IDLE for it overwrites the failure Dart has already turned
        // into ReconnectingState: the status chip drops to "Idle" mid-reconnect and the Stop
        // button disappears, leaving no way to cancel the retry loop.
        pipeline.onDisconnect()

        assertEquals(NativePipelineState.ERROR, pipeline.state)
        verify(exactly = 0) { listener.onState(NativePipelineState.IDLE) }
    }

    @Test
    fun `auth error reports rtmpAuthFailed, onAuthResult false, stops sampling, and releases the engine`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

        pipeline.onAuthError()

        verify { listener.onAuthResult(false) }
        verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.RTMP_AUTH_FAILED, any()) }
        verify { statsSampler.stop() }
        verify(exactly = 1) { engine.release() }
    }

    @Test
    fun `auth success reports onAuthResult true`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

        pipeline.onAuthSuccess()

        verify { listener.onAuthResult(true) }
    }

    @Test
    fun `setReTries(0) is always called after a successful prepare`() {
        pipeline.prepare(validConfig)

        verify { engine.setReTries(0) }
    }

    @Test
    fun `adaptive bitrate on invokes setVideoBitrateOnFly via BitrateAdapter on new bitrate`() {
        pipeline.prepare(validConfig.copy(adaptiveBitrate = true))
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        pipeline.onConnectionSuccess()

        // VERIFIED (RootEncoder 2.8.1 BitrateAdapter): the listener only fires once its
        // internal sample counter reaches 5 - a single onNewBitrate tick is not enough with
        // the real BitrateAdapter, so this test drives the real accumulation threshold.
        repeat(5) { pipeline.onNewBitrate(1_500_000L) }

        verify { engine.setVideoBitrateOnFly(any()) }
    }

    @Test
    fun `adaptive bitrate off never calls setVideoBitrateOnFly from onNewBitrate`() {
        pipeline.prepare(validConfig.copy(adaptiveBitrate = false))
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        pipeline.onConnectionSuccess()

        pipeline.onNewBitrate(1_500_000L)

        verify(exactly = 0) { engine.setVideoBitrateOnFly(any()) }
    }

    @Test
    fun `prepare with an invalid config returns a failed PrepareResult`() {
        val result = pipeline.prepare(validConfig.copy(width = 0L))

        assertFalse(result.ok)
        assertEquals(GazerErrorCode.ENCODER_FAILED, result.error)
    }

    @Test
    fun `prepareAudio failure returns audioSourceFailed and releases the engine`() {
        every { engine.prepareVideo(any(), any(), any(), any(), any()) } returns true
        every { engine.prepareAudio(any(), any(), any()) } returns false

        val result = pipeline.prepare(validConfig)

        assertFalse(result.ok)
        assertEquals(GazerErrorCode.AUDIO_SOURCE_FAILED, result.error)
        verify(exactly = 1) { engine.release() }
    }

    @Test
    fun `prepare still returns a failed result even if release throws during video-failure cleanup`() {
        every { engine.prepareVideo(any(), any(), any(), any(), any()) } returns false
        every { engine.release() } throws RuntimeException("boom")

        val result = pipeline.prepare(validConfig)

        assertFalse(result.ok)
        assertEquals(GazerErrorCode.ENCODER_FAILED, result.error)
    }

    @Test
    fun `prepare after an error path releases the previous engine and builds a fresh one`() {
        val engine2 = mockk<StreamEngine>(relaxed = true)
        every { engine2.prepareVideo(any(), any(), any(), any(), any()) } returns true
        every { engine2.prepareAudio(any(), any(), any()) } returns true
        every { engine2.hasCongestion(20f) } returns false
        val engines = listOf(engine, engine2).iterator()
        pipeline =
            GazerPipeline(
                engineFactory = { _, _, _ -> engines.next() },
                videoSources = videoSources,
                audioSources = audioSources,
                listener = listener,
                statsSampler = statsSampler,
            )

        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        pipeline.onConnectionFailed("Connection timeout")

        verify(exactly = 1) { engine.release() }

        val result = pipeline.prepare(validConfig)

        assertTrue(result.ok)
        verify(exactly = 0) { engine2.release() }
    }

    @Test
    fun `stop's blocked engine call does not hold the lock - a concurrent onDisconnect completes first`() {
        val stopStreamEnteredLatch = CountDownLatch(1)
        val proceedLatch = CountDownLatch(1)
        every { engine.stopStream() } answers {
            stopStreamEnteredLatch.countDown()
            proceedLatch.await(5, TimeUnit.SECONDS)
            true
        }
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        pipeline.onConnectionSuccess()

        val stopError = AtomicReference<Throwable?>()
        val stopThread =
            Thread {
                try {
                    pipeline.stop()
                } catch (t: Throwable) {
                    stopError.set(t)
                }
            }
        stopThread.start()
        // stop() has already snapshotted+cleared the engine field and released the lock by the
        // time it calls the (now-blocked) engine.stopStream() - a concurrent onDisconnect() must
        // therefore be able to acquire the lock and complete immediately, proving no monitor is
        // held across the engine call.
        assertTrue(stopStreamEnteredLatch.await(5, TimeUnit.SECONDS))

        val disconnectCompleted = CountDownLatch(1)
        val disconnectError = AtomicReference<Throwable?>()
        val disconnectThread =
            Thread {
                try {
                    pipeline.onDisconnect()
                } catch (t: Throwable) {
                    disconnectError.set(t)
                } finally {
                    disconnectCompleted.countDown()
                }
            }
        disconnectThread.start()

        assertTrue(
            disconnectCompleted.await(2, TimeUnit.SECONDS),
            "onDisconnect() blocked - the lock was held across engine.stopStream()",
        )

        proceedLatch.countDown()
        stopThread.join(5_000)
        disconnectThread.join(5_000)

        assertNull(stopError.get())
        assertNull(disconnectError.get())
    }

    @Test
    fun `a listener that re-enters the pipeline synchronously from onState does not deadlock`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        every { listener.onState(NativePipelineState.ERROR, any(), any()) } answers {
            pipeline.stop()
        }

        pipeline.onConnectionFailed("Connection timeout")

        assertEquals(NativePipelineState.IDLE, pipeline.state)
    }

    @Test
    fun `start from the wrong state reports onState error unknown`() {
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))

        verify { listener.onState(NativePipelineState.ERROR, GazerErrorCode.UNKNOWN, any()) }
    }

    @Test
    fun `stop from any state returns to idle via stopping`() {
        pipeline.prepare(validConfig)
        pipeline.start(StreamTarget(url = "rtmp://example.com/live/key"))
        pipeline.onConnectionSuccess()

        pipeline.stop()

        assertEquals(NativePipelineState.IDLE, pipeline.state)
        verify { listener.onState(NativePipelineState.STOPPING) }
        verify { listener.onState(NativePipelineState.IDLE) }
        verify { engine.stopStream() }
        verify { engine.release() }
    }

    @Test
    fun `onConnectionStarted reports connecting`() {
        pipeline.prepare(validConfig)

        pipeline.onConnectionStarted("rtmp://example.com/live/key")

        assertEquals(NativePipelineState.CONNECTING, pipeline.state)
    }

    @Test
    fun `setVideoBitrate clamps to the 500 to 5000 kbps range`() {
        pipeline.prepare(validConfig)

        pipeline.setVideoBitrate(100)
        verify { engine.setVideoBitrateOnFly(500_000) }

        pipeline.setVideoBitrate(9000)
        verify { engine.setVideoBitrateOnFly(5_000_000) }
    }
}
