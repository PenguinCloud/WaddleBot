import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/telemetry/telemetry_config.dart';

void main() {
  group('TelemetryConfig.resolve', () {
    test(
      'a non-empty settings endpoint wins over the --dart-define default',
      () {
        final config = TelemetryConfig.resolve(
          settingsEndpoint: 'http://collector.example.com:4318',
          settingsHeadersJson: '',
          serviceVersion: '1.2.3',
        );
        expect(config.endpoint, 'http://collector.example.com:4318');
        expect(config.serviceVersion, '1.2.3');
        expect(config.serviceName, 'gazer');
        expect(config.deploymentEnvironment, 'dev');
        expect(config.protocol, 'http/json');
      },
    );

    test('an empty settings endpoint falls back to the --dart-define value (empty when unset)', () {
      final config = TelemetryConfig.resolve(
        settingsEndpoint: '',
        settingsHeadersJson: '',
        serviceVersion: '1.2.3',
      );
      expect(config.endpoint, isEmpty);
    });

    test('settings headers parse as comma-separated key=value pairs and win over the define', () {
      final config = TelemetryConfig.resolve(
        settingsEndpoint: '',
        settingsHeadersJson: 'authorization=Bearer abc,x-tenant=demo',
        serviceVersion: '1.2.3',
      );
      expect(config.headers, {
        'authorization': 'Bearer abc',
        'x-tenant': 'demo',
      });
    });

    test('a malformed header pair (no "=") is skipped, not thrown', () {
      final config = TelemetryConfig.resolve(
        settingsEndpoint: '',
        settingsHeadersJson: 'not-a-pair,authorization=ok',
        serviceVersion: '1.2.3',
      );
      expect(config.headers, {'authorization': 'ok'});
    });
  });
}
