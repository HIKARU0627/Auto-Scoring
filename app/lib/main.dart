import 'dart:async';
import 'dart:io';

// `AppExitResponse` -- the `didRequestAppExit` contract -- is declared in
// dart:ui, and neither material nor widgets re-exports it.
import 'dart:ui' show AppExitResponse;

// `kDebugMode` is declared in foundation, which material does not re-export.
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/app_router.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/sidecar_paths.dart';
import 'package:auto_scoring_app/core/sidecar_platform_io.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:auto_scoring_app/features/startup/startup_gate.dart';

void main() {
  // Required before `Platform`/`Directory` are touched below, and before
  // `AutoScoringApp` registers a `WidgetsBindingObserver` for the exit hook.
  WidgetsFlutterBinding.ensureInitialized();
  runApp(AutoScoringApp(supervisor: buildSidecarSupervisor()));
}

/// Where the app lands: ホーム画面, unless a screenshot run named another
/// screen.
///
/// `scripts/screenshot-linux-app.sh` photographs one screen per launch: it
/// starts the app, waits until it can prove the window is being drawn, and
/// shoots (`docs/linux-desktop-development.md` §4). It has no way to click, so
/// without this every screen but ホーム画面 was out of its reach.
///
/// Read from the environment rather than from the command line because the
/// same launch already carries the window size that way
/// (`app/linux/runner/my_application.cc`), and one mechanism is easier to
/// explain than two.
String get _landingRoute =>
    _screenshotEnvironment('AUTO_SCORING_INITIAL_ROUTE') ?? AppRoutes.home;

/// The theme a screenshot run asked for, or `null` to follow the desktop.
///
/// Needed for the same reason as [_landingRoute]: the alternative is
/// flipping the operator's own GNOME colour scheme around the shutter, which
/// changes their whole desktop and stays changed if the run dies partway.
ThemeMode? get _requestedThemeMode =>
    switch (_screenshotEnvironment('AUTO_SCORING_THEME')) {
      'light' => ThemeMode.light,
      'dark' => ThemeMode.dark,
      _ => null,
    };

/// [name] from the environment **in debug builds only**.
///
/// Where the app lands and which theme it wears are not decisions a shipped
/// build may take from its environment. The screenshot script builds
/// `--debug` (`docs/linux-desktop-development.md` §2), so this is on exactly
/// where it is needed, and a release build takes the `null` branch --
/// `kDebugMode` is a compile-time constant. That the branch is then *removed*
/// from a Windows release build has not been measured; what is guaranteed here
/// is only that it is never taken (§4.4).
String? _screenshotEnvironment(String name) =>
    kDebugMode ? Platform.environment[name] : null;

/// The one supervisor the app runs with, resolved against the real filesystem.
///
/// Separate from [main] so the resolution is nameable in a stack trace and so
/// nothing about it depends on `runApp` having happened.
SidecarSupervisor buildSidecarSupervisor() {
  return SidecarSupervisor(
    platform: SidecarPlatformIo(),
    executablePath: resolveSidecarExecutable(
      sidecarExecutableCandidates(
        resolvedExecutable: Platform.resolvedExecutable,
        workingDirectory: Directory.current.path,
        isWindows: Platform.isWindows,
      ),
      exists: (path) => File(path).existsSync(),
    ),
    // No `appDataDirectory`: the sidecar owns that decision -- see
    // `SidecarSupervisor`'s field doc and `docs/windows-distribution.md` §3.
  );
}

/// Application root, and the composition root: the one place allowed to wire
/// `core` and `features` together.
///
/// With a [supervisor] it owns the sidecar's lifetime -- starting it, turning
/// the connection it establishes into the app's [AppDependencies], and killing
/// it on the way out. Without one it goes straight to the landing screen,
/// which is how `widget_test.dart` runs.
///
/// It is also where [appDependenciesProvider] is overridden: every screen
/// resolves its collaborators through that provider, so this is the only place
/// a live [SidecarApiClient] is handed to the feature layer.
class AutoScoringApp extends StatefulWidget {
  const AutoScoringApp({super.key, this.supervisor, this.dependencies});

  /// Drives sidecar startup and the splash/error overlay. `null` in widget
  /// tests, which have no sidecar to supervise.
  final SidecarSupervisor? supervisor;

