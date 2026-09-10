import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../l10n/app_localizations.dart';

/// Landing screen for the Gazer app.
///
/// This task provides the navigation shell only (app bar + settings gear
/// button). Task 14 replaces the body with the source picker, Go
/// Live/Stop controls, and the status chip.
class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.homeScreenTitle),
        actions: <Widget>[
          Semantics(
            label: l10n.settingsButtonLabel,
            button: true,
            child: IconButton(
              icon: const Icon(Icons.settings),
              tooltip: l10n.settingsButtonLabel,
              onPressed: () => context.push('/settings'),
            ),
          ),
        ],
      ),
      body: const SizedBox.shrink(),
    );
  }
}
