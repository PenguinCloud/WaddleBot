// ignore_for_file: prefer_initializing_formals
// Public constructor parameter names (`dio`, `cache`, `deviceIdProvider`,
// `now`) are fixed by the design contract and differ from the private field
// names by more than the leading underscore, so an explicit assignment list
// is required instead of `this._dio` etc.
import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../config/constants.dart';
import '../models/license_state.dart';
import 'device_id.dart';

/// Persists the most recent [LicenseState] as JSON in shared_preferences.
class LicenseCache {
  LicenseCache(SharedPreferencesAsync prefs) : _prefs = prefs;

  final SharedPreferencesAsync _prefs;

  static const String _kKey = 'gazer.license.state';

  /// Returns the cached state, or `null` if nothing has ever been written.
  Future<LicenseState?> read() async {
    final json = await _prefs.getString(_kKey);
    if (json == null) return null;
    return LicenseState.fromJson(jsonDecode(json) as Map<String, dynamic>);
  }

  /// Overwrites the cached state with [s].
  Future<void> write(LicenseState s) async {
    await _prefs.setString(_kKey, jsonEncode(s.toJson()));
  }
}

/// App-local client for the PenguinTech license server's Gazer-facing API
/// (temporary bridge pending promotion into `flutter_libs` — see the
/// design spec's "TEMPORARY BRIDGE" decision).
///
/// Never throws: every failure path degrades to a cached or `unknown`
/// [LicenseState] instead of propagating an exception to the caller.
class LicenseClient {
  LicenseClient({
    required Dio dio,
    required LicenseCache cache,
    required DeviceIdProvider deviceIdProvider,
    required DateTime Function() now,
    this.baseUrl = kLicenseBaseUrl,
  }) : _dio = dio,
       _cache = cache,
       _deviceIdProvider = deviceIdProvider,
       _now = now;

  final Dio _dio;
  final LicenseCache _cache;
  final DeviceIdProvider _deviceIdProvider;
  final DateTime Function() _now;

  /// Base URL for `/validate`, `/features`, `/keepalive`.
  final String baseUrl;

  /// Validates this install and fetches its feature flags.
  ///
  /// Success -> `valid` with fresh flags and `lastFetched = now()`.
  /// Network error with a cache fetched within [kLicenseGracePeriod] ->
  /// `gracePeriod` with the cached flags. Network error with a stale or
  /// absent cache -> `unknown`. A 4xx response -> `invalid`. Any other
  /// failure (including a malformed response body) is swallowed and
  /// treated the same as a network error — this method never throws.
  Future<LicenseState> validateAndFetchFlags() async {
    final deviceId = await _deviceIdProvider.deviceId();
    final cached = await _cache.read();
    try {
      await _dio.post<dynamic>('$baseUrl/validate', data: _payload(deviceId));
      final response = await _dio.post<dynamic>(
        '$baseUrl/features',
        data: _payload(deviceId),
      );
      final rawFlags = Map<String, dynamic>.from(
        (response.data as Map<String, dynamic>)['features'] as Map,
      );
      final flags = rawFlags.map((key, value) => MapEntry(key, value as bool));
      final state = LicenseState(
        status: LicenseStatus.valid,
        flags: flags,
        lastFetched: _now(),
        deviceId: deviceId,
      );
      await _cache.write(state);
      return state;
    } on DioException catch (e) {
      final statusCode = e.response?.statusCode;
      if (statusCode != null && statusCode >= 400 && statusCode < 500) {
        final invalid = LicenseState(
          status: LicenseStatus.invalid,
          flags: cached?.flags ?? const {},
          lastFetched: cached?.lastFetched,
          deviceId: deviceId,
        );
        await _cache.write(invalid);
        return invalid;
      }
      return _offlineFallback(cached, deviceId);
    } catch (_) {
      return _offlineFallback(cached, deviceId);
    }
  }

  /// Fire-and-forget keepalive ping; failures are swallowed silently.
  Future<void> keepalive() async {
    final deviceId = await _deviceIdProvider.deviceId();
    unawaited(_sendKeepalive(deviceId));
  }

  /// Wrapped in its own `async` body so that a synchronous throw from
  /// `_dio.post` (as well as an asynchronous one) is caught the same way —
  /// `catchError` on the bare call only guards a rejected [Future], not a
  /// call that throws before returning one.
  Future<void> _sendKeepalive(String deviceId) async {
    try {
      await _dio.post<dynamic>('$baseUrl/keepalive', data: _payload(deviceId));
    } catch (_) {
      // Fire-and-forget: keepalive failures are never surfaced to the caller.
    }
  }

  LicenseState _offlineFallback(LicenseState? cached, String deviceId) {
    if (cached?.lastFetched != null &&
        _now().difference(cached!.lastFetched!) <= kLicenseGracePeriod) {
      return cached.copyWith(status: LicenseStatus.gracePeriod);
    }
    return LicenseState(
      status: LicenseStatus.unknown,
      flags: cached?.flags ?? const {},
      lastFetched: cached?.lastFetched,
      deviceId: deviceId,
    );
  }

  Map<String, String> _payload(String deviceId) => {
    'device_id': deviceId,
    'product': 'waddlebot',
    'component': 'gazer',
  };
}
