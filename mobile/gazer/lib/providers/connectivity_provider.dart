import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'connectivity_provider.g.dart';

/// The [Connectivity] instance the app queries; overridden in tests with a
/// mock that emits a scripted sequence of results.
@Riverpod(keepAlive: true)
Connectivity connectivity(Ref ref) => Connectivity();

/// Online/offline indicator shown in the status panel: true whenever the
/// device reports any connectivity result other than [ConnectivityResult.none].
@riverpod
Stream<bool> isOnline(Ref ref) {
  final connectivityInstance = ref.watch(connectivityProvider);
  return connectivityInstance.onConnectivityChanged.map(
    (results) => results.any((r) => r != ConnectivityResult.none),
  );
}
