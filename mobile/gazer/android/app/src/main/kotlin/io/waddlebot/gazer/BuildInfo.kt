package io.waddlebot.gazer

/**
 * Static build identity for this app. Exists (beyond Gradle's own `applicationId`) so a plain
 * JVM unit test can assert on the application id without parsing the manifest, giving the
 * `android-unit` JaCoCo gate a real, non-zero-denominator class to measure from Task 2 onward —
 * every later Kotlin file in Tasks 17-20 adds to this same gate, never replaces it.
 */
object BuildInfo {
    /** The application id declared in `android/app/build.gradle.kts`'s `defaultConfig`. */
    const val APPLICATION_ID = "io.waddlebot.gazer"

    /** Human-readable one-line identity string, e.g. for logs. */
    fun describe(): String = APPLICATION_ID
}
