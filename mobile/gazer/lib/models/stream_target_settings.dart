import 'package:freezed_annotation/freezed_annotation.dart';

part 'stream_target_settings.freezed.dart';
part 'stream_target_settings.g.dart';

/// User-supplied RTMP/RTMPS destination: URL, optional stream key, and an
/// optional both-or-neither username/password pair.
///
/// Every field here is sensitive: [SecureSettingsRepository] stores it in
/// `flutter_secure_storage`, never `shared_preferences`, and it is never
/// logged. Validation and the key-append/dedupe logic live in
/// `TargetValidator`, not here.
@freezed
abstract class StreamTargetSettings with _$StreamTargetSettings {
  const factory StreamTargetSettings({
    required String url,
    String? streamKey,
    String? username,
    String? password,
  }) = _StreamTargetSettings;

  /// Deserializes a [StreamTargetSettings] from JSON (round-trip tests only).
  factory StreamTargetSettings.fromJson(Map<String, dynamic> json) =>
      _$StreamTargetSettingsFromJson(json);

  /// Empty target: blank URL, no key, no credentials — the pre-setup state.
  factory StreamTargetSettings.empty() => const StreamTargetSettings(url: '');
}
