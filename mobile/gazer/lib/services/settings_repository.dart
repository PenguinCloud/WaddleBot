import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/gazer_settings.dart';
import '../models/quality.dart';
import '../models/stream_target_settings.dart';

/// Loads and persists the user's [GazerSettings].
///
/// Implementations decide where each field lives; [SecureSettingsRepository]
/// is the only implementation in M1, splitting secrets into secure storage
/// and everything else into shared_preferences per the design's storage
/// split table.
abstract class SettingsRepository {
  /// Returns the persisted settings, or [GazerSettings.defaults] if nothing
  /// has ever been saved.
  Future<GazerSettings> load();

  /// Persists every field of [s].
  Future<void> save(GazerSettings s);
}

/// [SettingsRepository] backed by `flutter_secure_storage` (target: URL,
/// stream key, username, password) and `shared_preferences` (quality,
/// audio, developer toggle) — never mixes the two.
class SecureSettingsRepository implements SettingsRepository {
  // Constructor params (secure, prefs) are the fixed public contract while
  // the fields stay private (_secure, _prefs); an initializing formal
  // (`this._secure`) would force the external param name to match the
  // private field name, breaking the contract, so these are assigned
  // explicitly instead.
  SecureSettingsRepository({
    required FlutterSecureStorage secure,
    required SharedPreferencesAsync prefs,
  }) : _secure = secure, // ignore: prefer_initializing_formals
       _prefs = prefs; // ignore: prefer_initializing_formals

  final FlutterSecureStorage _secure;
  final SharedPreferencesAsync _prefs;

  static const String _kTargetUrl = 'gazer.target.url';
  static const String _kTargetStreamKey = 'gazer.target.streamKey';
  static const String _kTargetUsername = 'gazer.target.username';
  static const String _kTargetPassword = 'gazer.target.password';
  static const String _kQualityResolution = 'gazer.quality.resolution';
  static const String _kQualityFps = 'gazer.quality.fps';
  static const String _kQualityBitrate = 'gazer.quality.bitrate';
  static const String _kQualityAdaptive = 'gazer.quality.adaptive';
  static const String _kAudioSource = 'gazer.audio.source';
  static const String _kDeveloperForceLibuvc = 'gazer.developer.forceLibuvc';
  static const String _kDeveloperDebugLogs = 'gazer.developer.debugLogs';

  @override
  Future<GazerSettings> load() async {
    final defaults = GazerSettings.defaults();

    final url = await _secure.read(key: _kTargetUrl) ?? defaults.target.url;
    final streamKey = await _secure.read(key: _kTargetStreamKey);
    final username = await _secure.read(key: _kTargetUsername);
    final password = await _secure.read(key: _kTargetPassword);

    final resolutionName = await _prefs.getString(_kQualityResolution);
    final resolution = Resolution.values.firstWhere(
      (r) => r.name == resolutionName,
      orElse: () => defaults.quality.resolution,
    );
    final fpsValue = await _prefs.getInt(_kQualityFps);
    final frameRate = FrameRate.values.firstWhere(
      (f) => f.value == fpsValue,
      orElse: () => defaults.quality.frameRate,
    );
    final bitrate =
        await _prefs.getInt(_kQualityBitrate) ??
        defaults.quality.videoBitrateKbps;
    final adaptive =
        await _prefs.getBool(_kQualityAdaptive) ??
        defaults.quality.adaptiveBitrate;

    final audioName = await _prefs.getString(_kAudioSource);
    final audio = AudioSourceChoice.values.firstWhere(
      (a) => a.name == audioName,
      orElse: () => defaults.audio,
    );
    final forceLibuvc =
        await _prefs.getBool(_kDeveloperForceLibuvc) ?? defaults.forceLibuvc;
    final debugLogs =
        await _prefs.getBool(_kDeveloperDebugLogs) ?? defaults.debugLogs;

    return GazerSettings(
      target: StreamTargetSettings(
        url: url,
        streamKey: streamKey,
        username: username,
        password: password,
      ),
      quality: QualitySettings(
        resolution: resolution,
        frameRate: frameRate,
        videoBitrateKbps: bitrate,
        adaptiveBitrate: adaptive,
      ),
      audio: audio,
      forceLibuvc: forceLibuvc,
      debugLogs: debugLogs,
    );
  }

  @override
  Future<void> save(GazerSettings s) async {
    await _secure.write(key: _kTargetUrl, value: s.target.url);
    await _writeOrDeleteSecure(_kTargetStreamKey, s.target.streamKey);
    await _writeOrDeleteSecure(_kTargetUsername, s.target.username);
    await _writeOrDeleteSecure(_kTargetPassword, s.target.password);

    await _prefs.setString(_kQualityResolution, s.quality.resolution.name);
    await _prefs.setInt(_kQualityFps, s.quality.frameRate.value);
    await _prefs.setInt(_kQualityBitrate, s.quality.videoBitrateKbps);
    await _prefs.setBool(_kQualityAdaptive, s.quality.adaptiveBitrate);
    await _prefs.setString(_kAudioSource, s.audio.name);
    await _prefs.setBool(_kDeveloperForceLibuvc, s.forceLibuvc);
    await _prefs.setBool(_kDeveloperDebugLogs, s.debugLogs);
  }

  Future<void> _writeOrDeleteSecure(String key, String? value) {
    if (value == null) {
      return _secure.delete(key: key);
    }
    return _secure.write(key: key, value: value);
  }
}
