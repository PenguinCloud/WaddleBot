package io.waddlebot.gazer.pipeline

import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * StreamService's constructor and onBind() never touch Context (attachBaseContext is never
 * called here, unlike a real running Service) - only lazily-initialized/framework-lifecycle
 * methods do - so this is the one slice of StreamService itself directly exercisable on the JVM
 * unit-test target without Robolectric/instrumentation; onCreate/onStartCommand/onDestroy remain
 * covered only by the instrumented StreamServiceTest (androidTest).
 */
class StreamServiceUnitTest {
    @Test
    fun `onBind returns a StreamService LocalBinder`() {
        val service = StreamService()

        val binder = service.onBind(null)

        assertNotNull(binder)
        assertTrue(binder is StreamService.LocalBinder)
    }

    @Test
    fun `releaseWakeLock is a no-op before any wake lock is ever acquired`() {
        val service = StreamService()

        service.releaseWakeLock()
    }
}
