import 'package:flutter/material.dart';
import 'package:flutter_libs/flutter_libs.dart';
import 'package:go_router/go_router.dart';

import 'l10n/app_localizations.dart';
import 'screens/home_screen.dart';
import 'screens/settings_screen.dart';

/// Route table for the app: `'/'` → [HomeScreen], `'/settings'` →
/// [SettingsScreen]. Declared at file scope (rather than inside
/// [GazerApp]) so [GazerApp] stays `const` and tests share one instance.
final GoRouter gazerRouter = GoRouter(
  initialLocation: '/',
  routes: <RouteBase>[
    GoRoute(
      path: '/',
      name: 'home',
      builder: (BuildContext context, GoRouterState state) =>
          const HomeScreen(),
    ),
    GoRoute(
      path: '/settings',
      name: 'settings',
      builder: (BuildContext context, GoRouterState state) =>
          const SettingsScreen(),
    ),
  ],
);

/// Root widget for the Gazer mobile app.
///
/// Wires go_router navigation, the Elder theme, and the generated
/// [AppLocalizations] delegates. `ElderThemeData` (flutter_libs) is a
/// [ThemeExtension], not a [ThemeData], so it is installed via
/// `ThemeData(...).copyWith(extensions: [ElderThemeData.dark])`.
/// `themeMode` is [ThemeMode.system] but both `theme` and `darkTheme` are
/// set to the same Elder-dark [ThemeData], so the app renders dark
/// regardless of the platform brightness setting (house rule: dark
/// default for client apps with a single supported theme).
class GazerApp extends StatelessWidget {
  const GazerApp({super.key});

  static ThemeData get _elderDarkTheme => ThemeData.dark().copyWith(
    scaffoldBackgroundColor: ElderThemeData.dark.pageBackground,
    colorScheme: ThemeData.dark().colorScheme.copyWith(
      primary: ElderThemeData.dark.primaryButton,
      onPrimary: ElderThemeData.dark.primaryButtonText,
      error: ElderThemeData.dark.errorText,
    ),
    extensions: <ThemeExtension<dynamic>>[ElderThemeData.dark],
  );

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      onGenerateTitle: (BuildContext context) =>
          AppLocalizations.of(context).appTitle,
      theme: _elderDarkTheme,
      darkTheme: _elderDarkTheme,
      themeMode: ThemeMode.system,
      routerConfig: gazerRouter,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
    );
  }
}
