import '../pigeon/pipeline.g.dart';
import 'app_localizations.dart';

/// Maps a [GazerErrorCode] to its localized `(message, action)` pair.
///
/// Centralised so every error surface (today: [HomeScreen]'s error
/// banner) reads identical copy for the same code.
(String, String) errorTextFor(AppLocalizations l10n, GazerErrorCode code) {
  return switch (code) {
    GazerErrorCode.usbPermissionDenied => (
      l10n.errorUsbPermissionDeniedMessage,
      l10n.errorUsbPermissionDeniedAction,
    ),
    GazerErrorCode.uvcNoUsableFormat => (
      l10n.errorUvcNoUsableFormatMessage,
      l10n.errorUvcNoUsableFormatAction,
    ),
    GazerErrorCode.uvcOpenFailed => (
      l10n.errorUvcOpenFailedMessage,
      l10n.errorUvcOpenFailedAction,
    ),
    GazerErrorCode.cameraUnavailable => (
      l10n.errorCameraUnavailableMessage,
      l10n.errorCameraUnavailableAction,
    ),
    GazerErrorCode.cameraInUse => (
      l10n.errorCameraInUseMessage,
      l10n.errorCameraInUseAction,
    ),
    GazerErrorCode.encoderFailed => (
      l10n.errorEncoderFailedMessage,
      l10n.errorEncoderFailedAction,
    ),
    GazerErrorCode.audioSourceFailed => (
      l10n.errorAudioSourceFailedMessage,
      l10n.errorAudioSourceFailedAction,
    ),
    GazerErrorCode.rtmpAuthFailed => (
      l10n.errorRtmpAuthFailedMessage,
      l10n.errorRtmpAuthFailedAction,
    ),
    GazerErrorCode.rtmpConnectFailed => (
      l10n.errorRtmpConnectFailedMessage,
      l10n.errorRtmpConnectFailedAction,
    ),
    GazerErrorCode.rtmpDisconnected => (
      l10n.errorRtmpDisconnectedMessage,
      l10n.errorRtmpDisconnectedAction,
    ),
    GazerErrorCode.usbDetached => (
      l10n.errorUsbDetachedMessage,
      l10n.errorUsbDetachedAction,
    ),
    GazerErrorCode.serviceStartDenied => (
      l10n.errorServiceStartDeniedMessage,
      l10n.errorServiceStartDeniedAction,
    ),
    GazerErrorCode.unknown => (
      l10n.errorUnknownMessage,
      l10n.errorUnknownAction,
    ),
  };
}
