package io.waddlebot.gazer

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.ServiceTestRule
import io.waddlebot.gazer.pipeline.StreamService
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Instrumented lifecycle test: StreamService must post its foreground notification on start and
 * remove it cleanly on stop. Cannot run on the JVM unit-test target since it needs a real
 * NotificationManager and Android service lifecycle - this is also RootEncoderEngine's only
 * coverage, since it can't run outside a real Camera2/MediaCodec-capable device or emulator.
 */
@RunWith(AndroidJUnit4::class)
class StreamServiceTest {
    @get:Rule
    val serviceRule = ServiceTestRule()

    private val context: Context = ApplicationProvider.getApplicationContext()
    private val notificationManager: NotificationManager =
        context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    @Test
    fun startPostsTheForegroundNotificationAndStopRemovesIt() {
        serviceRule.startService(Intent(context, StreamService::class.java))

        val hasNotification =
            pollUntil(timeoutMs = 5000) {
                notificationManager.activeNotifications.any { it.packageName == context.packageName }
            }
        assertTrue("expected an active notification after start", hasNotification)

        context.stopService(Intent(context, StreamService::class.java))

        val notificationGone =
            pollUntil(timeoutMs = 5000) {
                notificationManager.activeNotifications.none { it.packageName == context.packageName }
            }
        assertTrue("expected the notification to be removed after stop", notificationGone)
    }

    private fun pollUntil(
        timeoutMs: Long,
        intervalMs: Long = 100,
        condition: () -> Boolean,
    ): Boolean {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (condition()) return true
            Thread.sleep(intervalMs)
        }
        return condition()
    }
}
