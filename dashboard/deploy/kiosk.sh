#!/usr/bin/env bash
# Open the dashboard full-screen in Chromium once the server is answering.
# Started by ~/.config/labwc/autostart (written by deploy/install.sh), by the desktop launcher,
# or by the dashboard server ("Show dashboard on the Pi" on the settings page).
#
# Normal mode is an "app window" that starts full-screen: F11 toggles to a regular window with the
# taskbar, Alt+F4 closes it, and the desktop underneath is a normal Raspberry Pi OS desktop.
# Set display.locked_kiosk: true in config.yaml for a tamper-proof --kiosk window instead.
PORT="${DASHBOARD_PORT:-8080}"
URL="http://localhost:${PORT}/"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Make the Wayland session reachable when launched from the service or a terminal over SSH.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  WAYLAND_DISPLAY="$(ls "$XDG_RUNTIME_DIR" 2>/dev/null | grep -E '^wayland-[0-9]+$' | head -1)"
  export WAYLAND_DISPLAY
fi
[ -z "${DISPLAY:-}" ] && export DISPLAY=:0

# Only one dashboard window at a time.
if pgrep -f -- "--class=watcher-dashboard" >/dev/null 2>&1; then
  echo "dashboard window already open"; exit 0
fi

# Wait for the server (it starts as a systemd service at boot; the desktop may come up first).
for _ in $(seq 1 120); do
  curl -sf "${URL}api/health" >/dev/null 2>&1 && break
  sleep 2
done

# Register as an HDMI-CEC playback device so deploy/screen.sh can put the TV on standby (ignored if unsupported).
if command -v cec-ctl >/dev/null 2>&1; then
  for dev in /dev/cec*; do [ -e "$dev" ] && cec-ctl -d "$dev" --playback -S >/dev/null 2>&1 || true; done
fi

# Find a Chromium-family browser: Raspberry Pi OS and Omarchy ship "chromium"; others vary.
BROWSER=""
for candidate in chromium chromium-browser google-chrome google-chrome-stable; do
  if command -v "$candidate" >/dev/null 2>&1; then BROWSER="$candidate"; break; fi
done
if [ -z "$BROWSER" ] && command -v flatpak >/dev/null 2>&1 && flatpak info org.chromium.Chromium >/dev/null 2>&1; then
  BROWSER="flatpak run org.chromium.Chromium"
fi
if [ -z "$BROWSER" ]; then
  echo "no Chromium or Chrome found; install one and re-run deploy/install.sh"; exit 2
fi

# Hyprland / Omarchy: the idle lock would cover the dashboard after a few quiet minutes.
# Unless display.stop_idle_lock is false, stop hypridle for this login (it comes back next login).
if [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] || ls "$XDG_RUNTIME_DIR"/hypr/*/ >/dev/null 2>&1; then
  KEEP_LOCK="$(grep -E '^\s*stop_idle_lock:\s*false' "$DIR/config.yaml" 2>/dev/null | head -1)"
  if [ -z "$KEEP_LOCK" ] && pgrep -x hypridle >/dev/null 2>&1; then
    pkill -x hypridle || true
  fi
fi

# X11 desktops: keep the screen from blanking under the dashboard.
if [ -z "${WAYLAND_DISPLAY:-}" ] && command -v xset >/dev/null 2>&1; then
  xset s off -dpms >/dev/null 2>&1 || true
fi

# Clear the "Chromium didn't shut down correctly" bubble after a power cut.
PREFS="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PREFS"
fi

LOCKED="$(grep -E '^\s*locked_kiosk:\s*true' "$DIR/config.yaml" 2>/dev/null | head -1)"
if [ -n "$LOCKED" ] || [ "${DASHBOARD_LOCKED:-0}" = "1" ]; then
  MODE=(--kiosk "$URL")
else
  MODE=(--app="$URL" --start-fullscreen)
fi

OZONE=()
if [ -n "${OZONE_PLATFORM:-}" ]; then OZONE=(--ozone-platform="$OZONE_PLATFORM")
elif [ -n "${WAYLAND_DISPLAY:-}" ] && [ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; then OZONE=(--ozone-platform=wayland)
fi

exec $BROWSER \
  "${MODE[@]}" "${OZONE[@]}" \
  --class=watcher-dashboard \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --autoplay-policy=no-user-gesture-required
