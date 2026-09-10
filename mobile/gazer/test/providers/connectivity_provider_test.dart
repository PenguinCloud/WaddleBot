import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:gazer/providers/connectivity_provider.dart';
import 'package:mocktail/mocktail.dart';

class _MockConnectivity extends Mock implements Connectivity {}

void main() {
  test('isOnlineProvider is true when any result is not none', () async {
    final connectivity = _MockConnectivity();
    when(() => connectivity.onConnectivityChanged)
        .thenAnswer((_) => Stream.value([ConnectivityResult.wifi]));
    final container = ProviderContainer(
      overrides: [connectivityProvider.overrideWithValue(connectivity)],
    );
    addTearDown(container.dispose);
    // isOnlineProvider is autoDispose. A bare `container.read(x.future)`
    // takes out a temporary listener and drops it the instant the future
    // resolves, which (riverpod 3.4.3) schedules the element's auto-dispose
    // via its internal scheduler; that scheduled task then races
    // `addTearDown`'s full `container.dispose()` and throws "was disposed
    // during loading state, yet no value could be emitted." Holding an
    // explicit listener open for the rest of the test keeps the listener
    // count above zero, so no auto-dispose is ever scheduled — the
    // container's own dispose is the sole, race-free teardown.
    container.listen(isOnlineProvider, (_, _) {});

    final result = await container.read(isOnlineProvider.future);

    expect(result, isTrue);
  });

  test('isOnlineProvider is false when the only result is none', () async {
    final connectivity = _MockConnectivity();
    when(() => connectivity.onConnectivityChanged)
        .thenAnswer((_) => Stream.value([ConnectivityResult.none]));
    final container = ProviderContainer(
      overrides: [connectivityProvider.overrideWithValue(connectivity)],
    );
    addTearDown(container.dispose);
    // See the comment in the first test.
    container.listen(isOnlineProvider, (_, _) {});

    final result = await container.read(isOnlineProvider.future);

    expect(result, isFalse);
  });
}
