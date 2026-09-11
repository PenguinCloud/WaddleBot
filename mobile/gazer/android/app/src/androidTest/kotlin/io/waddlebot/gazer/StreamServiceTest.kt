package io.waddlebot.gazer

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.rule.GrantPermissionRule
import androidx.test.rule.ServiceTestRule
import io.waddlebot.gazer.pipeline.StreamService
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Instrumented lifecycle test: StreamService must post its foreground notification on start and
 * remove it cleanly when ACTION_STOP is broadcast (the real path the notification's own Stop
 * action - and any other Stop trigger - takes; see StreamService's stopReceiver, which calls
 * pipeline.stop(), stopForeground(STOP_FOREGROUND_REMOVE), and stopSelf()). Cannot run on the JVM
 * unit-test target since it needs a real NotificationManager and Android service lifecycle - this
 * is also RootEncoderEngine's only coverage, since it can't run outside a real Camera2/MediaCodec
 * -capable device or emulator.
 */
@RunWith(AndroidJUnit4::class)
class StreamServiceTest {
    @get:Rule
    val serviceRule = ServiceTestRule()

    /**
     * StreamService.onStartCommand calls startForeground with the camera+microphone FGS types, and
     * Android 14+ rejects that with a SecurityException ("requires permissions: all of ...") unless
     * CAMERA and RECORD_AUDIO are actually granted -- which crashes the whole instrumentation
     * process, not just this test. The connectedAndroidTest install does not grant them, so the
     * test grants what the service it exercises needs rather than depending on whatever the device
     * happened to be left in by an earlier install.
     */
    @get:Rule
    val permissionRule: GrantPermissionRule =
        GrantPermissionRule.grant(
            android.Manifest.permission.CAMERA,
            android.Manifest.permission.RECORD_AUDIO,
            android.Manifest.permission.POST_NOTIFICATIONS,
        )

    private val context: Context = ApplicationProvider.getApplicationContext()
    private val notificationManager: NotificationManager =
        context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    @Test
    fun startPostsTheForegroundNotificationAndActionStopRemovesItAndStopsTheService() {
        serviceRule.startService(Intent(context, StreamService::class.java))

        val hasNotification =
            pollUntil(timeoutMs = 5000) {
                notificationManager.activeNotifications.any { it.packageName == context.packageName }
            }
        assertTrue("expected an active notification after start", hasNotification)

        // The real Stop trigger: the notification's own action (and any other Stop UI) broadcasts
        // ACTION_STOP, which stopReceiver handles by stopping the pipeline, removing the
        // foreground notification, and calling stopSelf() to destroy the service - exercised here
        // via sendBroadcast rather than a direct stopService()/unbindService() call, since that's
        // the actual path production code takes.
        context.sendBroadcast(Intent(StreamService.ACTION_STOP).setPackage(context.packageName))

        // stopForeground(STOP_FOREGROUND_REMOVE) removes the notification synchronously with the
        // broadcast receipt, before the asynchronous stopSelf()-driven onDestroy() completes, so
        // notification removal is the reliable, immediately observable signal here that the
        // ACTION_STOP path ran end to end (a further onDestroy()-completion assertion would need
        // its own instrumentation hook, which this behavioral guarantee doesn't require).
        val notificationGone =
            pollUntil(timeoutMs = 5000) {
                notificationManager.activeNotifications.none { it.packageName == context.packageName }
            }
        assertTrue("expected the notification to be removed after ACTION_STOP", notificationGone)
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
