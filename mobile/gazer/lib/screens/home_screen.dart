import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../config/flag_keys.dart';
import '../l10n/app_localizations.dart';
import '../l10n/error_text.dart';
import '../models/gazer_settings.dart';
import '../models/pipeline_state.dart';
import '../models/validation_issue.dart';
import '../pigeon/pipeline.g.dart';
import '../providers/devices_provider.dart';
import '../providers/license_provider.dart';
import '../providers/pipeline_provider.dart';
import '../providers/settings_provider.dart';
import '../services/feature_flags.dart';
import '../services/pipeline_controller.dart';
import '../services/settings_validation.dart';
import '../widgets/source_picker.dart';
import '../widgets/status_chip.dart';
import 'status_panel.dart';

/// Landing screen: source picker, Go Live / Stop controls, and the status
/// chip that opens [showStatusPanel].
///
/// The selected video device id is local widget state (M1 has no
/// persisted "last camera" preference); everything else is read from
/// Riverpod providers so the screen re-renders on every pipeline/settings
/// change.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  String? _selectedDeviceId;

  /// Invokes [PipelineController.goLive] and surfaces the two exceptions
  /// it documents as possible ([StateError] on re-entrancy/wrong-state,
  /// [ArgumentError] on validation) as a [SnackBar] — both are races
  /// against this screen's own enablement check (e.g. the pipeline state
  /// or device list changed between build and tap), not expected in
  /// normal operation, so the controller's own message is not surfaced
  /// verbatim; a single localized fallback covers both.
  Future<void> _handleGoLive({
    required PipelineController controller,
    required GazerSettings settings,
    required List<VideoDevice> devices,
    required FeatureFlags flags,
    required OutputOrientation orientation,
  }) async {
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);
    final AppLocalizations l10n = AppLocalizations.of(context);
    try {
      await controller.goLive(
        settings,
        devices: devices,
        videoDeviceId: _selectedDeviceId!,
        flags: flags,
        orientation: orientation,
      );
    } on StateError catch (_) {
      if (!mounted) return;
      messenger.showSnackBar(SnackBar(content: Text(l10n.goLiveFailedMessage)));
    } on ArgumentError catch (_) {
      if (!mounted) return;
      messenger.showSnackBar(SnackBar(content: Text(l10n.goLiveFailedMessage)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    final List<VideoDevice> devices =
        ref.watch(videoDevicesProvider).value ?? const <VideoDevice>[];
    final GazerSettings? settings = ref.watch(settingsProvider).value;
    final FeatureFlags flags = ref.watch(featureFlagsProvider);
    final PipelineController controller = ref.watch(pipelineControllerProvider);
    final PipelineState state =
        ref.watch(pipelineStateProvider).value ?? controller.current;

    if (_selectedDeviceId == null && devices.isNotEmpty) {
      _selectedDeviceId = devices.first.id;
    }

    final List<ValidationIssue> issues = settings == null
        ? const <ValidationIssue>[]
        : validateGazerSettings(settings, flags);
    final bool canGoLive =
        settings != null &&
        issues.isEmpty &&
        flags.hasFetchedOnce &&
        flags.isEnabled(FlagKeys.cameraStream) &&
        _selectedDeviceId != null &&
        (state is IdleState || state is ReadyState || state is ErrorState);
    final bool showStop =
        state is ConnectingState ||
        state is StreamingState ||
        state is ReconnectingState;

    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.homeScreenTitle),
        actions: <Widget>[
          Semantics(
            label: l10n.settingsButtonLabel,
            button: true,
            child: IconButton(
              key: const Key('settingsGearButton'),
              icon: const Icon(Icons.settings),
              tooltip: l10n.settingsButtonLabel,
              onPressed: () => context.push('/settings'),
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: <Widget>[
            StatusChip(state: state, onTap: () => showStatusPanel(context)),
            const SizedBox(height: 16),
            Expanded(
              child: SourcePicker(
                devices: devices,
                selectedId: _selectedDeviceId,
                onSelected: (String id) =>
                    setState(() => _selectedDeviceId = id),
              ),
            ),
            if (state is ErrorState) _ErrorBanner(error: state.error),
            const SizedBox(height: 16),
            if (showStop)
              Semantics(
                label: l10n.stopButtonSemanticsLabel,
                button: true,
                child: FilledButton(
                  key: const Key('stopButton'),
                  onPressed: () => controller.stop(),
                  child: Text(l10n.stopButtonLabel),
                ),
              )
            else
              Semantics(
                label: l10n.goLiveButtonSemanticsLabel,
                button: true,
                child: FilledButton(
                  key: const Key('goLiveButton'),
                  onPressed: canGoLive
                      ? () => _handleGoLive(
                          controller: controller,
                          settings: settings,
                          devices: devices,
                          flags: flags,
                          orientation:
                              MediaQuery.orientationOf(context) ==
                                  Orientation.portrait
                              ? OutputOrientation.portrait
                              : OutputOrientation.landscape,
                        )
                      : null,
                  child: Text(l10n.goLiveButtonLabel),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

/// Shows the localized message + action text for the current [GazerError].
class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.error});

  final GazerError error;

  @override
  Widget build(BuildContext context) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    final (String message, String action) = errorTextFor(l10n, error.code);
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(message),
            const SizedBox(height: 4),
            Text(action, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
    );
  }
}
