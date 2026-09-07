#!/usr/bin/env bash
# Take a PNG of the running Linux desktop build, for eyeballing UI work.
#
# Development scaffolding only -- Linux is not a distribution target. See
# docs/linux-desktop-development.md, which also covers the prerequisites this
# script only checks for.
#
#   ./scripts/screenshot-linux-app.sh [-o OUTPUT.png] [-s SETTLE_SECONDS]
#
# It fails rather than hand back a frame it cannot show to be current: a window
# the compositor has stopped presenting still photographs, as the same old frame
# (Issue #73, docs/linux-desktop-development.md 4.2).
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

# The lock screen and the blank screen are the same thing to us: mutter stops
# presenting the window behind them, and everything below would then be looking
# at a frame from before it happened. Asked before the app is even built so the
# answer is a sentence rather than a timeout, and again on both sides of the
# shutter, because a lock landing in those last seconds is exactly the shape of
# Issue #73. An answer we cannot get (no GNOME on the bus) reads as unlocked:
# this is the early, precise diagnosis, and the repaint check below is the
# guarantee that does not depend on anyone answering.
session_is_locked() {
  [[ "$(gdbus call --session --dest org.gnome.ScreenSaver \
      --object-path /org/gnome/ScreenSaver \
      --method org.gnome.ScreenSaver.GetActive 2>/dev/null)" == *true* ]]
}

locked_bail() {
  echo "the session is locked or blanked, so the window behind it is not being" >&2
  echo "presented and anything photographed now is an old frame. Unlock it (a" >&2
  echo "password is needed) and run again -- docs/linux-desktop-development.md 4.2." >&2
  exit 1
}

session_is_locked && locked_bail

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
# Every frame this script reads goes through one scratch file, including the
# shutter frame, and the output path is written only once that frame has passed
# the freshness checks below. Dropping an earlier run's PNG up front is part of
# the same contract: after any run, that path holds this run's frame or nothing.
sample="$(mktemp --suffix=.png)"
mkdir -p "$(dirname "$output")"
rm -f "$output"
"$BUNDLE" >/dev/null 2>&1 &
app_pid=$!
# Waits for the group to actually drain, not just for the app: uvicorn shuts
# down gracefully and keeps the app-data lock for a moment longer, which is
# long enough to fail the *next* run with "already running".
teardown() {
  rm -f "$sample"
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

# `import` cannot photograph a window that is not mapped yet, and the toplevel
# exists for a moment before mutter maps it, so waiting for the name alone
# hands the next step a window it cannot read.
window_is_viewable() {
  [[ "$(xwininfo -name "$WINDOW_NAME" -stats 2>/dev/null)" == *IsViewable* ]]
}

# One frame of the window, reduced to something two calls can compare.
frame_hash() {
  import -silent -window "$WINDOW_NAME" "$sample" 2>/dev/null &&
    md5sum <"$sample" | cut -d' ' -f1
}

# What `import` hands back is whatever the compositor last kept for the window,
# and mutter stops handing out frame callbacks as soon as the window is not
# being presented -- session locked or blanked, window minimised, another
# workspace in front. Flutter then blocks in eglSwapBuffers and draws nothing
# more, while `import` keeps succeeding and keeps returning that one frozen
# frame. That is how three runs of this script, in three separate processes and
# with three different settle times, produced byte-identical PNGs of the splash
# screen (Issue #73). Nothing downstream can tell such a frame from a fresh one,
# so the window has to prove it is live before the shutter.
#
# The splash screen's CircularProgressIndicator is the one thing on screen that
# is guaranteed to move, and it is up for exactly as long as we are waiting for
# the sidecar anyway.
#
# Three samples, because two consecutive intervals have to show movement. One
# interval would not do: a window that froze on startup still changes once, from
# bare to the single frame it managed to draw, and a check that accepted one
# change would call that alive.
splash_frame=''
window_is_repainting() {
  local first second third
  first="$(frame_hash)" || return 1
  sleep 0.2
  second="$(frame_hash)" || return 1
  sleep 0.2
  third="$(frame_hash)" || return 1
  [[ $first != "$second" && $second != "$third" ]] || return 1
  # The oldest of the three, so the reference stays a splash frame even if the
  # home screen happened to arrive while the samples were being taken.
  splash_frame="$first"
}

# The window is mapped on Flutter's first frame, not at startup
# (my_application.cc), so this already waits out engine warm-up. The sidecar
# gets far longer: a first launch runs every Alembic migration against a new
# database (sidecarStartupTimeout in app/lib/core/sidecar_supervisor.dart).
wait_for "the app window" 60 window_is_viewable
wait_for "the window to be repainted" 30 window_is_repainting || {
  cat >&2 <<'HINT'
the window is not being repainted, so `import` can only return a stale frame.
mutter stops presenting a window that is not on screen: unlock the session and
wake the display, and make sure the window is neither minimised nor behind
another workspace. See docs/linux-desktop-development.md 4.2.

The other way to reach a screen that never moves is the "already running" error
screen, which replaces the splash when a leftover sidecar still holds app-data:
`pgrep -af auto-scoring-sidecar` (docs/linux-desktop-development.md 5.1).
HINT
  exit 1
}
wait_for "the sidecar to start serving" 90 sidecar_is_serving
sleep "$settle_seconds"

session_is_locked && locked_bail
import -silent -window "$WINDOW_NAME" "$sample"
session_is_locked && locked_bail
# The startup overlay is gone by now, so the shutter frame cannot legitimately
# match the splash frame the check above left behind. If it does, the window
# stopped being presented in between and this is that same old frame again.
[[ "$(md5sum <"$sample" | cut -d' ' -f1)" != "$splash_frame" ]] || {
  cat >&2 <<'HINT'
the captured frame is byte-identical to the splash frame sampled during startup,
so the window stopped being presented after it was checked. See
docs/linux-desktop-development.md 4.2.
HINT
  exit 1
}

mv "$sample" "$output"
echo "wrote $output"
