package io.waddlebot.gazer

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeAll
import org.junit.jupiter.api.Test
import org.w3c.dom.Document
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Parses the real AndroidManifest.xml from source with a plain XML DOM parser (no Android
 * framework, no Robolectric) and asserts the M1-required permissions, the StreamService
 * foreground-service declaration, and the M1 no-USB constraint. Exists so a manifest
 * regression (missing permission, wrong service flags) fails a JVM unit test instead of only
 * surfacing at runtime on-device.
 */
class ManifestContentTest {
    companion object {
        private lateinit var document: Document

        @BeforeAll
        @JvmStatic
        fun loadManifest() {
            val manifestFile = File("src/main/AndroidManifest.xml")
            require(manifestFile.exists()) { "AndroidManifest.xml not found at ${manifestFile.absolutePath}" }
            val builder = DocumentBuilderFactory.newInstance().newDocumentBuilder()
            document = builder.parse(manifestFile)
        }
    }

    /**
     * Returns every `android:name` value declared by a `uses-permission` element in the parsed
     * manifest, in document order — the shared lookup each permission-focused test filters.
     */
    private fun permissionNames(): List<String> {
        val nodes = document.getElementsByTagName("uses-permission")
        return (0 until nodes.length).map { (nodes.item(it) as Element).getAttribute("android:name") }
    }

    @Test
    fun `declares camera and microphone permissions`() {
        val names = permissionNames()
        assertTrue(names.contains("android.permission.CAMERA"))
        assertTrue(names.contains("android.permission.RECORD_AUDIO"))
    }

    @Test
    fun `declares foreground service permissions for camera and microphone`() {
        val names = permissionNames()
        assertTrue(names.contains("android.permission.FOREGROUND_SERVICE"))
        assertTrue(names.contains("android.permission.FOREGROUND_SERVICE_CAMERA"))
        assertTrue(names.contains("android.permission.FOREGROUND_SERVICE_MICROPHONE"))
    }

    @Test
    fun `declares network, notification and wake lock permissions`() {
        val names = permissionNames()
        assertTrue(names.contains("android.permission.INTERNET"))
        assertTrue(names.contains("android.permission.POST_NOTIFICATIONS"))
        assertTrue(names.contains("android.permission.WAKE_LOCK"))
    }

    @Test
    fun `declares no USB permissions or features in M1`() {
        val names = permissionNames()
        assertFalse(names.any { it.contains("USB", ignoreCase = true) })
        val features = document.getElementsByTagName("uses-feature")
        val featureNames = (0 until features.length).map { (features.item(it) as Element).getAttribute("android:name") }
        assertFalse(featureNames.any { it.contains("usb", ignoreCase = true) })
    }

    @Test
    fun `declares StreamService as a non-exported camera and microphone foreground service`() {
        val services = document.getElementsByTagName("service")
        val streamService =
            (0 until services.length)
                .map { services.item(it) as Element }
                .firstOrNull { it.getAttribute("android:name") == ".pipeline.StreamService" }
        requireNotNull(streamService) { "StreamService not declared in AndroidManifest.xml" }
        val serviceType = streamService.getAttribute("android:foregroundServiceType")
        assertTrue(serviceType.contains("camera"))
        assertTrue(serviceType.contains("microphone"))
        assertFalse(streamService.getAttribute("android:exported").toBoolean())
    }
}
