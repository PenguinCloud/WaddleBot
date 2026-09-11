package io.waddlebot.gazer.pipeline

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.camera2.CameraManager
import android.os.Build
import io.waddlebot.gazer.pigeon.NativePipelineState
import io.waddlebot.gazer.pipeline.sources.AudioSourceFactory
import io.waddlebot.gazer.pipeline.sources.CameraManagerIds
import io.waddlebot.gazer.pipeline.sources.VideoSourceFactory

/** StreamService's persistent notification channel id, also its Android notification-tap-target identity. */
internal const val NOTIFICATION_CHANNEL_ID = "gazer.stream"
internal const val NOTIFICATION_CHANNEL_NAME = "Gazer streaming"
internal const val NOTIFICATION_ID = 1001
internal const val NOTIFICATION_TITLE = "Gazer is live"
internal const val NOTIFICATION_STOP_ACTION_LABEL = "Stop"

/**
 * Decides whether a native state transition should acquire or release StreamService's partial
 * wake lock, driving injected [acquire]/[release] actions instead of a real PowerManager. Pure
 * decision table extracted out of StreamService's Service-framework-bound PipelineListener so it
 * can be unit-tested without Robolectric/instrumentation.
 */
class WakeLockController(
    private val acquire: () -> Unit,
    private val release: () -> Unit,
) {
    /** Applies the wake-lock decision for [state]: acquire while streaming, release once idle, no-op otherwise. */
    fun onState(state: NativePipelineState) {
        when (state) {
            NativePipelineState.STREAMING -> acquire()
            NativePipelineState.IDLE -> release()
            else -> Unit
        }
    }
}

/**
 * Resolves the FOREGROUND_SERVICE_TYPE flags StreamService must declare to startForeground() on
 * [sdkInt]: the type parameter is required (and only accepted) from Android 10 (Q) onward, so
 * this returns null below that to signal the two-argument startForeground() overload instead.
 */
internal fun foregroundServiceType(sdkInt: Int): Int? =
    if (sdkInt >= Build.VERSION_CODES.Q) {
        ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
    } else {
        null
    }

/** True when [action] (a received broadcast's Intent.action) is StreamService's Stop request. */
internal fun isStopAction(action: String?): Boolean = action == StreamService.ACTION_STOP

/** Builds the (silent, low-importance) notification channel StreamService's foreground notification posts to. */
internal fun buildNotificationChannel(): NotificationChannel =
    NotificationChannel(NOTIFICATION_CHANNEL_ID, NOTIFICATION_CHANNEL_NAME, NotificationManager.IMPORTANCE_LOW)

/**
 * Registers [buildNotificationChannel] with [manager] - createNotificationChannel is
 * idempotent, so safe to call on every onCreate.
 */
internal fun registerNotificationChannel(manager: NotificationManager) {
    manager.createNotificationChannel(buildNotificationChannel())
}

/**
 * Builds the PendingIntent StreamService's Stop notification action broadcasts ACTION_STOP through
 * when tapped.
 *
 * setPackage is load-bearing, not tidiness: StreamService registers its stop receiver with
 * RECEIVER_NOT_EXPORTED (required from API 33), and an implicit broadcast - one carrying neither a
 * package nor a component - is not delivered to a non-exported receiver. Without it the Stop action
 * on the ongoing notification silently does nothing on Android 14+, leaving the stream running with
 * no way to end it from the notification shade. Proven by StreamServiceTest, which broadcasts the
 * same way.
 */
internal fun buildStopPendingIntent(context: Context): PendingIntent? =
    PendingIntent.getBroadcast(
        context,
        0,
        Intent(StreamService.ACTION_STOP).setPackage(context.packageName),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

/**
 * Builds the GazerPipeline StreamService binds out - the RootEncoder engine factory, video/audio
 * source factories, and the StatsSampler's live-engine lookup - from [context] and [listenerRelay]
 * alone (no StreamService instance needed), so this wiring is unit-testable with a mocked Context
 * the same way GazerFlutterBindings.install is.
 */
internal fun buildStreamPipeline(
    context: Context,
    listenerRelay: RelayPipelineListener,
): GazerPipeline {
    var activeEngine: StreamEngine? = null
    val statsSampler = StatsSampler(engine = { activeEngine }) { sample -> listenerRelay.onStats(sample) }
    val cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
    return GazerPipeline(
        engineFactory = { checker, video, audio ->
            RootEncoderEngine(context, checker, video, audio).also { activeEngine = it }
        },
        videoSources = VideoSourceFactory(context, CameraManagerIds(cameraManager)),
        audioSources = AudioSourceFactory(),
        listener = listenerRelay,
        statsSampler = statsSampler,
    )
}
