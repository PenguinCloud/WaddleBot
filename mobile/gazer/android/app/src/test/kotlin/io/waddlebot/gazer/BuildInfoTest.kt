package io.waddlebot.gazer

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

/** Trivial coverage-anchor test for [BuildInfo] — see the class doc for why it exists. */
class BuildInfoTest {
    @Test
    fun `application id matches the Gradle applicationId`() {
        assertEquals("io.waddlebot.gazer", BuildInfo.APPLICATION_ID)
    }

    @Test
    fun `describe returns the application id`() {
        assertEquals("io.waddlebot.gazer", BuildInfo.describe())
    }
}
