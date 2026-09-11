import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/gazer_settings.dart';
import 'package:gazer/models/license_state.dart';
import 'package:gazer/models/stream_target_settings.dart';
import 'package:gazer/models/validation_issue.dart';
import 'package:gazer/services/feature_flags.dart';
import 'package:gazer/services/settings_validation.dart';

FeatureFlags _flags({required bool rtmpAuth}) => FeatureFlags(
  LicenseState(
    status: LicenseStatus.valid,
    flags: <String, bool>{'waddlebot.gazer.rtmp-auth': rtmpAuth},
    lastFetched: DateTime.utc(2026, 9, 7),
    deviceId: 'test-device',
  ),
);

void main() {
  test('passes through TargetValidator issues unchanged', () {
    final GazerSettings settings = GazerSettings.defaults().copyWith(
      target: const StreamTargetSettings(url: 'not-a-valid-url'),
    );
    final List<ValidationIssue> issues = validateGazerSettings(
      settings,
      _flags(rtmpAuth: true),
    );
    expect(issues, isNotEmpty);
    expect(issues.first.field, 'url');
  });

  test('flags a username/password pair when rtmpAuth is disabled', () {
    final GazerSettings settings = GazerSettings.defaults().copyWith(
      target: const StreamTargetSettings(
        url: 'rtmp://example.com/live/mystream',
        username: 'alice',
        password: 'secret',
      ),
    );
    final List<ValidationIssue> issues = validateGazerSettings(
      settings,
      _flags(rtmpAuth: false),
    );
    expect(
      issues,
      contains(
        const ValidationIssue(
          field: 'username',
          messageKey: 'rtmpAuthDisabled',
        ),
      ),
    );
  });

  test('accepts a username/password pair when rtmpAuth is enabled', () {
    final GazerSettings settings = GazerSettings.defaults().copyWith(
      target: const StreamTargetSettings(
        url: 'rtmp://example.com/live/mystream',
        username: 'alice',
        password: 'secret',
      ),
    );
    final List<ValidationIssue> issues = validateGazerSettings(
      settings,
      _flags(rtmpAuth: true),
    );
    expect(issues, isEmpty);
  });
}
