package io.waddlebot.gazer.pipeline

import io.waddlebot.gazer.pigeon.GazerErrorCode

/**
 * Classifies RootEncoder's free-text ConnectChecker.onConnectionFailed(reason) strings into a
 * Pigeon GazerErrorCode Dart can branch on - RootEncoder never returns a structured error type,
 * only reason strings, so this table is the single place that interprets them.
 */
object ErrorMapper {
    private val authMarkers = listOf("401", "auth", "unauthorized")
    private val connectMarkers = listOf("timeout", "refused", "unreachable", "failed to connect", "unknownhost")
    private val encoderMarkers = listOf("encoder", "codec")

    /** Maps a ConnectChecker reason string to a GazerErrorCode, case-insensitively. */
    fun fromReason(reason: String): GazerErrorCode {
        val lower = reason.lowercase()
        return when {
            authMarkers.any { lower.contains(it) } -> GazerErrorCode.RTMP_AUTH_FAILED
            connectMarkers.any { lower.contains(it) } -> GazerErrorCode.RTMP_CONNECT_FAILED
            encoderMarkers.any { lower.contains(it) } -> GazerErrorCode.ENCODER_FAILED
            else -> GazerErrorCode.UNKNOWN
        }
    }
}
