#!/usr/bin/env bash
# Take a PNG of the running Linux desktop build, for eyeballing UI work.
#
# Development scaffolding only -- Linux is not a distribution target. See
# docs/linux-desktop-development.md, which also covers the prerequisites this
# script only checks for.
#
#   ./scripts/screenshot-linux-app.sh [-o OUTPUT.png] [-s SETTLE_SECONDS]
#                                     [-r ROUTE] [-t light|dark] [-w WIDTHxHEIGHT]
#
#   -r  screen to land on, as a route path (app/lib/core/app_routes.dart).
#       Defaults to ホーム画面. This is how anything but the landing screen gets
#       photographed: the script has no way to click.
#   -t  theme to pin. Defaults to whatever the desktop's colour scheme says,
#       which is the operator's setting and not this script's to change.
#   -w  window size. Defaults to 1280x720, the desktop width the docs use;
#       700x720 is the narrow width they pair it with.
#
# One launch, one screen: an evaluation set is this script in a loop
# (docs/linux-desktop-development.md §4.4).
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
# Time between the requested screen being seen to arrive and the shutter.
# Dismissing the startup overlay is one setState, so this only has to cover a
# frame or two; a screen that loads a PDF wants more.
settle_seconds=2

readonly USAGE="usage: $0 [-o OUTPUT.png] [-s SETTLE_SECONDS] [-r ROUTE] \
[-t light|dark] [-w WIDTHxHEIGHT]"

