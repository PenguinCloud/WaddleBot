package io.waddlebot.gazer.pipeline

import io.waddlebot.gazer.pigeon.GazerErrorCode
import org.junit.jupiter.api.Assertions.assertAll
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.function.Executable

/** Table-driven coverage of every ErrorMapper.fromReason rule, including case-insensitivity. */
class ErrorMapperTest {
    private val cases =
        listOf(
            "401 Unauthorized" to GazerErrorCode.RTMP_AUTH_FAILED,
            "auth failed" to GazerErrorCode.RTMP_AUTH_FAILED,
            "AUTH FAILED" to GazerErrorCode.RTMP_AUTH_FAILED,
            "Unauthorized access" to GazerErrorCode.RTMP_AUTH_FAILED,
            "UNAUTHORIZED" to GazerErrorCode.RTMP_AUTH_FAILED,
            "Connection timeout" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "TIMEOUT" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "Connection refused" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "REFUSED" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "Host unreachable" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "UNREACHABLE" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "Failed to connect" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "FAILED TO CONNECT" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "java.net.UnknownHostException: example.com" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "UNKNOWNHOST" to GazerErrorCode.RTMP_CONNECT_FAILED,
            "Encoder error" to GazerErrorCode.ENCODER_FAILED,
            "ENCODER" to GazerErrorCode.ENCODER_FAILED,
            "codec configuration failed" to GazerErrorCode.ENCODER_FAILED,
            "CODEC" to GazerErrorCode.ENCODER_FAILED,
            "some other reason" to GazerErrorCode.UNKNOWN,
            "" to GazerErrorCode.UNKNOWN,
        )

    @Test
    fun `maps every reason string to the correct GazerErrorCode`() {
        assertAll(
            cases.map { (reason, expected) ->
                Executable { assertEquals(expected, ErrorMapper.fromReason(reason), "reason=\"$reason\"") }
            },
        )
    }
}
