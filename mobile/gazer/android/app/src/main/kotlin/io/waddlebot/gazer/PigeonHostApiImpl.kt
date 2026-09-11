package io.waddlebot.gazer

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import io.waddlebot.gazer.pigeon.AudioDevice
import io.waddlebot.gazer.pigeon.GazerErrorCode
import io.waddlebot.gazer.pigeon.GazerFlutterApi
import io.waddlebot.gazer.pigeon.GazerHostApi
import io.waddlebot.gazer.pigeon.NativePipelineState
import io.waddlebot.gazer.pigeon.PrepareResult
import io.waddlebot.gazer.pigeon.StateEvent
import io.waddlebot.gazer.pigeon.StatsSample
import io.waddlebot.gazer.pigeon.StreamConfig
import io.waddlebot.gazer.pigeon.StreamTarget
import io.waddlebot.gazer.pigeon.VideoDevice
import io.waddlebot.gazer.pipeline.GazerPipeline
import io.waddlebot.gazer.pipeline.PipelineHost
import io.waddlebot.gazer.pipeline.PipelineListener
import io.waddlebot.gazer.pipeline.StreamService
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

/**
 * Implements the Pigeon GazerHostApi: binds/starts StreamService on prepare(), forwards every
 * command to the bound GazerPipeline, and relays PipelineListener facts back to Dart via
 * GazerFlutterApi. Pigeon 28 generates `@async` GazerHostApi methods as plain `suspend fun` (no
 * callback parameter) - the generated `setUp` wrapper already runs each call in its own
 * `CoroutineScope(Dispatchers.Main).launch { }` and replies with the result or a caught
 * exception, so this class never manages that scope itself. GazerFlutterApi is generated the
 * same way (its methods are `suspend fun` too), which is why every `PipelineListener` callback
 * below runs inside [mainScope] instead of a `Handler.post { }` callback.
 */
class PigeonHostApiImpl(
    private val context: Context,
    private val flutterApi: GazerFlutterApi,
    private val videoDevices: () -> List<VideoDevice>,
    private val audioDevices: () -> List<AudioDevice>,
    private val mainScope: CoroutineScope = CoroutineScope(Dispatchers.Main.immediate),
) : GazerHostApi,
    PipelineListener {
    /** Test/composition seam - `internal` so PigeonHostApiImplTest can inject a fake without a real ServiceConnection. */
    internal var host: PipelineHost? = null
    private var hostDeferred: CompletableDeferred<PipelineHost>? = null

    /**
     * Test seam - `internal` so PigeonHostApiImplTest can drive onServiceConnected/
     * onServiceDisconnected directly with a real StreamService.LocalBinder.
     */
    internal val connection =
        object : ServiceConnection {
            override fun onServiceConnected(
                name: ComponentName?,
                binder: IBinder?,
            ) {
                val serviceBinder = binder as? StreamService.LocalBinder ?: return
                serviceBinder.setListener(this@PigeonHostApiImpl)
                val boundHost =
                    object : PipelineHost {
                        override fun pipeline(): GazerPipeline = serviceBinder.pipeline
                    }
                host = boundHost
                hostDeferred?.complete(boundHost)
                hostDeferred = null
            }

            override fun onServiceDisconnected(name: ComponentName?) {
                host = null
            }
        }

    override fun listVideoDevices(): List<VideoDevice> = videoDevices()

    override fun listAudioDevices(): List<AudioDevice> = audioDevices()

    override suspend fun requestUsbPermission(deviceId: String): Boolean {
        // M1 lists no USB devices; always deny so Dart's UI never offers a USB source.
        return false
    }

    override suspend fun prepare(config: StreamConfig): PrepareResult {
        val currentHost = host ?: awaitBoundHost()
        if (currentHost == null) {
            postState(NativePipelineState.ERROR, GazerErrorCode.SERVICE_START_DENIED, "bindService failed")
            return PrepareResult(ok = false, error = GazerErrorCode.SERVICE_START_DENIED, detail = "bindService failed")
        }
        return currentHost.pipeline().prepare(config)
    }

    override suspend fun start(target: StreamTarget) {
        host?.pipeline()?.start(target)
    }

    override suspend fun stop() {
        host?.pipeline()?.stop()
    }

    override fun setVideoBitrate(kbps: Long) {
        host?.pipeline()?.setVideoBitrate(kbps.toInt())
    }

    override fun getState(): NativePipelineState = host?.pipeline()?.state ?: NativePipelineState.IDLE

    /** Binds StreamService and suspends until its ServiceConnection connects; null if bindService() itself refuses to even start binding. */
    private suspend fun awaitBoundHost(): PipelineHost? {
        val deferred = CompletableDeferred<PipelineHost>()
        hostDeferred = deferred
        val bound = bindService()
        if (!bound) {
            hostDeferred = null
            return null
        }
        return deferred.await()
    }

    private fun bindService(): Boolean {
        StreamService.start(context)
        return context.bindService(Intent(context, StreamService::class.java), connection, Context.BIND_AUTO_CREATE)
    }

    // PipelineListener - each call launches on mainScope, since GazerFlutterApi's methods are
    // suspend functions (Pigeon 28 default for @FlutterApi) that must run on the main thread,
    // the same thread platform channel messages are always sent from.

    override fun onState(
        state: NativePipelineState,
        error: GazerErrorCode?,
        detail: String?,
    ) {
        postState(state, error, detail)
    }

    override fun onStats(sample: StatsSample) {
        mainScope.launch { flutterApi.onStats(sample) }
    }

    override fun onAuthResult(ok: Boolean) {
        mainScope.launch { flutterApi.onAuthResult(ok) }
    }

    private fun postState(
        state: NativePipelineState,
        error: GazerErrorCode?,
        detail: String?,
    ) {
        mainScope.launch { flutterApi.onStateChanged(StateEvent(state = state, error = error, detail = detail)) }
    }
}
