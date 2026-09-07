#!/usr/bin/env bash
# Take a PNG of the running Linux desktop build, for eyeballing UI work.
#
# Development scaffolding only -- Linux is not a distribution target. See
# docs/linux-desktop-development.md, which also covers the prerequisites this
# script only checks for.
#
#   ./scripts/screenshot-linux-app.sh [-o OUTPUT.png] [-s SETTLE_SECONDS]
#
# Runs against the desktop session's Xwayland server, the same display
# docs/orca-remote-environment.md §1.1 (b) already relies on, so a GNOME
# session has to be logged in. A virtual display would be the better answer
# and does not work: see §4 of the doc above for why Xvfb cannot render this
# app at all.
set -euo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# gtk_window_set_title()/gtk_header_bar_set_title() in
# app/linux/runner/my_application.cc. Not MaterialApp's title: the Flutter
# Linux embedder never pushes that to the window.
readonly WINDOW_NAME=auto_scoring_app

readonly BUNDLE="$REPO_ROOT/app/build/linux/x64/debug/bundle/auto_scoring_app"

output="$REPO_ROOT/app/build/linux-screenshot.png"
# Time between the sidecar answering and the shutter. Dismissing the startup
# overlay is one setState, so this only has to cover a frame or two.
settle_seconds=2

while getopts ':o:s:h' option; do
  case "$option" in
    o) output="$OPTARG" ;;
    s) settle_seconds="$OPTARG" ;;
    h) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//;$d'; exit 0 ;;
    *) echo "usage: $0 [-o OUTPUT.png] [-s SETTLE_SECONDS]" >&2; exit 2 ;;
  esac
done

for tool in import xwininfo curl; do
  command -v "$tool" >/dev/null ||
    { echo "$tool is not installed -- see docs/linux-desktop-development.md §1" >&2; exit 1; }
done

export DISPLAY="${DISPLAY:-:0}"

# Mutter names its Xwayland auth file with a fresh random suffix per session,
# so it can only be found at run time (docs/orca-remote-environment.md §1.1).
# Already-set values win: outside a Wayland desktop there is nothing to find.
if [[ -z ${XAUTHORITY:-} && -n ${XDG_RUNTIME_DIR:-} ]]; then
  for candidate in "$XDG_RUNTIME_DIR"/.mutter-Xwaylandauth.*; do
    [[ -f $candidate ]] && { export XAUTHORITY="$candidate"; break; }
  done
fi

xwininfo -root >/dev/null 2>&1 ||
  { echo "cannot reach the X display $DISPLAY -- is a desktop session logged in?" >&2; exit 1; }

# Forces the app onto Xwayland instead of letting GTK pick the Wayland
# backend. A native Wayland client has no X window, and every capture tool
# here speaks X.
export GDK_BACKEND=x11

# Incremental, so this is a no-op once the bundle is up to date. Building here
# rather than asking the caller to remember keeps this one command.
(cd "$REPO_ROOT/app" && flutter build linux --debug)

# Job control, so the app gets a process group of its own and the trap below
# can take the sidecar down with it. Necessary because ChildProcessGroup is a
# deliberate no-op off Windows (app/lib/core/child_process_group.dart), and a
# sidecar that outlives the app keeps its lock on app-data/ -- which makes the
# *next* run fail with "already running".
set -m

# From the repository root, so the sidecar resolves through the third
# candidate of sidecarExecutableCandidates() in app/lib/core/sidecar_paths.dart
# (backend/.venv) exactly as `flutter run` from app/ resolves through the
# second.
cd "$REPO_ROOT"
"$BUNDLE" >/dev/null 2>&1 &
app_pid=$!
# Waits for the group to actually drain, not just for the app: uvicorn shuts
# down gracefully and keeps the app-data lock for a moment longer, which is
# long enough to fail the *next* run with "already running".
teardown() {
  kill -- -"$app_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
  local deadline=$((SECONDS + 15))
  while pgrep -g "$app_pid" >/dev/null 2>&1 && ((SECONDS < deadline)); do sleep 0.2; done
}
trap teardown EXIT

# Polls rather than sleeps, because both things worth waiting for are
# observable and one long sleep would silently photograph the splash screen
# whenever the machine is slow.
wait_for() {
  local what="$1" timeout="$2"
  shift 2
  local deadline=$((SECONDS + timeout))
  until "$@" >/dev/null 2>&1; do
    kill -0 "$app_pid" 2>/dev/null || { echo "the app exited before $what" >&2; return 1; }
    ((SECONDS < deadline)) || { echo "timed out after ${timeout}s waiting for $what" >&2; return 1; }
    sleep 0.25
  done
}

# `/healthz` answering is the same signal SidecarSupervisor waits for before
# it leaves SidecarStarting and the startup overlay uncovers the home screen,
# so this waits for the screen actually worth photographing. The port has to
# be discovered rather than asked for: the sidecar is started with `--port 0`
# and reports what it got through a handshake file the app deletes on sight.
#
# Waiting on the listening socket alone is not enough -- uvicorn binds it
# before running the startup work, so an early shutter catches the splash.
sidecar_is_serving() {
  local sidecar_pid port
  sidecar_pid="$(pgrep -P "$app_pid" | head -n 1)"
  [[ -n $sidecar_pid ]] || return 1
  port="$(ss -ltnpH | grep "pid=${sidecar_pid}," | grep -oP ':\K[0-9]+(?= )' | head -n 1)"
  [[ -n $port ]] || return 1
  curl -sfo /dev/null "http://127.0.0.1:${port}/healthz"
}

# The window is mapped on Flutter's first frame, not at startup
# (my_application.cc), so this already waits out engine warm-up. The sidecar
# gets far longer: a first launch runs every Alembic migration against a new
# database (sidecarStartupTimeout in app/lib/core/sidecar_supervisor.dart).
wait_for "the app window" 60 xwininfo -name "$WINDOW_NAME"
wait_for "the sidecar to start serving" 90 sidecar_is_serving
sleep "$settle_seconds"

mkdir -p "$(dirname "$output")"
import -silent -window "$WINDOW_NAME" "$output"
echo "wrote $output"
