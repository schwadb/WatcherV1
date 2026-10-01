#!/usr/bin/env bash
# One-time setup on the Raspberry Pi. Run from the dashboard folder:
#     cd ~/WatcherV1/dashboard && bash deploy/install.sh
# Safe to run again later (for example after `git pull`).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"
PORT="$(grep -E '^\s*port:' "$DIR/config.yaml" | head -1 | sed -E 's/.*port:\s*([0-9]+).*/\1/' || echo 8080)"
PORT="${PORT:-8080}"
TZ_NAME="$(grep -E '^\s*timezone:' "$DIR/config.yaml" | head -1 | sed -E 's/.*timezone:\s*"?([^"#]+)"?.*/\1/' | xargs || true)"

echo "==> Installing system packages"
sudo apt-get update -qq
PKGS="git python3 python3-venv python3-pip curl fonts-noto-color-emoji"
sudo apt-get install -y -qq $PKGS chromium >/dev/null || sudo apt-get install -y -qq $PKGS chromium-browser >/dev/null

echo "==> Creating the Python environment in $DIR/.venv"
if [ ! -x "$DIR/.venv/bin/python" ]; then
  python3 -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

echo "==> Preparing folders and secrets file"
mkdir -p "$DIR/photos" "$DIR/cache"
if [ ! -f "$DIR/.env" ]; then
  cp "$DIR/.env.example" "$DIR/.env"
  echo "    created $DIR/.env  <-- paste your FINNHUB_API_KEY and OUTLOOK_ICS_URL here"
fi

if [ -n "$TZ_NAME" ] && command -v timedatectl >/dev/null 2>&1; then
  echo "==> Setting the Pi's time zone to $TZ_NAME"
  sudo timedatectl set-timezone "$TZ_NAME" || true
fi

echo "==> Installing the systemd service (starts the server at boot)"
sed -e "s|__USER__|$USER_NAME|g" -e "s|__DIR__|$DIR|g" -e "s|__PORT__|$PORT|g" \
  "$DIR/deploy/dashboard.service" | sudo tee /etc/systemd/system/dashboard.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable dashboard >/dev/null
sudo systemctl restart dashboard

if command -v raspi-config >/dev/null 2>&1; then
  echo "==> Turning off screen blanking"
  sudo raspi-config nonint do_blanking 1 || true
fi

echo "==> Setting up the full-screen browser at login (Wayland/labwc autostart)"
chmod +x "$DIR/deploy/kiosk.sh"
AUTOSTART="$HOME/.config/labwc/autostart"
mkdir -p "$(dirname "$AUTOSTART")"
touch "$AUTOSTART"
if ! grep -q "deploy/kiosk.sh" "$AUTOSTART"; then
  echo "DASHBOARD_PORT=$PORT $DIR/deploy/kiosk.sh &" >> "$AUTOSTART"
fi
# Older images (X11 / LXDE) use a different autostart file; add it there too if that folder exists.
LX_AUTOSTART="$HOME/.config/lxsession/LXDE-pi/autostart"
if [ -d "$(dirname "$LX_AUTOSTART")" ] && ! grep -qs "deploy/kiosk.sh" "$LX_AUTOSTART"; then
  echo "@$DIR/deploy/kiosk.sh" >> "$LX_AUTOSTART"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Done. Next steps:"
echo "  1. nano $DIR/.env          (paste your Finnhub key and Outlook ICS link, then Ctrl+O, Enter, Ctrl+X)"
echo "  2. sudo systemctl restart dashboard"
echo "  3. curl http://localhost:$PORT/api/health   (every source should say \"ok\": true within a minute)"
echo "  4. Copy photos into $DIR/photos/"
echo "  5. sudo reboot   -> the dashboard opens full screen"
echo
echo "From another device on your Wi-Fi: http://$(hostname).local:$PORT  or  http://${IP:-<pi-ip>}:$PORT"
echo "Logs: journalctl -u dashboard -f"
