import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Restarting the sidecar, as a feature screen is allowed to ask for it
/// (Issue #96).
///
/// The sidecar builds its AI provider chain once, at startup, from the
/// credentials that existed then -- so a key saved on the settings screen
/// does nothing until the process comes back. "Saved, but it will not take
/// effect until you restart the app" is the shape this project keeps
/// deleting: a screen explaining the implementation instead of doing the
/// thing. The app already supervises that process
/// (`core/sidecar_supervisor.dart`, whose `start()` is also §24's 再起動
/// button), so the screen restarts it.
typedef RestartSidecar = Future<void> Function();

/// `null` where this app has no sidecar of its own to restart -- widget
/// tests, and any host that was handed an already-running connection. The
/// screen then says what to do instead of offering a button that cannot
/// work. `main.dart` overrides it with the supervisor's own `start`.
final restartSidecarProvider = Provider<RestartSidecar?>((ref) => null);
