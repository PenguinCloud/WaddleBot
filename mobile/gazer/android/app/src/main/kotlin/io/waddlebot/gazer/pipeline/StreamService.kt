package io.waddlebot.gazer.pipeline

import android.app.Notification
import android.app.NotificationManager
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import io.waddlebot.gazer.pigeon.GazerErrorCode
import io.waddlebot.gazer.pigeon.NativePipelineState
import io.waddlebot.gazer.pigeon.StatsSample
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit

/**
 * Fans PipelineListener calls out to every attached listener, so PigeonHostApiImpl can attach
 * itself after binding without ever replacing StreamService's own wake-lock-controlling
 * listener - GazerPipeline's `listener` constructor field (fixed at construction, per the
 * SHARED CONTRACT) never changes. Backed by [CopyOnWriteArrayList]: StatsSampler's own
 * ScheduledExecutorService thread delivers `onStats` here concurrently with attach/detach calls
 * that can happen on the main thread (PigeonHostApiImpl binding/unbinding), so a plain
 * MutableList would risk a ConcurrentModificationException.
 */
class RelayPipelineListener : PipelineListener {
    private val listeners = CopyOnWriteArrayList<PipelineListener>()

    fun attach(listener: PipelineListener) {
        listeners.add(listener)
    }

    fun detach(listener: PipelineListener) {
        listeners.remove(listener)
    }

    override fun onState(
        state: NativePipelineState,
        error: GazerErrorCode?,
        detail: String?,
    ) {
        listeners.forEach { it.onState(state, error, detail) }
    }

    override fun onStats(sample: StatsSample) {
        listeners.forEach { it.onStats(sample) }
    }

    override fun onAuthResult(ok: Boolean) {
        listeners.forEach { it.onAuthResult(ok) }
    }
}

/**
 * Foreground service hosting the live GazerPipeline. Owns the persistent "gazer.stream"
 * notification (with a Stop action broadcasting ACTION_STOP), a partial wake lock held only
 * while streaming, and stops the pipeline in onDestroy so a killed/removed app never leaves
 * RootEncoder running against a camera or socket.
 */
class StreamService : Service() {
    companion object {
        const val ACTION_STOP = "io.waddlebot.gazer.action.STOP"
        private const val WAKE_LOCK_TAG = "gazer:stream-service"

        /** Starts the service in the foreground; safe to call repeatedly. */
        fun start(context: Context) {
            context.startForegroundService(Intent(context, StreamService::class.java))
        }

        /** Stops the service; safe to call when not running. */
        fun stop(context: Context) {
            context.stopService(Intent(context, StreamService::class.java))
        }
    }

    /**
     * Binder exposing the live pipeline and a way to attach the bound client as a listener.
     * Takes [pipelineProvider]/[attachListener] as constructor parameters rather than being an
     * `inner class` of StreamService, so it can be constructed directly in a plain JVM unit test
     * (PigeonHostApiImplTest) without a real, Robolectric/instrumentation-backed Service instance.
     */
    class LocalBinder(
        private val pipelineProvider: () -> GazerPipeline,
        private val attachListener: (PipelineListener) -> Unit,
    ) : Binder() {
        val pipeline: GazerPipeline get() = pipelineProvider()

        fun setListener(listener: PipelineListener) {
            attachListener(listener)
        }
    }

    private val listenerRelay = RelayPipelineListener()
    private val binder = LocalBinder(pipelineProvider = { pipeline }, attachListener = { listenerRelay.attach(it) })
    private var wakeLock: PowerManager.WakeLock? = null

    private val pipeline: GazerPipeline by lazy { buildStreamPipeline(applicationContext, listenerRelay) }

    private val wakeLockController = WakeLockController(acquire = ::acquireWakeLock, release = ::releaseWakeLock)

    private val stopReceiver =
        object : BroadcastReceiver() {
            override fun onReceive(
                context: Context,
                intent: Intent,
            ) {
                // isStopAction is the only decision here (already extracted, unit-tested in
                // StreamServicePoliciesTest); the resulting teardown sequence below is fixed and
                // entirely Service-framework-bound (pipeline.stop() needs the live pipeline,
                // stopForeground()/stopSelf() need a real Service instance), so there is no
                // further pure logic to pull out of this receiver.
                if (isStopAction(intent.action)) {
                    pipeline.stop()
                    stopForeground(STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
            }
        }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        val filter = IntentFilter(ACTION_STOP)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(stopReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(stopReceiver, filter)
        }
        listenerRelay.attach(
            object : PipelineListener {
                override fun onState(
                    state: NativePipelineState,
                    error: GazerErrorCode?,
                    detail: String?,
                ) = wakeLockController.onState(state)

                override fun onStats(sample: StatsSample) = Unit

                override fun onAuthResult(ok: Boolean) = Unit
            },
        )
    }

    override fun onStartCommand(
        intent: Intent?,
        flags: Int,
        startId: Int,
    ): Int {
        val notification = buildNotification()
        val serviceType = foregroundServiceType(Build.VERSION.SDK_INT)
        if (serviceType != null) {
            startForeground(NOTIFICATION_ID, notification, serviceType)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onDestroy() {
        pipeline.stop()
        releaseWakeLock()
        runCatching { unregisterReceiver(stopReceiver) }
        super.onDestroy()
    }

    private fun createNotificationChannel() {
        registerNotificationChannel(getSystemService(NotificationManager::class.java))
    }

    private fun buildNotification(): Notification {
        val stopIntent = buildStopPendingIntent(this)
        return NotificationCompat
            .Builder(this, NOTIFICATION_CHANNEL_ID)
            .setContentTitle(NOTIFICATION_TITLE)
            .setSmallIcon(android.R.drawable.presence_video_online)
            .setOngoing(true)
            .addAction(0, NOTIFICATION_STOP_ACTION_LABEL, stopIntent)
            .build()
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock =
            powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, WAKE_LOCK_TAG).apply {
                setReferenceCounted(false)
                acquire(TimeUnit.HOURS.toMillis(4))
            }
    }

    /**
     * Test seam - `internal` (not `private`) so StreamServiceUnitTest can exercise the
     * no-wake-lock-yet no-op path without a real Context.
     */
    internal fun releaseWakeLock() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
    }
}
