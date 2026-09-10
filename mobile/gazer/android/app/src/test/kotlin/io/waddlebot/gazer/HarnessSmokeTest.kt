package io.waddlebot.gazer

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Test

/**
 * Trivial JVM-only tests proving the JUnit5 + JaCoCo unit-test harness (Task 2) actually
 * executes and reports coverage for this module. A canary: if gradle/test wiring breaks, this
 * fails loudly here instead of every later Kotlin test in Tasks 18-20 silently not running.
 */
class HarnessSmokeTest {
    @Test
    fun `arithmetic sanity check proves the JUnit5 runner executes`() {
        assertEquals(4, 2 + 2)
    }

    @Test
    fun `MainActivity can be constructed by the JVM unit test harness`() {
        // Plain object allocation only (no lifecycle call) - proves MainActivity links against
        // the Flutter embedding classpath from the unit-test target too, and gives JaCoCo a
        // non-trivial denominator for this class ahead of Task 20's real wiring.
        assertNotNull(MainActivity())
    }
}
