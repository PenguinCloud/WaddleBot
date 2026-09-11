import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';

/// Opens the status panel as a modal bottom sheet.
///
/// Initial version for Task 14's HomeScreen wiring — shows only the
/// panel title. Task 16 extends both this function and [StatusPanel]
/// with the full diagnostic panel and the ≥600dp side-pane behaviour.
void showStatusPanel(BuildContext context) {
  showModalBottomSheet<void>(
    context: context,
    builder: (BuildContext context) => const StatusPanel(),
  );
}

/// Initial status panel body — Task 16 extends this with the full diagnostic content.
class StatusPanel extends StatelessWidget {
  const StatusPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(
          l10n.statusPanelTitle,
          style: Theme.of(context).textTheme.titleLarge,
        ),
      ),
    );
  }
}
