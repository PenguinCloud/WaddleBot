// ignore: unused_import
import 'package:intl/intl.dart' as intl;

import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Gazer';

  @override
  String get homeScreenTitle => 'Gazer';

  @override
  String get settingsScreenTitle => 'Settings';

  @override
  String get settingsButtonLabel => 'Settings';

  @override
  String versionLabel(String version) {
    return 'Version $version';
  }

  @override
  String get sourcePickerTitle => 'Select camera';

  @override
  String get sourceBackCameraLabel => 'Back camera';

  @override
  String get sourceFrontCameraLabel => 'Front camera';

  @override
  String sourceTileSemanticsLabel(String name) {
    return '$name camera source';
  }

  @override
  String get goLiveButtonLabel => 'Go Live';

  @override
  String get goLiveButtonSemanticsLabel => 'Go live button';

  @override
  String get stopButtonLabel => 'Stop';

  @override
  String get stopButtonSemanticsLabel => 'Stop stream button';

  @override
  String get statusChipIdleLabel => 'Idle';

  @override
  String get statusChipPreparingLabel => 'Preparing';

  @override
  String get statusChipReadyLabel => 'Ready';

  @override
  String get statusChipConnectingLabel => 'Connecting';

  @override
  String get statusChipStreamingLabel => 'Streaming';

  @override
  String get statusChipReconnectingLabel => 'Reconnecting';

  @override
  String get statusChipStoppingLabel => 'Stopping';

  @override
  String get statusChipErrorLabel => 'Error';

  @override
  String statusChipSemanticsLabel(String status) {
    return 'Stream status: $status';
  }

  @override
  String get statusPanelTitle => 'Status';

  @override
  String get errorUsbPermissionDeniedMessage => 'USB permission was denied.';

  @override
  String get errorUsbPermissionDeniedAction =>
      'Reconnect the device and grant permission when prompted.';

  @override
  String get errorUvcNoUsableFormatMessage =>
      'No usable video format was found on this device.';

  @override
  String get errorUvcNoUsableFormatAction =>
      'Try a different capture device, or use the phone camera.';

  @override
  String get errorUvcOpenFailedMessage =>
      'The capture device could not be opened.';

  @override
  String get errorUvcOpenFailedAction =>
      'Disconnect and reconnect the device, then try again.';

  @override
  String get errorCameraUnavailableMessage => 'The camera is unavailable.';

  @override
  String get errorCameraUnavailableAction =>
      'Check camera permission in system settings.';

  @override
  String get errorCameraInUseMessage => 'The camera is in use by another app.';

  @override
  String get errorCameraInUseAction =>
      'Close other apps using the camera and try again.';

  @override
  String get errorEncoderFailedMessage => 'The video encoder failed to start.';

  @override
  String get errorEncoderFailedAction =>
      'Lower the resolution or bitrate and try again.';

  @override
  String get errorAudioSourceFailedMessage =>
      'The audio source failed to start.';

  @override
  String get errorAudioSourceFailedAction =>
      'Choose a different audio source in Settings.';

  @override
  String get errorRtmpAuthFailedMessage =>
      'The server rejected the stream credentials.';

  @override
  String get errorRtmpAuthFailedAction =>
      'Check the username and password in Settings.';

  @override
  String get errorRtmpConnectFailedMessage =>
      'Could not connect to the streaming server.';

  @override
  String get errorRtmpConnectFailedAction =>
      'Check the URL and your network connection, then try again.';

  @override
  String get errorRtmpDisconnectedMessage => 'The stream was disconnected.';

  @override
  String get errorRtmpDisconnectedAction =>
      'Reconnecting automatically; check your network if this repeats.';

  @override
  String get errorUsbDetachedMessage => 'The USB device was disconnected.';

  @override
  String get errorUsbDetachedAction => 'Reconnect the device to resume.';

  @override
  String get errorServiceStartDeniedMessage =>
      'The streaming service could not start.';

  @override
  String get errorServiceStartDeniedAction =>
      'Grant the notification/camera permissions and try again.';

  @override
  String get errorUnknownMessage => 'An unexpected error occurred.';

  @override
  String get errorUnknownAction => 'Try again; open Status for details.';

  @override
  String get targetSectionTitle => 'Stream Target';

  @override
  String get urlFieldLabel => 'RTMP URL';

  @override
  String get urlFieldHint => 'rtmp://host/app';

  @override
  String get streamKeyFieldLabel => 'Stream Key';

  @override
  String get revealStreamKeyLabel => 'Show stream key';

  @override
  String get usernameFieldLabel => 'Username';

  @override
  String get passwordFieldLabel => 'Password';

  @override
  String get revealPasswordLabel => 'Show password';

  @override
  String get qualitySectionTitle => 'Quality';

  @override
  String get resolutionFieldLabel => 'Resolution';

  @override
  String get frameRateFieldLabel => 'Frame Rate';

  @override
  String frameRateOptionLabel(int value) {
    return '$value fps';
  }

  @override
  String get bitrateFieldLabel => 'Video Bitrate';

  @override
  String bitrateValueLabel(int value) {
    return '$value kbps';
  }

  @override
  String get adaptiveBitrateLabel => 'Adaptive Bitrate';

  @override
  String get audioSectionTitle => 'Audio Source';

  @override
  String get audioSourceAutoLabel => 'Automatic';

  @override
  String get audioSourceMicLabel => 'Phone Microphone';

  @override
  String get audioSourceUsbLabel => 'USB Audio';

  @override
  String get audioSourceSilenceLabel => 'Silence';

  @override
  String get developerSectionTitle => 'Developer';

  @override
  String get forceLibuvcLabel => 'Force libuvc';

  @override
  String get saveButtonLabel => 'Save';

  @override
  String get saveButtonSemanticsLabel => 'Save settings';

  @override
  String get settingsSavedMessage => 'Settings saved';

  @override
  String get validationUrlSchemeError =>
      'URL must start with rtmp:// or rtmps://';

  @override
  String get validationUrlHostError => 'URL must include a host';

  @override
  String get validationUrlPathError => 'URL must include a path, e.g. /live';

  @override
  String get validationAuthBothOrNeitherError =>
      'Enter both username and password, or leave both blank';

  @override
  String get validationRtmpAuthDisabledError =>
      'Username/password authentication is not enabled for this license tier';

  @override
  String get validationUnknownError => 'This field is invalid';

  @override
  String get statusPanelCameraLabel => 'Camera';

  @override
  String get statusPanelCameraOffLabel => 'Off';

  @override
  String statusPanelCameraOnLabel(String name) {
    return 'On ($name)';
  }

  @override
  String get statusPanelUvcLabel => 'UVC Capture';

  @override
  String get statusPanelUvcNotConnectedLabel => 'No capture card connected';

  @override
  String get statusPanelStreamLabel => 'Stream';

  @override
  String get statusPanelConnectionLabel => 'Connection';

  @override
  String get statusPanelConnectionProtocolLabel => 'Protocol';

  @override
  String get statusPanelConnectionHostLabel => 'Host';

  @override
  String get statusPanelConnectionPathLabel => 'Path';

  @override
  String get statusPanelConnectionKeyLabel => 'Stream Key';

  @override
  String get statusPanelConnectionAuthLabel => 'Auth';

  @override
  String get statusPanelConnectionAuthYes => 'Yes';

  @override
  String get statusPanelConnectionAuthNo => 'No';

  @override
  String get statusPanelStatsLabel => 'Live Stats';

  @override
  String statusPanelBitrateLabel(String value) {
    return 'Bitrate: $value kbps';
  }

  @override
  String statusPanelFpsLabel(String value) {
    return 'FPS: $value';
  }

  @override
  String statusPanelDroppedFramesLabel(String value) {
    return 'Dropped frames: $value';
  }

  @override
  String statusPanelUptimeLabel(String value) {
    return 'Uptime: ${value}s';
  }

  @override
  String statusPanelReconnectCountLabel(String value) {
    return 'Reconnects: $value';
  }

  @override
  String statusPanelCongestionLabel(String value) {
    return 'Congestion: $value%';
  }

  @override
  String get statusPanelConnectivityLabel => 'Connectivity';

  @override
  String get statusPanelOnlineLabel => 'Online';

  @override
  String get statusPanelOfflineLabel => 'Offline';

  @override
  String get statusPanelLicenseLabel => 'License';

  @override
  String get statusPanelLicenseStatusUnknown => 'Unknown';

  @override
  String get statusPanelLicenseStatusValid => 'Valid';

  @override
  String get statusPanelLicenseStatusGracePeriod => 'Grace period';

  @override
  String get statusPanelLicenseStatusInvalid => 'Invalid';

  @override
  String get statusPanelLicenseFetchingLabel =>
      'Fetching features… (required to stream)';

  @override
  String statusPanelLicenseLastFetchedLabel(String time) {
    return 'Last fetched: $time';
  }

  @override
  String statusPanelUpdateAvailableLabel(String version) {
    return 'Update available: v$version';
  }

  @override
  String get statusPanelUpdateNoneLabel => 'Up to date';

  @override
  String get statusPanelForegroundServiceLabel => 'Foreground Service';

  @override
  String get statusPanelForegroundServiceActiveLabel => 'Active';

  @override
  String get statusPanelForegroundServiceInactiveLabel => 'Inactive';

  @override
  String get statusPanelCloseButtonLabel => 'Close';

  @override
  String get goLiveFailedMessage =>
      'Could not start the stream. Please try again.';

  @override
  String get settingsSaveFailed => 'Failed to save settings. Please try again.';

  @override
  String get settingsDebugLogsLabel => 'Debug logs';

  @override
  String get updateOpenFailed =>
      'Could not open the release page. Please try again.';

  @override
  String get permissionDeniedMessage =>
      'Camera and microphone permission are needed to go live.';

  @override
  String get permissionDeniedRetryLabel => 'Retry';

  @override
  String get permissionPermanentlyDeniedMessage =>
      'Camera or microphone permission was permanently denied.';

  @override
  String get permissionOpenSettingsLabel => 'Open settings';
}
