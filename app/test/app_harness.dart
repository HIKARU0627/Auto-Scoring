import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
// `Override` -- the type of a `ProviderScope.overrides` entry -- is not in
// flutter_riverpod's default export set.
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/app_router.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_theme.dart';

/// Pumps the app at [location], with [dependencies] standing in for a live
/// sidecar.
///
/// This is the replacement for the constructor injection screens used to take
/// (`SomePage(dependencies: ...)`): pages are built by the app's own route
/// table now, from their path alone, so `ProviderScope(overrides: ...)` is
/// where a test swaps a collaborator. Anything else a test needs to stand in
/// for -- the native file picker, say -- goes in [overrides] the same way.
///
/// Using the real route table (rather than a `MaterialApp(home: ...)` around
/// one page) also means a test that taps through to another screen exercises
/// the same routes the app does.
///
/// [brightness] picks which of the app's two themes to run under. Almost every
/// test leaves it at light -- `design_tokens_screens_test.dart` is the one that
/// walks the screens under both (Issue #67).
Future<void> pumpAppAt(
  WidgetTester tester,
  String location, {
  AppDependencies dependencies = const AppDependencies(),
  List<Override> overrides = const [],
  Brightness brightness = Brightness.light,
}) {
  // A fresh router per pump: a `GoRouter` owns navigation state, so sharing
  // one between tests would leak the previous test's stack. `MaterialApp.router`
  // does not own the config it is handed, so this disposes it.
  final router = createAppRouter(initialLocation: location);
  addTearDown(router.dispose);
  return tester.pumpWidget(
    wrapWithDependencies(
      // The real theme, not Material's default: screens read design tokens
      // through `ThemeExtension`s that only `AppTheme` installs, so a bare
      // `MaterialApp` here would exercise a widget tree the app never runs
      // (Issue #67).
      MaterialApp.router(
        theme: brightness == Brightness.light
            ? AppTheme.light()
            : AppTheme.dark(),
        routerConfig: router,
      ),
      dependencies: dependencies,
      overrides: overrides,
    ),
  );
}

/// The [ProviderScope] the app runs under, for the few widgets a test builds
/// directly rather than reaching through a route (dialogs, mostly).
Widget wrapWithDependencies(
  Widget child, {
  AppDependencies dependencies = const AppDependencies(),
  List<Override> overrides = const [],
}) {
  return ProviderScope(
    overrides: [
      appDependenciesProvider.overrideWithValue(dependencies),
      ...overrides,
    ],
    child: child,
  );
}
