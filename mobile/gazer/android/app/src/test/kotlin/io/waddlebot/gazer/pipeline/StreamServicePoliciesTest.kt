package io.waddlebot.gazer.pipeline

import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import io.mockk.mockk
import io.mockk.verify
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

/**
 * foregroundServiceType/isStopAction/notification-building are the pure decision points and
 * Android-API-call wrappers StreamService's onCreate/onStartCommand/stopReceiver delegate to -
 * each takes its Android dependency as a plain parameter (SDK int, NotificationManager, Context)
 * instead of reading Build.VERSION.SDK_INT or `this` directly, so they are testable with mockk
 * instead of needing Robolectric/instrumentation.
 */
class StreamServicePoliciesTest {
    @Test
    fun `foregroundServiceType is null below Android Q`() {
        assertNull(foregroundServiceType(Build.VERSION_CODES.P))
    }

    @Test
    fun `foregroundServiceType combines camera and microphone from Android Q onward`() {
        val expected = ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        assertEquals(expected, foregroundServiceType(Build.VERSION_CODES.Q))
    }

    @Test
    fun `isStopAction is true only for StreamService's ACTION_STOP`() {
        assertTrue(isStopAction(StreamService.ACTION_STOP))
        assertFalse(isStopAction("some.other.action"))
        assertFalse(isStopAction(null))
    }

    @Test
    fun `buildNotificationChannel constructs without throwing`() {
        // NotificationChannel's own getters (id/name/importance) are stubbed to return default
        // values under the JVM unit-test android.jar (no Robolectric here) regardless of what the
        // constructor was given, so this only asserts construction succeeds - the real values are
        // exercised on a device by the instrumented StreamServiceTest.
        assertNotNull(buildNotificationChannel())
    }

    @Test
    fun `registerNotificationChannel registers the built channel with the manager`() {
        val manager = mockk<NotificationManager>(relaxed = true)

        registerNotificationChannel(manager)

        verify { manager.createNotificationChannel(any()) }
    }

    @Test
    fun `buildStopPendingIntent does not throw against a mocked context`() {
        val context = mockk<Context>(relaxed = true)

        buildStopPendingIntent(context)
    }
}
