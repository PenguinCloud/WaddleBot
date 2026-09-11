import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/app_localizations.dart';
import '../models/gazer_settings.dart';
import '../models/license_state.dart';
import '../models/pipeline_state.dart';
import '../models/stream_stats.dart';
import '../models/update_info.dart';
import '../pigeon/pipeline.g.dart';
import '../providers/connectivity_provider.dart';
import '../providers/devices_provider.dart';
import '../providers/license_provider.dart';
import '../providers/pipeline_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/telemetry_provider.dart';
import '../providers/update_provider.dart';
import '../services/feature_flags.dart';
import '../services/pipeline_controller.dart';
import '../telemetry/gazer_telemetry.dart';
import '../telemetry/telemetry_config.dart';
import '../widgets/masked_text.dart';

/// Width, in logical pixels, at which [HomeScreen] switches from a single
/// controls column (with [StatusPanel] behind [showStatusPanel]'s bottom
/// sheet) to a persistent two-pane layout. Shared as one constant so the
/// two call sites (here and `home_screen.dart`) can never drift apart.
const double kTabletBreakpointWidth = 600;

/// Opens the status panel as a modal bottom sheet on phones (<600dp
/// width). On tablets (≥600dp) this is a no-op — [HomeScreen] already
/// renders [StatusPanel] as a persistent right pane at that breakpoint.
void showStatusPanel(BuildContext context) {
  if (MediaQuery.of(context).size.width >= kTabletBreakpointWidth) return;
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (BuildContext context) =>
        const FractionallySizedBox(heightFactor: 0.85, child: StatusPanel()),
  );
}

/// Full diagnostic panel: camera/UVC/stream state, connection details
/// (secrets masked via [MaskedText]), live stats, connectivity, license
/// status, update notice, and foreground-service state.
///
/// Rendered as a bottom sheet body (<600dp, via [showStatusPanel]) or as
/// [HomeScreen]'s persistent right pane (≥600dp) — the widget itself does
/// not know which; it always renders the same content.
class StatusPanel extends ConsumerWidget {
  const StatusPanel({super.key});

