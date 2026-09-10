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
  /// Private constructor (freezed convention) so this class can carry the
  /// [toString] override below in addition to its generated members.
  const StreamTargetSettings._();

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

  /// Redacted string form (R22): this class is logged and nested inside
  /// [GazerSettings]'s own toString, so the freezed-generated default
  /// (which prints every field in plaintext) is overridden here. [url] is
  /// reduced to host + path (query/userinfo/fragment dropped, since a
  /// RTMPS URL can carry auth in those parts); [username] and [password]
  /// print as `<redacted>`; [streamKey] prints masked with only its last 4
  /// characters visible, enough to eyeball "is this the key I expect"
  /// without exposing it.
  @override
  String toString() {
    return 'StreamTargetSettings(url: $_redactedUrl, streamKey: $_redactedStreamKey, '
        'username: ${_redactCredential(username)}, password: ${_redactCredential(password)})';
  }

  String get _redactedUrl {
    if (url.isEmpty) return '';
    final uri = Uri.tryParse(url);
    if (uri == null || uri.host.isEmpty) return '<redacted>';
    return '${uri.host}${uri.path}';
  }

  String get _redactedStreamKey {
    final key = streamKey;
    if (key == null) return 'null';
    if (key.length <= 4) return '****';
    return '****${key.substring(key.length - 4)}';
  }

  /// `null` stays `null` (absence isn't a secret); any non-null value,
  /// however short, redacts fully rather than partially mask it.
  String _redactCredential(String? value) =>
      value == null ? 'null' : '<redacted>';
}
