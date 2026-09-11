import 'package:device_info_plus/device_info_plus.dart';
import 'package:permission_handler/permission_handler.dart';

/// Outcome of requesting the permissions Gazer needs before streaming.
enum PermissionOutcome {
  /// Every needed permission was granted.
  granted,

  /// At least one permission was denied, but the user can still be asked
  /// again — no "don't ask again" was recorded.
  denied,

  /// At least one permission was permanently denied; the only way
  /// forward is the system app settings page.
  permanentlyDenied,
}

/// Requests the runtime permissions Gazer needs before Go Live can start
/// the native pipeline.
///
/// Implementations must never throw — a failed permission check degrades
/// to [PermissionOutcome.denied] rather than crashing the app.
abstract class PermissionGate {
  /// Requests camera, microphone, and (Android 13+) notification
  /// permission, returning the combined outcome.
  Future<PermissionOutcome> ensureLivePermissions();
}

/// [PermissionGate] backed by `permission_handler`.
///
/// `Permission.notification` is only requested on Android 13+ (API 33),
/// where `POST_NOTIFICATIONS` became a runtime permission — [sdkInt] is
/// injected so tests can drive both branches without a real device.
class PermissionHandlerGate implements PermissionGate {
  PermissionHandlerGate({this.sdkInt = _defaultSdkInt});

  /// Returns the Android SDK level; defaults to the real device's via
  /// `device_info_plus`, overridden in tests.
  final Future<int> Function() sdkInt;

  static Future<int> _defaultSdkInt() async {
    final AndroidDeviceInfo info = await DeviceInfoPlugin().androidInfo;
    return info.version.sdkInt;
  }

  @override
  Future<PermissionOutcome> ensureLivePermissions() async {
    try {
      final int sdk = await sdkInt();
      final List<Permission> permissions = <Permission>[
        Permission.camera,
        Permission.microphone,
        if (sdk >= 33) Permission.notification,
      ];
      final Map<Permission, PermissionStatus> statuses = await permissions
          .request();

      if (statuses.values.every((PermissionStatus s) => s.isGranted)) {
        return PermissionOutcome.granted;
      }
      if (statuses.values.any((PermissionStatus s) => s.isPermanentlyDenied)) {
        return PermissionOutcome.permanentlyDenied;
      }
      return PermissionOutcome.denied;
    } catch (_) {
      return PermissionOutcome.denied;
    }
  }
}
