import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/services/device_id.dart';
import 'package:mocktail/mocktail.dart';
import 'package:package_info_plus/package_info_plus.dart';

class _MockDeviceInfoPlugin extends Mock implements DeviceInfoPlugin {}

class _MockAndroidDeviceInfo extends Mock implements AndroidDeviceInfo {}

void main() {
  group('AndroidDeviceIdProvider.deviceId', () {
    test('is sha256("<androidId>:<packageName>") hex-encoded', () async {
      final deviceInfoPlugin = _MockDeviceInfoPlugin();
      final androidInfo = _MockAndroidDeviceInfo();
      when(() => androidInfo.id).thenReturn('abc123');
      when(() => deviceInfoPlugin.androidInfo)
          .thenAnswer((_) async => androidInfo);

      final packageInfo = PackageInfo(
        appName: 'Gazer',
        packageName: 'io.waddlebot.gazer',
        version: '1.0.0',
        buildNumber: '1',
      );

      final provider = AndroidDeviceIdProvider(
        deviceInfo: deviceInfoPlugin,
        packageInfo: packageInfo,
      );

      final id = await provider.deviceId();
      final expected = sha256
          .convert(utf8.encode('abc123:io.waddlebot.gazer'))
          .toString();
      expect(id, expected);
    });

    test('is deterministic across repeated calls', () async {
      final deviceInfoPlugin = _MockDeviceInfoPlugin();
      final androidInfo = _MockAndroidDeviceInfo();
      when(() => androidInfo.id).thenReturn('xyz789');
      when(() => deviceInfoPlugin.androidInfo)
          .thenAnswer((_) async => androidInfo);
      final packageInfo = PackageInfo(
        appName: 'Gazer',
        packageName: 'io.waddlebot.gazer',
        version: '1.0.0',
        buildNumber: '1',
      );
      final provider = AndroidDeviceIdProvider(
        deviceInfo: deviceInfoPlugin,
        packageInfo: packageInfo,
      );

      final first = await provider.deviceId();
      final second = await provider.deviceId();
      expect(first, second);
    });
  });
}
