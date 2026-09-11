import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/services/permission_gate.dart';
import 'package:mocktail/mocktail.dart';
// `Permission`/`PermissionStatus` (used below) are also exported by
// permission_handler.dart, but that import is flagged `unnecessary_import`
// by `flutter analyze` since every symbol this file uses from it is
// already provided transitively through this platform-interface import.
import 'package:permission_handler_platform_interface/permission_handler_platform_interface.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';

/// Mocktail double for the platform channel `permission_handler` talks to
/// — `MockPlatformInterfaceMixin` disables `PlatformInterface`'s normal
/// `extends`-only enforcement so `Mock` can `implement` it directly (see
/// this task's package-verification note).
class MockPermissionHandlerPlatform extends Mock
    with MockPlatformInterfaceMixin
    implements PermissionHandlerPlatform {}

void main() {
  late MockPermissionHandlerPlatform platform;
  late PermissionHandlerPlatform originalPlatform;

  setUpAll(() {
    registerFallbackValue(<Permission>[]);
  });

  setUp(() {
    originalPlatform = PermissionHandlerPlatform.instance;
    platform = MockPermissionHandlerPlatform();
    PermissionHandlerPlatform.instance = platform;
  });

  tearDown(() {
    PermissionHandlerPlatform.instance = originalPlatform;
  });

  PermissionHandlerGate buildGate({required int sdkInt}) =>
      PermissionHandlerGate(sdkInt: () async => sdkInt);

  test('all granted -> PermissionOutcome.granted', () async {
    when(() => platform.requestPermissions(any())).thenAnswer(
      (_) async => <Permission, PermissionStatus>{
        Permission.camera: PermissionStatus.granted,
        Permission.microphone: PermissionStatus.granted,
      },
    );

    final result = await buildGate(sdkInt: 30).ensureLivePermissions();

    expect(result, PermissionOutcome.granted);
    final requested =
        verify(() => platform.requestPermissions(captureAny())).captured.single
            as List<Permission>;
    expect(
      requested,
      containsAll(<Permission>[Permission.camera, Permission.microphone]),
    );
    expect(requested, isNot(contains(Permission.notification)));
  });

  test(
    'any permanentlyDenied -> PermissionOutcome.permanentlyDenied',
    () async {
      when(() => platform.requestPermissions(any())).thenAnswer(
        (_) async => <Permission, PermissionStatus>{
          Permission.camera: PermissionStatus.permanentlyDenied,
          Permission.microphone: PermissionStatus.granted,
        },
      );

      final result = await buildGate(sdkInt: 33).ensureLivePermissions();

      expect(result, PermissionOutcome.permanentlyDenied);
    },
  );

  test('a plain denial with nothing permanently denied -> PermissionOutcome.denied', () async {
    when(() => platform.requestPermissions(any())).thenAnswer(
      (_) async => <Permission, PermissionStatus>{
        Permission.camera: PermissionStatus.denied,
        Permission.microphone: PermissionStatus.granted,
      },
    );

    final result = await buildGate(sdkInt: 30).ensureLivePermissions();

    expect(result, PermissionOutcome.denied);
  });

  test(
    'sdkInt >= 33 includes Permission.notification in the request',
    () async {
      when(() => platform.requestPermissions(any())).thenAnswer(
        (_) async => <Permission, PermissionStatus>{
          Permission.camera: PermissionStatus.granted,
          Permission.microphone: PermissionStatus.granted,
          Permission.notification: PermissionStatus.granted,
        },
      );

      await buildGate(sdkInt: 33).ensureLivePermissions();

      final requested =
          verify(() => platform.requestPermissions(captureAny()))
                  .captured
                  .single
              as List<Permission>;
      expect(requested, contains(Permission.notification));
    },
  );

  test('sdkInt < 33 never requests Permission.notification', () async {
    when(() => platform.requestPermissions(any())).thenAnswer(
      (_) async => <Permission, PermissionStatus>{
        Permission.camera: PermissionStatus.granted,
        Permission.microphone: PermissionStatus.granted,
      },
    );

    await buildGate(sdkInt: 32).ensureLivePermissions();

    final requested =
        verify(() => platform.requestPermissions(captureAny())).captured.single
            as List<Permission>;
    expect(requested, isNot(contains(Permission.notification)));
  });
}
