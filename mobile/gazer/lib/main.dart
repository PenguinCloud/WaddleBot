import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

/// Entry point for the Gazer mobile app.
///
/// Wraps [GazerApp] in a [ProviderScope] so every Riverpod provider in the
/// widget tree resolves against the real (non-test) provider graph.
void main() {
  runApp(const ProviderScope(child: GazerApp()));
}
