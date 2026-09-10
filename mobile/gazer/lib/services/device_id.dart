// ignore_for_file: prefer_initializing_formals
// The public constructor parameter names (`deviceInfo`, `packageInfo`) are
// fixed by the design contract and differ from the private field names
// (`_deviceInfo`, `_packageInfo`) by more than the leading underscore
// convention allows for an initializing formal, so an explicit assignment
// list is required here instead of `this._deviceInfo`.
import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Resolves the stable per-install device identifier used by `LicenseClient`.
abstract class DeviceIdProvider {
  /// Returns a stable, hex-encoded identifier for this install.
  Future<String> deviceId();
}

/// Resolves the device identifier as SHA-256 of `'<androidId>:<packageName>'`,
/// hex-encoded.
///
/// `device_info_plus` does not expose the raw platform
/// `Settings.Secure.ANDROID_ID` value; [AndroidDeviceInfo.id] (the build
/// fingerprint ID) is the closest stable identifier reachable through the
/// two dependencies this class is constructed with, per the design
/// contract's exact constructor signature.
class AndroidDeviceIdProvider implements DeviceIdProvider {
  AndroidDeviceIdProvider({
    required DeviceInfoPlugin deviceInfo,
    required PackageInfo packageInfo,
  }) : _deviceInfo = deviceInfo,
       _packageInfo = packageInfo;

  final DeviceInfoPlugin _deviceInfo;
  final PackageInfo _packageInfo;

  @override
  Future<String> deviceId() async {
    final androidInfo = await _deviceInfo.androidInfo;
    final raw = '${androidInfo.id}:${_packageInfo.packageName}';
    return sha256.convert(utf8.encode(raw)).toString();
  }
}
