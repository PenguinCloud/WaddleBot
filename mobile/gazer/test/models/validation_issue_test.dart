import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/models/validation_issue.dart';

void main() {
  group('ValidationIssue equality', () {
    test('two instances with identical field/messageKey are ==', () {
      const a = ValidationIssue(field: 'url', messageKey: 'errorUrlScheme');
      const b = ValidationIssue(field: 'url', messageKey: 'errorUrlScheme');
      expect(a, b);
      expect(a.hashCode, b.hashCode);
    });

    test('differing messageKey breaks equality', () {
      const a = ValidationIssue(field: 'url', messageKey: 'errorUrlScheme');
      const b = ValidationIssue(field: 'url', messageKey: 'errorUrlHost');
      expect(a == b, isFalse);
    });
  });

  test('fields are exposed exactly as constructed', () {
    const issue = ValidationIssue(
      field: 'password',
      messageKey: 'errorAuthBothOrNeither',
    );
    expect(issue.field, 'password');
    expect(issue.messageKey, 'errorAuthBothOrNeither');
  });
}
