import '../models/stream_target_settings.dart';
import '../models/validation_issue.dart';

/// Validates a [StreamTargetSettings] against the RTMP/RTMPS target rules
/// from the design spec, and computes the final connect URL (with the
/// stream key folded into the path) via [effectiveUrl].
///
/// Stateless and side-effect free: never logs, never touches storage or
/// the network. `PipelineController.goLive` calls [validate] before ever
/// touching the native pipeline.
class TargetValidator {
  const TargetValidator();

  /// Returns the list of validation problems with [t]; empty means valid.
  ///
  /// Checks, in order: the URL parses with an `rtmp`/`rtmps` scheme, a
  /// non-empty host, at least one non-empty path segment, and that
  /// username/password are both present or both absent.
  List<ValidationIssue> validate(StreamTargetSettings t) {
    final issues = <ValidationIssue>[];
    final uri = Uri.tryParse(t.url);

    if (uri == null || (uri.scheme != 'rtmp' && uri.scheme != 'rtmps')) {
      issues.add(
        const ValidationIssue(field: 'url', messageKey: 'errorUrlScheme'),
      );
    } else {
      if (uri.host.isEmpty) {
        issues.add(
          const ValidationIssue(field: 'url', messageKey: 'errorUrlHost'),
        );
      }
      final hasPath = uri.pathSegments.any((segment) => segment.isNotEmpty);
      if (!hasPath) {
        issues.add(
          const ValidationIssue(field: 'url', messageKey: 'errorUrlPath'),
        );
      }
    }

    final hasUsername = (t.username ?? '').isNotEmpty;
    final hasPassword = (t.password ?? '').isNotEmpty;
    if (hasUsername != hasPassword) {
      issues.add(
        const ValidationIssue(
          field: 'auth',
          messageKey: 'errorAuthBothOrNeither',
        ),
      );
    }

    return issues;
  }

  /// The final URL passed to the native `start()` call: [t]'s url with
  /// its stream key folded into the path (appended once, leading slash on
  /// the key normalised away, no trailing-slash duplication).
  ///
  /// Never logs its input or output — the result may contain the stream
  /// key, which is a secret.
  static String effectiveUrl(StreamTargetSettings t) {
    final key = t.streamKey?.trim();
    if (key == null || key.isEmpty) {
      return t.url;
    }
    final normalizedKey = key.startsWith('/') ? key.substring(1) : key;
    final trimmedUrl = t.url.endsWith('/')
        ? t.url.substring(0, t.url.length - 1)
        : t.url;
    final lastSegment = trimmedUrl.split('/').last;
    if (lastSegment == normalizedKey) {
      return trimmedUrl;
    }
    return '$trimmedUrl/$normalizedKey';
  }
}
