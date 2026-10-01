#!/usr/bin/env bash
# Launch Chromium full-screen on the dashboard once the server is answering.
# Started by ~/.config/labwc/autostart (written by deploy/install.sh).
PORT="${DASHBOARD_PORT:-8080}"
URL="http://localhost:${PORT}/"

# Wait for the server (it starts as a systemd service at boot; the desktop may come up first).
for _ in $(seq 1 120); do
  curl -sf "${URL}api/health" >/dev/null 2>&1 && break
  sleep 2
done

# Register as an HDMI-CEC playback device so deploy/screen.sh can put the TV on standby (ignored if unsupported).
if [ -e /dev/cec0 ] && command -v cec-ctl >/dev/null 2>&1; then
  cec-ctl -d /dev/cec0 --playback -S >/dev/null 2>&1 || true
fi

# Bookworm ships the package as "chromium"; older images used "chromium-browser".
if command -v chromium >/dev/null 2>&1; then BROWSER=chromium; else BROWSER=chromium-browser; fi

# Clear the "Chromium didn't shut down correctly" bubble after a power cut.
PREFS="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PREFS"
fi

exec "$BROWSER" \
  --kiosk "$URL" \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --autoplay-policy=no-user-gesture-required \
  --start-fullscreen \
  --ozone-platform="${OZONE_PLATFORM:-wayland}"
