import 'dart:async';
import 'dart:io';

// `AppExitResponse` -- the `didRequestAppExit` contract -- is declared in
// dart:ui, and neither material nor widgets re-exports it.
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/sidecar_paths.dart';
import 'package:auto_scoring_app/core/sidecar_platform_io.dart';
import 'package:auto_scoring_app/core/sidecar_supervisor.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/startup/startup_gate.dart';

void main() {
  // Required before `Platform`/`Directory` are touched below, and before
  // `AutoScoringApp` registers a `WidgetsBindingObserver` for the exit hook.
  WidgetsFlutterBinding.ensureInitialized();
  runApp(AutoScoringApp(supervisor: buildSidecarSupervisor()));
}

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
/// it on the way out. Without one it goes straight to [HomePage], which is how
/// widget tests run.
class AutoScoringApp extends StatefulWidget {
  const AutoScoringApp({super.key, this.supervisor, this.dependencies});

  /// Drives sidecar startup and the splash/error overlay. `null` in widget
  /// tests, which have no sidecar to supervise.
  final SidecarSupervisor? supervisor;

  /// Only used when [supervisor] is `null`. With a supervisor the dependencies
  /// come from the live connection it establishes, so passing both would be
  /// ambiguous.
  final AppDependencies? dependencies;

  @override
  State<AutoScoringApp> createState() => _AutoScoringAppState();
}

class _AutoScoringAppState extends State<AutoScoringApp>
    with WidgetsBindingObserver {
  /// Needed to drop pushed routes when the sidecar goes away -- see
  /// [_onSidecarStateChanged].
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  /// Built from the connection the supervisor established, and closed again
  /// whenever the sidecar stops being reachable: a client pins its base URL and
  /// bearer token at construction, and every restart mints new ones.
  SidecarApiClient? _client;
  AppDependencies? _dependencies;

  @override
  void initState() {
    super.initState();
    final supervisor = widget.supervisor;
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
    } else {
      // Drop every pushed route *before* closing the client, because each one
      // captured the `AppDependencies` that existed when it was pushed. Left
      // alone they would go on calling a closed client against a port nothing
      // answers on any more, and a restart -- which mints a fresh port and
      // token -- would never reach them (Issue #24 review round 1, P1).
      //
      // The reviewer loses the screen they were on. That is honest rather than
      // regrettable: the sidecar holding their unsaved edits has died, so the
      // edits are gone either way, and the error screen says so.
      _navigatorKey.currentState?.popUntil((route) => route.isFirst);
      _client?.close();
      _client = null;
      _dependencies = null;
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final supervisor = widget.supervisor;
    if (supervisor == null) {
      return MaterialApp(
        title: 'Auto-Scoring',
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        home: HomePage(
          dependencies: widget.dependencies ?? const AppDependencies(),
        ),
      );
    }

    final dependencies = _dependencies;
    return MaterialApp(
      title: 'Auto-Scoring',
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      navigatorKey: _navigatorKey,
      // An empty Scaffold until the first successful connection: there is no
      // client to give [HomePage] yet, and the overlay is covering everything
      // regardless.
      home: dependencies == null
          ? const Scaffold()
          : HomePage(dependencies: dependencies),
      // Above the Navigator, not inside it, so the error screen and its restart
      // button are visible over whatever the reviewer had pushed.
      builder: (context, child) => SidecarStartupOverlay(
        state: supervisor.state.value,
        onRestart: () => unawaited(supervisor.start()),
        child: child,
      ),
    );
  }
}
