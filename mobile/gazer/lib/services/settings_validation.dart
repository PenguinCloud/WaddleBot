import '../config/flag_keys.dart';
import '../models/gazer_settings.dart';
import '../models/validation_issue.dart';
import '../services/feature_flags.dart';
import '../services/target_validator.dart';

/// Combines [TargetValidator]'s structural checks with the license gate
/// the contract's Go Live rule requires: a username/password pair is
/// only valid when `FlagKeys.rtmpAuth` is enabled for this license tier.
///
/// Both [HomeScreen]'s enablement check and Task 15's `SettingsScreen`
/// call this — never `TargetValidator` alone — so the two screens can
/// never disagree about validity.
List<ValidationIssue> validateGazerSettings(
  GazerSettings settings,
  FeatureFlags flags,
) {
  final List<ValidationIssue> issues = <ValidationIssue>[
    ...const TargetValidator().validate(settings.target),
  ];
  final bool hasAuthPair =
      (settings.target.username?.isNotEmpty ?? false) ||
      (settings.target.password?.isNotEmpty ?? false);
  if (hasAuthPair && !flags.isEnabled(FlagKeys.rtmpAuth)) {
    issues.add(
      const ValidationIssue(field: 'username', messageKey: 'rtmpAuthDisabled'),
    );
  }
  return issues;
}
