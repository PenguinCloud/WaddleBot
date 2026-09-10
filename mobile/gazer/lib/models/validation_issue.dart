import 'package:freezed_annotation/freezed_annotation.dart';

part 'validation_issue.freezed.dart';

/// A single settings-validation failure: which [field] failed and an l10n
/// [messageKey] to render (never a hardcoded English string).
///
/// Produced by `TargetValidator.validate`; an empty issue list means the
/// settings are valid and Go Live may proceed.
@freezed
abstract class ValidationIssue with _$ValidationIssue {
  const factory ValidationIssue({
    required String field,
    required String messageKey,
  }) = _ValidationIssue;
}