while getopts ':o:s:r:t:w:h' option; do
  case "$option" in
    o) output="$OPTARG" ;;
    s) settle_seconds="$OPTARG" ;;
    # Passed to the app through the environment, which is where both sides read
    # them: the route and theme in app/lib/main.dart (debug builds only), the
    # size in app/linux/runner/my_application.cc. Checked here rather than
    # there, because a typo that silently falls back to ホーム画面 in the light
    # theme produces a plausible PNG under the wrong file name -- which is worse
    # than no PNG at all.
    r) [[ $OPTARG == /* ]] ||
         { echo "-r takes a route path starting with / (app_routes.dart)" >&2; exit 2; }
       export AUTO_SCORING_INITIAL_ROUTE="$OPTARG" ;;
    t) [[ $OPTARG == light || $OPTARG == dark ]] ||
         { echo "-t takes light or dark" >&2; exit 2; }
       export AUTO_SCORING_THEME="$OPTARG" ;;
    w) [[ $OPTARG =~ ^[0-9]+x[0-9]+$ ]] ||
         { echo "-w takes WIDTHxHEIGHT, e.g. 1280x720" >&2; exit 2; }
       export AUTO_SCORING_WINDOW_SIZE="$OPTARG" ;;
    h) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed 's/^# \?//;$d'; exit 0 ;;
    *) echo "$USAGE" >&2; exit 2 ;;
  esac
done

# Resolved and cleared before anything else can fail, so that every exit path
# below leaves the caller with this run's frame or with nothing -- never with the
# PNG some earlier run left at the same path. A stale file that outlives a failed
# run is the same trap as a stale frame: the caller looks at the path and
# believes what is there.
mkdir -p "$(dirname "$output")"
rm -f "$output"

for tool in import xwininfo xprop curl; do
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

# mutter stops presenting a window the moment it leaves the screen, and Flutter
# then stops drawing, while `import` carries on returning the last frame the
# compositor kept. These are the three ways off the screen that X and the session
# bus can be asked about outright, so they are worth asking rather than inferring.
# A question that cannot be answered (no GNOME on the bus, no window yet) counts
# as "still on screen": this is the direct, early diagnosis, and the startup loop
# further down is the part that does not depend on anyone answering.
window_left_the_screen() {
  local desktop current
  if [[ "$(gdbus call --session --dest org.gnome.ScreenSaver \
        --object-path /org/gnome/ScreenSaver \
        --method org.gnome.ScreenSaver.GetActive 2>/dev/null)" == *true* ]]; then
    echo "the session is locked or blanked"
    return
  fi
  if [[ "$(xprop -name "$WINDOW_NAME" _NET_WM_STATE 2>/dev/null)" == *_NET_WM_STATE_HIDDEN* ]]; then
    echo "the window is minimised"
    return
  fi
  # `|| true` because there is nothing to read before the window exists, and an
  # unanswered question is not an answer of "gone".
  desktop="$(xprop -name "$WINDOW_NAME" _NET_WM_DESKTOP 2>/dev/null | grep -o '[0-9]*$' || true)"
  current="$(xprop -root _NET_CURRENT_DESKTOP 2>/dev/null | grep -o '[0-9]*$' || true)"
  # 0xFFFFFFFF means "on every workspace", which is never the wrong one.
  if [[ -n $desktop && -n $current && $desktop != 4294967295 && $desktop != "$current" ]]; then
    echo "the window is on a workspace other than the one on screen"
  fi
  # This one answers on stdout, so its exit status carries nothing and must not
  # be allowed to look like a failure to `set -e`.
  return 0
}

on_screen_or_bail() {
  local reason
  reason="$(window_left_the_screen)"
  [[ -n $reason ]] || return 0
  cat >&2 <<HINT
$reason, so it is not being redrawn and \`import\` can only hand back the frame
the compositor kept from before. Put it back on screen and run again.
See docs/linux-desktop-development.md 4.2.
HINT
  exit 1
}

# Asked before the app is even built, so a locked session is a sentence rather
# than a timeout.
on_screen_or_bail

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
# shutter frame; the output path is written only once that frame has passed the
# checks below.
sample="$(mktemp --suffix=.png)"
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
# it leaves SidecarStarting and the startup overlay uncovers the screen the run
# asked for, so this waits for the screen actually worth photographing. The
# port has to be discovered rather than asked for: the sidecar is started with
# `--port 0` and reports what it got through a handshake file the app deletes
# on sight.
#
# Waiting on the listening socket alone is not enough -- uvicorn binds it
# before running the startup work, so an early shutter catches the splash.
sidecar_port=''
sidecar_is_serving() {
  local sidecar_pid
  # Found once and kept: the loop below polls this often enough that a pgrep and
  # an ss per call would cost more than the wait it is timing.
  if [[ -z $sidecar_port ]]; then
    sidecar_pid="$(pgrep -P "$app_pid" | head -n 1)"
    [[ -n $sidecar_pid ]] || return 1
    sidecar_port="$(ss -ltnpH | grep "pid=${sidecar_pid}," | grep -oP ':\K[0-9]+(?= )' | head -n 1)"
    [[ -n $sidecar_port ]] || return 1
  fi
  curl -sfo /dev/null "http://127.0.0.1:${sidecar_port}/healthz"
}

# `import` cannot photograph a window that is not mapped yet, and the toplevel
# exists for a moment before mutter maps it, so waiting for the name alone hands
# the next step a window it cannot read.
window_is_viewable() {
  [[ "$(xwininfo -name "$WINDOW_NAME" -stats 2>/dev/null)" == *IsViewable* ]]
}

# One frame of the window, reduced to something two calls can compare.
frame_hash() {
  import -silent -window "$WINDOW_NAME" "$sample" 2>/dev/null &&
    md5sum <"$sample" | cut -d' ' -f1
}

# Milliseconds, because the two moments this has to put in order -- the sidecar
# answering and the screen changing -- are a few hundred apart.
now_ms() { date +%s%3N; }

not_repainting_bail() {
  cat >&2 <<'HINT'
the window stopped redrawing before the requested screen could appear, so `import`
can only return the frame the compositor kept from before it stopped. mutter
stops presenting a window that is not on screen: unlock the session and wake the
display, and make sure the window is neither minimised nor on another workspace.
See docs/linux-desktop-development.md 4.2.
HINT
  exit 1
}

# The window is mapped on Flutter's first frame, not at startup
# (my_application.cc), so this already waits out engine warm-up.
wait_for "the app window" 60 window_is_viewable

# What `import` hands back is whatever the compositor last kept for the window,
# and mutter stops handing out frame callbacks as soon as the window is not being
# presented -- session locked or blanked, window minimised, another workspace in
# front. Flutter then blocks in eglSwapBuffers and draws nothing more, while
# `import` keeps succeeding and keeps returning that one frozen frame. That is how
# three runs of this script, in three separate processes and with three different
# settle times, produced byte-identical PNGs of the splash screen (Issue #73).
#
# What tells a current frame from a kept one is the startup overlay giving way to
# the screen underneath. The app only does that once the sidecar answers, so a
# screen that has moved no earlier than the sidecar came up is a screen still
# being drawn. This loop therefore polls `/healthz` and watches the window at
# the same time, and remembers when each of the two happened.
#
# Two things it deliberately does not do:
#
#   * It does not settle for "this frame differs from the one before it". A
#     window that freezes partway through the splash has already changed several
#     times and every one of those changes was real -- what it cannot do is
#     change once more after the backend is up.
#   * It does not insist on seeing movement either. If the sidecar is already
#     answering when the first sample is taken, the screen is up and static and
#     a healthy run has nothing left to show, so a screen that last moved no
#     earlier than the sidecar counts whether or not we watched it move.
readonly POLL_SECONDS=0.04
readonly FRAME_INTERVAL_MS=120
readonly ON_SCREEN_INTERVAL_MS=500
# How much earlier than `serving_ms` the last change is still allowed to be.
# `serving_ms` is when *we* saw the sidecar answer, and the app polls the same
# endpoint on its own schedule: it can act on an answer up to one of our polls
# before we record one, and then the screen has already changed and will never
# change again. That lag -- not the app's poll interval -- is all this has to
# cover, which is why /healthz is polled far more often than frames are sampled.
readonly SERVING_LAG_MS=120
# Once the backend is up the screen is one setState away, so this is generous.
# It only decides how long a window that will never redraw is waited on.
readonly SCREEN_TIMEOUT_MS=15000
# A screen that never stops changing is still a current screen, so this only
# gives up on waiting for stillness -- it does not give up on the screenshot.
readonly SETTLE_CAP_MS=30000

previous_frame="$(frame_hash || true)"
clock_ms="$(now_ms)"
last_change_ms=$clock_ms
last_frame_ms=$clock_ms
last_on_screen_ms=$clock_ms
serving_ms=''
sidecar_deadline=$((SECONDS + 90))
while :; do
  if [[ -z $serving_ms ]] && sidecar_is_serving; then
    serving_ms="$(now_ms)"
  fi
  clock_ms="$(now_ms)"
  if ((clock_ms - last_frame_ms >= FRAME_INTERVAL_MS)); then
    last_frame_ms=$clock_ms
    frame="$(frame_hash || true)"
    if [[ -n $frame && $frame != "$previous_frame" ]]; then
      previous_frame="$frame"
      last_change_ms=$clock_ms
    fi
  fi
  if [[ -n $serving_ms ]] && ((last_change_ms + SERVING_LAG_MS >= serving_ms)); then
    break
  fi

  kill -0 "$app_pid" 2>/dev/null ||
    { echo "the app exited during startup" >&2; exit 1; }
  # Asked here too, so a window that leaves the screen mid-startup says why
  # instead of running out one of the clocks below.
  if ((clock_ms - last_on_screen_ms >= ON_SCREEN_INTERVAL_MS)); then
    last_on_screen_ms=$clock_ms
    on_screen_or_bail
  fi
  if [[ -n $serving_ms ]] && ((clock_ms - serving_ms > SCREEN_TIMEOUT_MS)); then
    not_repainting_bail
  fi
  ((SECONDS < sidecar_deadline)) || {
    echo "timed out after 90s waiting for the sidecar to start serving" >&2
    echo "if the app is showing \"already running\" instead of the splash, a" >&2
    echo "leftover sidecar still holds app-data: pgrep -af auto-scoring-sidecar" >&2
    echo "(docs/linux-desktop-development.md 5.1)" >&2
    exit 1
  }
  sleep "$POLL_SECONDS"
done

# The screen has arrived but may not have finished arriving: every one of them
# loads from the backend after it is first painted, and 添削レビュー画面 decodes a
# PDF as well. Wait for the picture to hold still rather than sleeping a fixed
# amount and hoping.
settle_ms=$(awk "BEGIN { printf \"%d\", $settle_seconds * 1000 }")
settle_deadline_ms=$((clock_ms + SETTLE_CAP_MS))
while (($(now_ms) - last_change_ms < settle_ms)); do
  clock_ms="$(now_ms)"
  if ((clock_ms > settle_deadline_ms)); then
    echo "the screen is still changing after $((SETTLE_CAP_MS / 1000))s; shooting anyway" >&2
    break
  fi
  if ((clock_ms - last_frame_ms >= FRAME_INTERVAL_MS)); then
    last_frame_ms=$clock_ms
    frame="$(frame_hash || true)"
    if [[ -n $frame && $frame != "$previous_frame" ]]; then
      previous_frame="$frame"
      last_change_ms=$clock_ms
    fi
  fi
  sleep "$POLL_SECONDS"
done

# The loops above proved the window was live while the screen arrived and
# settled. Nothing watches it between that moment and the shutter, though, and a
# window that goes away in that gap freezes on whatever it had drawn by then --
# which is how a screenshot of a half-loaded screen gets taken and believed.
# Asking on both sides of the shutter closes that gap.
on_screen_or_bail
import -silent -window "$WINDOW_NAME" "$sample"
on_screen_or_bail

mv "$sample" "$output"
echo "wrote $output"
