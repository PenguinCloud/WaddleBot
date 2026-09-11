import 'package:freezed_annotation/freezed_annotation.dart';

import 'quality.dart';
import 'stream_target_settings.dart';

part 'gazer_settings.freezed.dart';
part 'gazer_settings.g.dart';

/// User's chosen audio source for the stream.
///
/// `auto` resolves at Go Live time (M1: always mic, since M1 has no UVC/USB
/// audio path); `usbAudio` is reserved for M2 and falls back to mic in M1.
enum AudioSourceChoice { auto, mic, usbAudio, silence }

/// The complete set of user-configurable Gazer settings: target, quality,
/// audio source and the hidden developer "force libuvc" toggle.
///
/// This is the aggregate root `SettingsRepository` loads/saves; persistence
/// itself is split across secure storage (target) and shared_preferences
/// (everything else) — see `SecureSettingsRepository`.
///
/// Requires the package-wide `explicit_to_json: true` in `build.yaml`
/// because [target] and [quality] are themselves freezed classes: without
/// it json_serializable embeds the raw nested object instead of calling its
/// `toJson()`, breaking round-trips.
@freezed
abstract class GazerSettings with _$GazerSettings {
  const factory GazerSettings({
    required StreamTargetSettings target,
    required QualitySettings quality,
    required AudioSourceChoice audio,
    required bool forceLibuvc,
    required bool debugLogs,
  }) = _GazerSettings;

  /// Deserializes a [GazerSettings] from JSON (round-trip tests only —
  /// [SecureSettingsRepository] persists fields individually, not as one blob).
  factory GazerSettings.fromJson(Map<String, dynamic> json) =>
      _$GazerSettingsFromJson(json);

  /// First-launch defaults: empty target, default quality, auto audio,
  /// developer toggles (force libuvc, debug logs) off.
  factory GazerSettings.defaults() => GazerSettings(
    target: StreamTargetSettings.empty(),
    quality: QualitySettings.defaults(),
    audio: AudioSourceChoice.auto,
    forceLibuvc: false,
    debugLogs: false,
  );
}
