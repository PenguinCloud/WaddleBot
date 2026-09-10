import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[Locale('en')];

  /// No description provided for @appTitle.
  ///
  /// In en, this message translates to:
  /// **'Gazer'**
  String get appTitle;

  /// No description provided for @homeScreenTitle.
  ///
  /// In en, this message translates to:
  /// **'Gazer'**
  String get homeScreenTitle;

  /// No description provided for @settingsScreenTitle.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsScreenTitle;

  /// No description provided for @settingsButtonLabel.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsButtonLabel;

  /// No description provided for @versionLabel.
  ///
  /// In en, this message translates to:
  /// **'Version {version}'**
  String versionLabel(String version);

  /// No description provided for @sourcePickerTitle.
  ///
  /// In en, this message translates to:
  /// **'Select camera'**
  String get sourcePickerTitle;

  /// No description provided for @sourceBackCameraLabel.
  ///
  /// In en, this message translates to:
  /// **'Back camera'**
  String get sourceBackCameraLabel;

  /// No description provided for @sourceFrontCameraLabel.
  ///
  /// In en, this message translates to:
  /// **'Front camera'**
  String get sourceFrontCameraLabel;

  /// No description provided for @sourceTileSemanticsLabel.
  ///
  /// In en, this message translates to:
  /// **'{name} camera source'**
  String sourceTileSemanticsLabel(String name);

  /// No description provided for @goLiveButtonLabel.
  ///
  /// In en, this message translates to:
  /// **'Go Live'**
  String get goLiveButtonLabel;

  /// No description provided for @goLiveButtonSemanticsLabel.
  ///
  /// In en, this message translates to:
  /// **'Go live button'**
  String get goLiveButtonSemanticsLabel;

  /// No description provided for @stopButtonLabel.
  ///
  /// In en, this message translates to:
  /// **'Stop'**
  String get stopButtonLabel;

  /// No description provided for @stopButtonSemanticsLabel.
  ///
  /// In en, this message translates to:
  /// **'Stop stream button'**
  String get stopButtonSemanticsLabel;

  /// No description provided for @statusChipIdleLabel.
  ///
  /// In en, this message translates to:
  /// **'Idle'**
  String get statusChipIdleLabel;

  /// No description provided for @statusChipPreparingLabel.
  ///
  /// In en, this message translates to:
  /// **'Preparing'**
  String get statusChipPreparingLabel;

  /// No description provided for @statusChipReadyLabel.
  ///
  /// In en, this message translates to:
  /// **'Ready'**
  String get statusChipReadyLabel;

  /// No description provided for @statusChipConnectingLabel.
  ///
  /// In en, this message translates to:
  /// **'Connecting'**
  String get statusChipConnectingLabel;

  /// No description provided for @statusChipStreamingLabel.
  ///
  /// In en, this message translates to:
  /// **'Streaming'**
  String get statusChipStreamingLabel;

  /// No description provided for @statusChipReconnectingLabel.
  ///
  /// In en, this message translates to:
  /// **'Reconnecting'**
  String get statusChipReconnectingLabel;

  /// No description provided for @statusChipStoppingLabel.
  ///
  /// In en, this message translates to:
  /// **'Stopping'**
  String get statusChipStoppingLabel;

  /// No description provided for @statusChipErrorLabel.
  ///
  /// In en, this message translates to:
  /// **'Error'**
  String get statusChipErrorLabel;

  /// No description provided for @statusChipSemanticsLabel.
  ///
  /// In en, this message translates to:
  /// **'Stream status: {status}'**
  String statusChipSemanticsLabel(String status);

  /// No description provided for @statusPanelTitle.
  ///
  /// In en, this message translates to:
  /// **'Status'**
  String get statusPanelTitle;

  /// No description provided for @errorUsbPermissionDeniedMessage.
  ///
  /// In en, this message translates to:
  /// **'USB permission was denied.'**
  String get errorUsbPermissionDeniedMessage;

  /// No description provided for @errorUsbPermissionDeniedAction.
  ///
  /// In en, this message translates to:
  /// **'Reconnect the device and grant permission when prompted.'**
  String get errorUsbPermissionDeniedAction;

  /// No description provided for @errorUvcNoUsableFormatMessage.
  ///
  /// In en, this message translates to:
  /// **'No usable video format was found on this device.'**
  String get errorUvcNoUsableFormatMessage;

  /// No description provided for @errorUvcNoUsableFormatAction.
  ///
  /// In en, this message translates to:
  /// **'Try a different capture device, or use the phone camera.'**
  String get errorUvcNoUsableFormatAction;

  /// No description provided for @errorUvcOpenFailedMessage.
  ///
  /// In en, this message translates to:
  /// **'The capture device could not be opened.'**
  String get errorUvcOpenFailedMessage;

  /// No description provided for @errorUvcOpenFailedAction.
  ///
  /// In en, this message translates to:
  /// **'Disconnect and reconnect the device, then try again.'**
  String get errorUvcOpenFailedAction;

  /// No description provided for @errorCameraUnavailableMessage.
  ///
  /// In en, this message translates to:
  /// **'The camera is unavailable.'**
  String get errorCameraUnavailableMessage;

  /// No description provided for @errorCameraUnavailableAction.
  ///
  /// In en, this message translates to:
  /// **'Check camera permission in system settings.'**
  String get errorCameraUnavailableAction;

  /// No description provided for @errorCameraInUseMessage.
  ///
  /// In en, this message translates to:
  /// **'The camera is in use by another app.'**
  String get errorCameraInUseMessage;

  /// No description provided for @errorCameraInUseAction.
  ///
  /// In en, this message translates to:
  /// **'Close other apps using the camera and try again.'**
  String get errorCameraInUseAction;

  /// No description provided for @errorEncoderFailedMessage.
  ///
  /// In en, this message translates to:
  /// **'The video encoder failed to start.'**
  String get errorEncoderFailedMessage;

  /// No description provided for @errorEncoderFailedAction.
  ///
  /// In en, this message translates to:
  /// **'Lower the resolution or bitrate and try again.'**
  String get errorEncoderFailedAction;

  /// No description provided for @errorAudioSourceFailedMessage.
  ///
  /// In en, this message translates to:
  /// **'The audio source failed to start.'**
  String get errorAudioSourceFailedMessage;

  /// No description provided for @errorAudioSourceFailedAction.
  ///
  /// In en, this message translates to:
  /// **'Choose a different audio source in Settings.'**
  String get errorAudioSourceFailedAction;

  /// No description provided for @errorRtmpAuthFailedMessage.
  ///
  /// In en, this message translates to:
  /// **'The server rejected the stream credentials.'**
  String get errorRtmpAuthFailedMessage;

  /// No description provided for @errorRtmpAuthFailedAction.
  ///
  /// In en, this message translates to:
  /// **'Check the username and password in Settings.'**
  String get errorRtmpAuthFailedAction;

  /// No description provided for @errorRtmpConnectFailedMessage.
  ///
  /// In en, this message translates to:
  /// **'Could not connect to the streaming server.'**
  String get errorRtmpConnectFailedMessage;

  /// No description provided for @errorRtmpConnectFailedAction.
  ///
  /// In en, this message translates to:
  /// **'Check the URL and your network connection, then try again.'**
  String get errorRtmpConnectFailedAction;

  /// No description provided for @errorRtmpDisconnectedMessage.
  ///
  /// In en, this message translates to:
  /// **'The stream was disconnected.'**
  String get errorRtmpDisconnectedMessage;

  /// No description provided for @errorRtmpDisconnectedAction.
  ///
  /// In en, this message translates to:
  /// **'Reconnecting automatically; check your network if this repeats.'**
  String get errorRtmpDisconnectedAction;

  /// No description provided for @errorUsbDetachedMessage.
  ///
  /// In en, this message translates to:
  /// **'The USB device was disconnected.'**
  String get errorUsbDetachedMessage;

  /// No description provided for @errorUsbDetachedAction.
  ///
  /// In en, this message translates to:
  /// **'Reconnect the device to resume.'**
  String get errorUsbDetachedAction;

  /// No description provided for @errorServiceStartDeniedMessage.
  ///
  /// In en, this message translates to:
  /// **'The streaming service could not start.'**
  String get errorServiceStartDeniedMessage;

  /// No description provided for @errorServiceStartDeniedAction.
  ///
  /// In en, this message translates to:
  /// **'Grant the notification/camera permissions and try again.'**
  String get errorServiceStartDeniedAction;

  /// No description provided for @errorUnknownMessage.
  ///
  /// In en, this message translates to:
  /// **'An unexpected error occurred.'**
  String get errorUnknownMessage;

  /// No description provided for @errorUnknownAction.
  ///
  /// In en, this message translates to:
  /// **'Try again; open Status for details.'**
  String get errorUnknownAction;

  /// No description provided for @targetSectionTitle.
  ///
  /// In en, this message translates to:
  /// **'Stream Target'**
  String get targetSectionTitle;

  /// No description provided for @urlFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'RTMP URL'**
  String get urlFieldLabel;

  /// No description provided for @urlFieldHint.
  ///
  /// In en, this message translates to:
  /// **'rtmp://host/app'**
  String get urlFieldHint;

  /// No description provided for @streamKeyFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'Stream Key'**
  String get streamKeyFieldLabel;

  /// No description provided for @revealStreamKeyLabel.
  ///
  /// In en, this message translates to:
  /// **'Show stream key'**
  String get revealStreamKeyLabel;

  /// No description provided for @usernameFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'Username'**
  String get usernameFieldLabel;

  /// No description provided for @passwordFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'Password'**
  String get passwordFieldLabel;

  /// No description provided for @revealPasswordLabel.
  ///
  /// In en, this message translates to:
  /// **'Show password'**
  String get revealPasswordLabel;

  /// No description provided for @qualitySectionTitle.
  ///
  /// In en, this message translates to:
  /// **'Quality'**
  String get qualitySectionTitle;

  /// No description provided for @resolutionFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'Resolution'**
  String get resolutionFieldLabel;

  /// No description provided for @frameRateFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'Frame Rate'**
  String get frameRateFieldLabel;

  /// No description provided for @frameRateOptionLabel.
  ///
  /// In en, this message translates to:
  /// **'{value} fps'**
  String frameRateOptionLabel(int value);

  /// No description provided for @bitrateFieldLabel.
  ///
  /// In en, this message translates to:
  /// **'Video Bitrate'**
  String get bitrateFieldLabel;

  /// No description provided for @bitrateValueLabel.
  ///
  /// In en, this message translates to:
  /// **'{value} kbps'**
  String bitrateValueLabel(int value);

  /// No description provided for @adaptiveBitrateLabel.
  ///
  /// In en, this message translates to:
  /// **'Adaptive Bitrate'**
  String get adaptiveBitrateLabel;

  /// No description provided for @audioSectionTitle.
  ///
  /// In en, this message translates to:
  /// **'Audio Source'**
  String get audioSectionTitle;

  /// No description provided for @audioSourceAutoLabel.
  ///
  /// In en, this message translates to:
  /// **'Automatic'**
  String get audioSourceAutoLabel;

  /// No description provided for @audioSourceMicLabel.
  ///
  /// In en, this message translates to:
  /// **'Phone Microphone'**
  String get audioSourceMicLabel;

  /// No description provided for @audioSourceUsbLabel.
  ///
  /// In en, this message translates to:
  /// **'USB Audio'**
  String get audioSourceUsbLabel;

  /// No description provided for @audioSourceSilenceLabel.
  ///
  /// In en, this message translates to:
  /// **'Silence'**
  String get audioSourceSilenceLabel;

  /// No description provided for @developerSectionTitle.
  ///
  /// In en, this message translates to:
  /// **'Developer'**
  String get developerSectionTitle;

  /// No description provided for @forceLibuvcLabel.
  ///
  /// In en, this message translates to:
  /// **'Force libuvc'**
  String get forceLibuvcLabel;

  /// No description provided for @saveButtonLabel.
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get saveButtonLabel;

  /// No description provided for @saveButtonSemanticsLabel.
  ///
  /// In en, this message translates to:
  /// **'Save settings'**
  String get saveButtonSemanticsLabel;

  /// No description provided for @settingsSavedMessage.
  ///
  /// In en, this message translates to:
  /// **'Settings saved'**
  String get settingsSavedMessage;

  /// No description provided for @validationUrlSchemeError.
  ///
  /// In en, this message translates to:
  /// **'URL must start with rtmp:// or rtmps://'**
  String get validationUrlSchemeError;

  /// No description provided for @validationUrlHostError.
  ///
  /// In en, this message translates to:
  /// **'URL must include a host'**
  String get validationUrlHostError;

  /// No description provided for @validationUrlPathError.
  ///
  /// In en, this message translates to:
  /// **'URL must include a path, e.g. /live'**
  String get validationUrlPathError;

  /// No description provided for @validationAuthBothOrNeitherError.
  ///
  /// In en, this message translates to:
  /// **'Enter both username and password, or leave both blank'**
  String get validationAuthBothOrNeitherError;

  /// No description provided for @validationRtmpAuthDisabledError.
  ///
  /// In en, this message translates to:
  /// **'Username/password authentication is not enabled for this license tier'**
  String get validationRtmpAuthDisabledError;

  /// No description provided for @validationUnknownError.
  ///
  /// In en, this message translates to:
  /// **'This field is invalid'**
  String get validationUnknownError;

  /// No description provided for @statusPanelCameraLabel.
  ///
  /// In en, this message translates to:
  /// **'Camera'**
  String get statusPanelCameraLabel;

  /// No description provided for @statusPanelCameraOffLabel.
  ///
  /// In en, this message translates to:
  /// **'Off'**
  String get statusPanelCameraOffLabel;

  /// No description provided for @statusPanelCameraOnLabel.
  ///
  /// In en, this message translates to:
  /// **'On ({name})'**
  String statusPanelCameraOnLabel(String name);

  /// No description provided for @statusPanelUvcLabel.
  ///
  /// In en, this message translates to:
  /// **'UVC Capture'**
  String get statusPanelUvcLabel;

  /// No description provided for @statusPanelUvcNotConnectedLabel.
  ///
  /// In en, this message translates to:
  /// **'No capture card connected'**
  String get statusPanelUvcNotConnectedLabel;

  /// No description provided for @statusPanelStreamLabel.
  ///
  /// In en, this message translates to:
  /// **'Stream'**
  String get statusPanelStreamLabel;

  /// No description provided for @statusPanelConnectionLabel.
  ///
  /// In en, this message translates to:
  /// **'Connection'**
  String get statusPanelConnectionLabel;

  /// No description provided for @statusPanelConnectionProtocolLabel.
  ///
  /// In en, this message translates to:
  /// **'Protocol'**
  String get statusPanelConnectionProtocolLabel;

  /// No description provided for @statusPanelConnectionHostLabel.
  ///
  /// In en, this message translates to:
  /// **'Host'**
  String get statusPanelConnectionHostLabel;

  /// No description provided for @statusPanelConnectionPathLabel.
  ///
  /// In en, this message translates to:
  /// **'Path'**
  String get statusPanelConnectionPathLabel;

  /// No description provided for @statusPanelConnectionKeyLabel.
  ///
  /// In en, this message translates to:
  /// **'Stream Key'**
  String get statusPanelConnectionKeyLabel;

  /// No description provided for @statusPanelConnectionAuthLabel.
  ///
  /// In en, this message translates to:
  /// **'Auth'**
  String get statusPanelConnectionAuthLabel;

  /// No description provided for @statusPanelConnectionAuthYes.
  ///
  /// In en, this message translates to:
  /// **'Yes'**
  String get statusPanelConnectionAuthYes;

  /// No description provided for @statusPanelConnectionAuthNo.
  ///
  /// In en, this message translates to:
  /// **'No'**
  String get statusPanelConnectionAuthNo;

  /// No description provided for @statusPanelStatsLabel.
  ///
  /// In en, this message translates to:
  /// **'Live Stats'**
  String get statusPanelStatsLabel;

  /// No description provided for @statusPanelBitrateLabel.
  ///
  /// In en, this message translates to:
  /// **'Bitrate: {value} kbps'**
  String statusPanelBitrateLabel(String value);

  /// No description provided for @statusPanelFpsLabel.
  ///
  /// In en, this message translates to:
  /// **'FPS: {value}'**
  String statusPanelFpsLabel(String value);

  /// No description provided for @statusPanelDroppedFramesLabel.
  ///
  /// In en, this message translates to:
  /// **'Dropped frames: {value}'**
  String statusPanelDroppedFramesLabel(String value);

  /// No description provided for @statusPanelUptimeLabel.
  ///
  /// In en, this message translates to:
  /// **'Uptime: {value}s'**
  String statusPanelUptimeLabel(String value);

  /// No description provided for @statusPanelReconnectCountLabel.
  ///
  /// In en, this message translates to:
  /// **'Reconnects: {value}'**
  String statusPanelReconnectCountLabel(String value);

  /// No description provided for @statusPanelCongestionLabel.
  ///
  /// In en, this message translates to:
  /// **'Congestion: {value}%'**
  String statusPanelCongestionLabel(String value);

  /// No description provided for @statusPanelConnectivityLabel.
  ///
  /// In en, this message translates to:
  /// **'Connectivity'**
  String get statusPanelConnectivityLabel;

  /// No description provided for @statusPanelOnlineLabel.
  ///
  /// In en, this message translates to:
  /// **'Online'**
  String get statusPanelOnlineLabel;

  /// No description provided for @statusPanelOfflineLabel.
  ///
  /// In en, this message translates to:
  /// **'Offline'**
  String get statusPanelOfflineLabel;

  /// No description provided for @statusPanelLicenseLabel.
  ///
  /// In en, this message translates to:
  /// **'License'**
  String get statusPanelLicenseLabel;

  /// No description provided for @statusPanelLicenseStatusUnknown.
  ///
  /// In en, this message translates to:
  /// **'Unknown'**
  String get statusPanelLicenseStatusUnknown;

  /// No description provided for @statusPanelLicenseStatusValid.
  ///
  /// In en, this message translates to:
  /// **'Valid'**
  String get statusPanelLicenseStatusValid;

  /// No description provided for @statusPanelLicenseStatusGracePeriod.
  ///
  /// In en, this message translates to:
  /// **'Grace period'**
  String get statusPanelLicenseStatusGracePeriod;

  /// No description provided for @statusPanelLicenseStatusInvalid.
  ///
  /// In en, this message translates to:
  /// **'Invalid'**
  String get statusPanelLicenseStatusInvalid;

  /// No description provided for @statusPanelLicenseFetchingLabel.
  ///
  /// In en, this message translates to:
  /// **'Fetching features… (required to stream)'**
  String get statusPanelLicenseFetchingLabel;

  /// No description provided for @statusPanelLicenseLastFetchedLabel.
  ///
  /// In en, this message translates to:
  /// **'Last fetched: {time}'**
  String statusPanelLicenseLastFetchedLabel(String time);

  /// No description provided for @statusPanelUpdateAvailableLabel.
  ///
  /// In en, this message translates to:
  /// **'Update available: v{version}'**
  String statusPanelUpdateAvailableLabel(String version);

  /// No description provided for @statusPanelUpdateNoneLabel.
  ///
  /// In en, this message translates to:
  /// **'Up to date'**
  String get statusPanelUpdateNoneLabel;

  /// No description provided for @statusPanelForegroundServiceLabel.
  ///
  /// In en, this message translates to:
  /// **'Foreground Service'**
  String get statusPanelForegroundServiceLabel;

  /// No description provided for @statusPanelForegroundServiceActiveLabel.
  ///
  /// In en, this message translates to:
  /// **'Active'**
  String get statusPanelForegroundServiceActiveLabel;

  /// No description provided for @statusPanelForegroundServiceInactiveLabel.
  ///
  /// In en, this message translates to:
  /// **'Inactive'**
  String get statusPanelForegroundServiceInactiveLabel;

  /// No description provided for @statusPanelCloseButtonLabel.
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get statusPanelCloseButtonLabel;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
