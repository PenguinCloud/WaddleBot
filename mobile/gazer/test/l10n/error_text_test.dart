import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/l10n/app_localizations_en.dart';
import 'package:gazer/l10n/error_text.dart';
import 'package:gazer/pigeon/pipeline.g.dart';

void main() {
  final AppLocalizationsEn l10n = AppLocalizationsEn();

  test('maps every GazerErrorCode to a non-empty (message, action) pair', () {
    for (final GazerErrorCode code in GazerErrorCode.values) {
      final (String message, String action) = errorTextFor(l10n, code);
      expect(message, isNotEmpty, reason: '$code message');
      expect(action, isNotEmpty, reason: '$code action');
    }
  });

  test('rtmpConnectFailed maps to the connect-failure copy', () {
    final (String message, String action) = errorTextFor(
      l10n,
      GazerErrorCode.rtmpConnectFailed,
    );
    expect(message, 'Could not connect to the streaming server.');
    expect(
      action,
      'Check the URL and your network connection, then try again.',
    );
  });

  test('unknown maps to the generic fallback copy', () {
    final (String message, String action) = errorTextFor(
      l10n,
      GazerErrorCode.unknown,
    );
    expect(message, 'An unexpected error occurred.');
    expect(action, 'Try again; open Status for details.');
  });
}
