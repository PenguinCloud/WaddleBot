import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../pigeon/pipeline.g.dart';

/// Lists selectable video sources (M1: back/front camera only) as
/// radio-style tiles.
///
/// [devices] comes from `videoDevicesProvider`; [selectedId] is the
/// currently-chosen `VideoDevice.id`; [onSelected] fires with the tapped
/// device's id.
class SourcePicker extends StatelessWidget {
  const SourcePicker({
    super.key,
    required this.devices,
    required this.selectedId,
    required this.onSelected,
  });

  final List<VideoDevice> devices;
  final String? selectedId;
  final ValueChanged<String> onSelected;

  String _labelFor(AppLocalizations l10n, VideoDevice d) {
    return switch (d.kind) {
      VideoDeviceKind.backCamera => l10n.sourceBackCameraLabel,
      VideoDeviceKind.frontCamera => l10n.sourceFrontCameraLabel,
      VideoDeviceKind.uvcCamera2 || VideoDeviceKind.uvcLibuvc => d.name,
    };
  }

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    // `RadioListTile.groupValue`/`onChanged` were deprecated in Flutter
    // 3.32 in favour of a single `RadioGroup` ancestor managing the whole
    // group — see radio_list_tile.dart's deprecation notice. `onChanged`
    // only ever fires with a non-null id here since none of these tiles
    // are toggleable.
    return RadioGroup<String>(
      groupValue: selectedId,
      onChanged: (String? id) {
        if (id != null) onSelected(id);
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Text(
              l10n.sourcePickerTitle,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          for (final VideoDevice d in devices)
            Semantics(
              label: l10n.sourceTileSemanticsLabel(_labelFor(l10n, d)),
              selected: d.id == selectedId,
              button: true,
              child: RadioListTile<String>(
                // 'camera:back' gets the fixed integration_test key; every
                // other tile still gets a stable per-device key so the list
                // never relies on Flutter's positional fallback.
                key: d.id == 'camera:back'
                    ? const Key('backCameraOption')
                    : ValueKey(d.id),
                value: d.id,
                title: Text(_labelFor(l10n, d)),
              ),
            ),
        ],
      ),
    );
  }
}
