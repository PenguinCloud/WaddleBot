package io.waddlebot.gazer.pipeline.sources

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import com.pedro.encoder.input.sources.video.Camera2Source
import com.pedro.encoder.input.sources.video.VideoSource
import io.waddlebot.gazer.pigeon.VideoDevice
import io.waddlebot.gazer.pigeon.VideoDeviceKind

/**
 * Resolves a Pigeon video device id ("camera:back"/"camera:front") to a physical Android
 * camera, indirected behind an interface so tests can fake CameraManager without Robolectric.
 */
interface CameraIds {
    /** Returns the camera id for [facing] (a CameraCharacteristics.LENS_FACING_* constant), or null if absent. */
    fun byFacing(facing: Int): String?
}

/** Production [CameraIds] backed by the real [CameraManager]. */
class CameraManagerIds(
    private val cameraManager: CameraManager,
) : CameraIds {
    override fun byFacing(facing: Int): String? {
        for (id in cameraManager.cameraIdList) {
            val characteristics = cameraManager.getCameraCharacteristics(id)
            if (characteristics.get(CameraCharacteristics.LENS_FACING) == facing) {
                return id
            }
        }
        return null
    }
}

/**
 * Lists and creates RootEncoder [VideoSource]s for M1's phone-camera-only device set. UVC and
 * Camera2-external sources are out of scope until M2 (see the M2 plan).
 */
class VideoSourceFactory(
    private val context: Context,
    private val cameraIds: CameraIds,
) {
    /** Lists back/front camera as [VideoDevice]s, omitting any facing the hardware lacks. */
    fun list(): List<VideoDevice> {
        val devices = mutableListOf<VideoDevice>()
        if (cameraIds.byFacing(CameraCharacteristics.LENS_FACING_BACK) != null) {
            devices.add(VideoDevice(id = "camera:back", kind = VideoDeviceKind.BACK_CAMERA, name = "Back camera"))
        }
        if (cameraIds.byFacing(CameraCharacteristics.LENS_FACING_FRONT) != null) {
            devices.add(VideoDevice(id = "camera:front", kind = VideoDeviceKind.FRONT_CAMERA, name = "Front camera"))
        }
        return devices
    }

    /**
     * Builds a [Camera2Source] for [deviceId]. VERIFIED (RootEncoder 2.8.1): Camera2Source
     * defaults to CameraHelper.Facing.BACK and only exposes facing selection via
     * switchCamera(), which flips the internal facing field unconditionally and only restarts
     * the camera if already running - safe to call immediately after construction, before
     * prepare()/start(). openCameraId(id) is NOT usable here: it is a no-op unless the source
     * isRunning() already (it calls Camera2ApiManager.reOpenCamera, meant for switching
     * physical camera ids on an already-open external/Camera2 source in M2, not cold facing
     * selection).
     */
    fun create(deviceId: String): VideoSource {
        val source = Camera2Source(context)
        when (deviceId) {
            "camera:back" -> Unit
            "camera:front" -> source.switchCamera()
            else -> throw IllegalArgumentException("Unknown video device id: $deviceId")
        }
        return source
    }
}