  /// Only used when [supervisor] is `null`. With a supervisor the dependencies
  /// come from the live connection it establishes, so passing both would be
  /// ambiguous.
  ///
  /// Passed here rather than through a surrounding `ProviderScope`, because
  /// this widget owns the scope that overrides [appDependenciesProvider] --
  /// an outer scope's override would be shadowed by it.
  final AppDependencies? dependencies;

  @override
  State<AutoScoringApp> createState() => _AutoScoringAppState();
}

class _AutoScoringAppState extends State<AutoScoringApp>
    with WidgetsBindingObserver {
  /// Built once and kept: the app's whole navigation state lives in it, and
  /// [_onSidecarStateChanged] drives it directly when the sidecar goes away.
  late final GoRouter _router;

  /// Built from the connection the supervisor established, and closed again
  /// whenever the sidecar stops being reachable: a client pins its base URL and
  /// bearer token at construction, and every restart mints new ones.
  SidecarApiClient? _client;
  AppDependencies? _dependencies;

  @override
  void initState() {
    super.initState();
    final supervisor = widget.supervisor;
    // Without a supervisor there is nothing to wait for, so the app starts at
    // the landing screen; with one it starts on the placeholder the startup
    // overlay covers, and [_onSidecarStateChanged] moves it to the landing
    // screen on the first successful connection.
    _router = createAppRouter(
      initialLocation: supervisor == null ? _landingRoute : AppRoutes.starting,
    );
    if (supervisor == null) return;
    WidgetsBinding.instance.addObserver(this);
    supervisor.state.addListener(_onSidecarStateChanged);
    // Not awaited: `start()` completes only once the sidecar is ready or has
    // failed, and rendering that wait is the whole point of the overlay.
    unawaited(supervisor.start());
  }

  @override
  void dispose() {
    widget.supervisor?.state.removeListener(_onSidecarStateChanged);
    WidgetsBinding.instance.removeObserver(this);
    _client?.close();
    _router.dispose();
    super.dispose();
  }

  @override
  Future<AppExitResponse> didRequestAppExit() async {
    // Flutter asks before closing the window, which is the last point any Dart
    // code runs. On Windows the Job Object would clean up even if this never
    // ran (`core/child_process_group.dart`); this is the orderly path.
    await widget.supervisor?.shutdown();
    return AppExitResponse.exit;
  }

  void _onSidecarStateChanged() {
    final state = widget.supervisor!.state.value;
    if (state is SidecarReady) {
      _client?.close();
      final client = SidecarApiClient(state.connection);
      _client = client;
      _dependencies = AppDependencies.fromClient(client);
      _router.go(_landingRoute);
    } else {
      // Drop every route the reviewer pushed *before* closing the client:
      // each screen resolves `appDependenciesProvider`, which is about to go
      // back to the not-connected default, and would otherwise go on calling a
      // closed client against a port nothing answers on any more -- a restart
      // mints a fresh port and token and would never reach them (Issue #24
      // review round 1, P1). [AppRoutes.starting] replaces the whole stack,
      // which is what `popUntil((route) => route.isFirst)` did before
      // go_router.
      //
      // The reviewer loses the screen they were on. That is honest rather than
      // regrettable: the sidecar holding their unsaved edits has died, so the
      // edits are gone either way, and the error screen says so.
      _router.go(AppRoutes.starting);
      _client?.close();
      _client = null;
      _dependencies = null;
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final supervisor = widget.supervisor;
    return ProviderScope(
      overrides: [
        appDependenciesProvider.overrideWithValue(
          _dependencies ?? widget.dependencies ?? const AppDependencies(),
        ),
      ],
      child: MaterialApp.router(
        title: 'Auto-Scoring',
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        // `ThemeMode.system` is the product behaviour; a screenshot run pins
        // one of the two so both can be photographed without touching the
        // desktop's own colour scheme.
        themeMode: _requestedThemeMode ?? ThemeMode.system,
        routerConfig: _router,
        // Above the Router, not inside it, so the error screen and its restart
        // button are visible over whatever the reviewer had pushed.
        builder: supervisor == null
            ? null
            : (context, child) => SidecarStartupOverlay(
                state: supervisor.state.value,
                onRestart: () => unawaited(supervisor.start()),
                child: child,
              ),
      ),
    );
  }
}