  String _streamStateLabel(AppLocalizations l10n, PipelineState s) {
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

  String _licenseStatusLabel(AppLocalizations l10n, LicenseStatus? status) {
    return switch (status) {
      LicenseStatus.valid => l10n.statusPanelLicenseStatusValid,
      LicenseStatus.gracePeriod => l10n.statusPanelLicenseStatusGracePeriod,
      LicenseStatus.invalid => l10n.statusPanelLicenseStatusInvalid,
      LicenseStatus.unknown => l10n.statusPanelLicenseStatusUnknown,
      null => l10n.statusPanelLicenseStatusUnknown,
    };
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final AppLocalizations l10n = AppLocalizations.of(context);
    final PipelineController controller = ref.watch(pipelineControllerProvider);
    final PipelineState state =
        ref.watch(pipelineStateProvider).value ?? controller.current;
    final StreamStats stats =
        ref.watch(streamStatsProvider).value ?? StreamStats.zero();
    final bool online = ref.watch(isOnlineProvider).value ?? false;
    final AsyncValue<LicenseState> licenseAsync = ref.watch(licenseProvider);
    final FeatureFlags flags = ref.watch(featureFlagsProvider);
    final UpdateInfo? update = ref.watch(updateInfoProvider).value;
    final List<VideoDevice> devices =
        ref.watch(videoDevicesProvider).value ?? const <VideoDevice>[];
    final GazerSettings? settings = ref.watch(settingsProvider).value;
    final AsyncValue<TelemetryConfig> telemetryConfig = ref.watch(
      telemetryConfigProvider,
    );

    final bool cameraOn = state is! IdleState && state is! ErrorState;
    final String? deviceLabel = cameraOn && devices.isNotEmpty
        ? devices.first.name
        : null;
    final Uri? url = settings == null
        ? null
        : Uri.tryParse(settings.target.url);

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              l10n.statusPanelTitle,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const Divider(),
            _row(
              context,
              l10n.statusPanelCameraLabel,
              cameraOn
                  ? l10n.statusPanelCameraOnLabel(deviceLabel ?? '')
                  : l10n.statusPanelCameraOffLabel,
            ),
            _row(
              context,
              l10n.statusPanelUvcLabel,
              l10n.statusPanelUvcNotConnectedLabel,
            ),
            _row(
              context,
              l10n.statusPanelStreamLabel,
              _streamStateLabel(l10n, state),
            ),
            const Divider(),
            Text(
              l10n.statusPanelConnectionLabel,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (settings != null) ...<Widget>[
              _row(
                context,
                l10n.statusPanelConnectionProtocolLabel,
                url?.scheme ?? '',
              ),
              _row(
                context,
                l10n.statusPanelConnectionHostLabel,
                url?.host ?? '',
              ),
              _row(
                context,
                l10n.statusPanelConnectionPathLabel,
                url?.path ?? '',
              ),
              // Wrap, not Row: MaskedText sizes itself to its full text
              // plus a reveal IconButton and does not shrink, so at the
              // ≥600dp breakpoint's narrower pane widths a Row here can
              // request more width than is available and throw a
              // `RenderFlex overflowed` assertion. Wrap instead drops the
              // key onto its own line when the pane is too narrow for
              // both on one line, never overflowing.
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                children: <Widget>[
                  Text(l10n.statusPanelConnectionKeyLabel),
                  MaskedText(
                    value: settings.target.streamKey ?? '',
                    revealSemanticsLabel: l10n.revealStreamKeyLabel,
                  ),
                ],
              ),
              _row(
                context,
                l10n.statusPanelConnectionAuthLabel,
                (settings.target.username?.isNotEmpty ?? false)
                    ? l10n.statusPanelConnectionAuthYes
                    : l10n.statusPanelConnectionAuthNo,
              ),
            ],
            const Divider(),
            Text(
              l10n.statusPanelStatsLabel,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            Text(
              l10n.statusPanelBitrateLabel(stats.currentBitrateKbps.toString()),
            ),
            Text(l10n.statusPanelFpsLabel(stats.fps.toStringAsFixed(1))),
            Text(
              l10n.statusPanelDroppedFramesLabel(
                stats.droppedFrames.toString(),
              ),
            ),
            Text(
              l10n.statusPanelUptimeLabel(stats.uptime.inSeconds.toString()),
            ),
            Text(
              l10n.statusPanelReconnectCountLabel(
                stats.reconnectCount.toString(),
              ),
            ),
            Text(
              l10n.statusPanelCongestionLabel(
                stats.congestionPercent.toStringAsFixed(0),
              ),
            ),
            const Divider(),
            _row(
              context,
              l10n.statusPanelConnectivityLabel,
              online
                  ? l10n.statusPanelOnlineLabel
                  : l10n.statusPanelOfflineLabel,
            ),
            const Divider(),
            Text(
              l10n.statusPanelLicenseLabel,
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (!flags.hasFetchedOnce)
              Text(l10n.statusPanelLicenseFetchingLabel)
            else ...<Widget>[
              _row(
                context,
                l10n.statusPanelLicenseLabel,
                _licenseStatusLabel(l10n, licenseAsync.value?.status),
              ),
              if (licenseAsync.value?.lastFetched != null)
                Text(
                  l10n.statusPanelLicenseLastFetchedLabel(
                    licenseAsync.value!.lastFetched!.toIso8601String(),
                  ),
                ),
            ],
            const Divider(),
            if (update == null)
              Text(l10n.statusPanelUpdateNoneLabel)
            else
              Semantics(
                link: true,
                label: l10n.statusPanelUpdateAvailableLabel(
                  update.latestVersion,
                ),
                child: InkWell(
                  onTap: () =>
                      _openReleaseUrl(context, update.releaseUrl, l10n),
                  child: Text(
                    l10n.statusPanelUpdateAvailableLabel(update.latestVersion),
                    style: const TextStyle(
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
              ),
            const Divider(),
            _row(
              context,
              l10n.statusPanelForegroundServiceLabel,
              state is! IdleState
                  ? l10n.statusPanelForegroundServiceActiveLabel
                  : l10n.statusPanelForegroundServiceInactiveLabel,
            ),
            const Divider(),
            _row(
              context,
              l10n.statusPanelTelemetryLabel,
              (telemetryConfig.value?.endpoint.isNotEmpty ?? false)
                  ? (GazerTelemetry.exportFailures > 0 &&
                            GazerTelemetry.exportSuccesses == 0
                        ? l10n.statusPanelTelemetryFailedLabel
                        : l10n.statusPanelTelemetryExportingLabel)
                  : l10n.statusPanelTelemetryDisabledLabel,
            ),
          ],
        ),
      ),
    );
  }

  /// Label/value line used throughout the panel.
  ///
  /// [value] is wrapped in a [Flexible] with a single-line ellipsis rather
  /// than a bare [Text]: at the ≥600dp breakpoint the panel can render as
  /// a narrow persistent pane (a 2:1 [Row] split leaves as little as
  /// ~200dp on some tablet widths), and several values here are
  /// user/server-controlled length (e.g. `statusPanelUvcNotConnectedLabel`,
  /// a connection host) — an unconstrained trailing [Text] would throw a
  /// `RenderFlex overflowed` assertion rather than gracefully truncating.
  Widget _row(BuildContext context, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: <Widget>[
          Expanded(child: Text(label)),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.end,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }

  /// Opens [url] via `url_launcher`, guarded against both known-unlaunchable
  /// URLs and launch failure: checks [canLaunchUrl] first, catches any
  /// [PlatformException] the platform channel itself throws, and also
  /// checks [launchUrl]'s own returned success flag — any of the three
  /// failure paths shows a [SnackBar] with [AppLocalizations.updateOpenFailed]
  /// instead of silently doing nothing. `context.mounted` is re-checked
  /// after every `await` since this runs from a tap handler that can
  /// outlive the widget (e.g. the panel's bottom sheet dismissed mid-launch).
  Future<void> _openReleaseUrl(
    BuildContext context,
    Uri url,
    AppLocalizations l10n,
  ) async {
    final ScaffoldMessengerState messenger = ScaffoldMessenger.of(context);
    bool launched = false;
    try {
      if (await canLaunchUrl(url)) {
        launched = await launchUrl(url);
      }
    } on PlatformException {
      launched = false;
    }
    if (!launched && context.mounted) {
      messenger.showSnackBar(SnackBar(content: Text(l10n.updateOpenFailed)));
    }
  }
}
