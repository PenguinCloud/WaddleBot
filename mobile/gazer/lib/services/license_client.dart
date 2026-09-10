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
  /// Network error with a cache fetched less than [kLicenseGracePeriod] ago
  /// -> `gracePeriod` with the cached flags. Network error with a stale or
  /// absent cache -> `unknown`. A 4xx response -> `invalid`. Any other
  /// failure — including a malformed response body, a device-id provider
  /// failure, or a corrupted cache — is swallowed and degrades to a cached
  /// or `unknown` result. This method never throws.
  Future<LicenseState> validateAndFetchFlags() async {
    String? deviceId;
    try {
      deviceId = await _deviceIdProvider.deviceId();
    } catch (_) {
      deviceId = null;
    }

    LicenseState? cached;
    try {
      cached = await _cache.read();
    } catch (_) {
      // A corrupted cache is treated exactly like no cache at all.
      cached = null;
    }

    if (deviceId == null) {
      // No device id available: never call the server without a real one
      // -- degrade exactly like a network failure, using the cached device
      // id (if any) only to shape the returned LicenseState, never sent
      // anywhere.
      return _offlineFallback(cached, cached?.deviceId ?? '');
    }

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
        // Cached even though invalid: lastFetched is deliberately left as
        // whatever it was before this call (not reset to `now()`), so
        // `_offlineFallback`'s grace-period math still grades off the last
        // *successful* fetch, not off this invalid response.
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

  /// Fire-and-forget keepalive ping; failures — including a device-id
  /// provider failure — are swallowed silently.
  Future<void> keepalive() async {
    try {
      final deviceId = await _deviceIdProvider.deviceId();
      unawaited(_sendKeepalive(deviceId));
    } catch (_) {
      // No device id available -- nothing to keep alive.
    }
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

  /// Degrades to a cached result when the server can't be reached (or no
  /// device id could be resolved): `gracePeriod` with the cached flags if
  /// [cached] was fetched strictly less than [kLicenseGracePeriod] ago,
  /// otherwise `unknown` with whatever flags [cached] holds (or empty, if
  /// there is no usable cache at all).
  LicenseState _offlineFallback(LicenseState? cached, String deviceId) {
    if (cached?.lastFetched != null &&
        _now().difference(cached!.lastFetched!) < kLicenseGracePeriod) {
      return cached.copyWith(status: LicenseStatus.gracePeriod);
    }
    return LicenseState(
      status: LicenseStatus.unknown,
      flags: cached?.flags ?? const {},
      lastFetched: cached?.lastFetched,
      deviceId: deviceId,
    );
  }

  /// Builds the request body sent to `/validate`, `/features`, and
  /// `/keepalive` — the resolved [deviceId] plus fixed product/component
  /// identifiers identifying this app to the license server.
  Map<String, String> _payload(String deviceId) => {
    'device_id': deviceId,
    'product': 'waddlebot',
    'component': 'gazer',
  };
}
