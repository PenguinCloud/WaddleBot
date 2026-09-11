package io.waddlebot.gazer.pipeline

import android.content.Context
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Test

/**
 * StreamService.start/stop take Context as a plain parameter and only call through its
 * (mockable) abstract startForegroundService/stopService methods, so they are directly testable
 * without a real Android runtime.
 */
class StreamServiceCompanionTest {
    @Test
    fun `start starts the foreground service`() {
        val context = mockk<Context>(relaxed = true)

        StreamService.start(context)

        verify { context.startForegroundService(any()) }
    }

    @Test
    fun `stop stops the service`() {
        val context = mockk<Context>(relaxed = true)

        StreamService.stop(context)

        verify { context.stopService(any()) }
    }
}
