import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../pigeon/pipeline.g.dart';

part 'devices_provider.g.dart';

/// The [GazerHostApi] the app talks to; overridden in tests with
/// `FakeGazerHostApi` so no real Pigeon channel is ever touched.
@Riverpod(keepAlive: true)
GazerHostApi gazerHostApi(Ref ref) => GazerHostApi();

/// Enumerable video sources (M1: back/front camera only). M1 has no
/// hot-plug refresh — the list is read once per provider build; USB/UVC
/// device attach-and-refresh arrives in M2.
@riverpod
Future<List<VideoDevice>> videoDevices(Ref ref) async {
  final host = ref.watch(gazerHostApiProvider);
  return host.listVideoDevices();
}

/// Enumerable audio sources (M1: mic + silence only). M1 has no hot-plug
/// refresh — the list is read once per provider build; USB/UVC audio
/// attach-and-refresh arrives in M2.
@riverpod
Future<List<AudioDevice>> audioDevices(Ref ref) async {
  final host = ref.watch(gazerHostApiProvider);
  return host.listAudioDevices();
}
