import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/pipeline_state.dart';

/// Colour-coded chip summarising the current [PipelineState].
///
/// Tapping it invokes [onTap] — [HomeScreen] wires this to
/// `showStatusPanel`. Colours: idle/ready/stopping = grey, preparing =
/// amber, connecting = blue, streaming = green, reconnecting = orange,
/// error = red (per spec).
class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.state, required this.onTap});

  final PipelineState state;
  final VoidCallback onTap;

  Color _colorFor(PipelineState s) {
    return switch (s) {
      IdleState() => Colors.grey,
      PreparingState() => Colors.amber,
      ReadyState() => Colors.grey,
      ConnectingState() => Colors.blue,
      StreamingState() => Colors.green,
      ReconnectingState() => Colors.orange,
      StoppingState() => Colors.grey,
      ErrorState() => Colors.red,
    };
  }

  String _labelFor(AppLocalizations l10n, PipelineState s) {
    return switch (s) {
      IdleState() => l10n.statusChipIdleLabel,
      PreparingState() => l10n.statusChipPreparingLabel,
      ReadyState() => l10n.statusChipReadyLabel,
      ConnectingState() => l10n.statusChipConnectingLabel,
      StreamingState() => l10n.statusChipStreamingLabel,
      ReconnectingState() => l10n.statusChipReconnectingLabel,
      StoppingState() => l10n.statusChipStoppingLabel,
      ErrorState() => l10n.statusChipErrorLabel,
    };
  }

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    final String label = _labelFor(l10n, state);
    return Semantics(
      key: const Key('statusChip'),
      label: l10n.statusChipSemanticsLabel(label),
      button: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Chip(
          backgroundColor: _colorFor(state),
          label: Text(label, style: const TextStyle(color: Colors.black)),
        ),
      ),
    );
  }
}
