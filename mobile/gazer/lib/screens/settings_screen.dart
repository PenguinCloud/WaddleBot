import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';

/// Settings screen for the Gazer app.
///
/// This task provides the navigation shell only (app bar; the back
/// button is supplied automatically by go_router). Task 15 replaces the
/// body with the full target/quality/audio/developer form.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(l10n.settingsScreenTitle)),
      body: const SizedBox.shrink(),
    );
  }
}
