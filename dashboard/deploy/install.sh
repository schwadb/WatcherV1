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
PKGS="git python3 python3-venv python3-pip curl fonts-noto-color-emoji wlr-randr v4l-utils"
sudo apt-get install -y -qq $PKGS chromium >/dev/null || sudo apt-get install -y -qq $PKGS chromium-browser >/dev/null

echo "==> Creating the Python environment in $DIR/.venv"
if [ ! -x "$DIR/.venv/bin/python" ]; then
  python3 -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

echo "==> Preparing folders, settings and secrets files"
mkdir -p "$DIR/photos" "$DIR/cache" "$DIR/data"
if [ ! -f "$DIR/config.yaml" ]; then
  cp "$DIR/config.example.yaml" "$DIR/config.yaml"
  echo "    created $DIR/config.yaml (your settings; edit it from the settings page)"
fi
if [ ! -f "$DIR/.env" ]; then
  cp "$DIR/.env.example" "$DIR/.env"
  echo "    created $DIR/.env (your secrets; fill them in from the settings page)"
fi

echo "==> Allowing the Reboot button on the settings page (sudo rule limited to reboot)"
echo "$USER_NAME ALL=(root) NOPASSWD: /sbin/reboot" | sudo tee /etc/sudoers.d/dashboard-reboot >/dev/null
sudo chmod 440 /etc/sudoers.d/dashboard-reboot

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
chmod +x "$DIR/deploy/kiosk.sh" "$DIR/deploy/screen.sh"
AUTOSTART="$HOME/.config/labwc/autostart"
mkdir -p "$(dirname "$AUTOSTART")"
touch "$AUTOSTART"
START_AT_LOGIN="$(grep -E '^\s*start_at_login:\s*false' "$DIR/config.yaml" | head -1 || true)"
if [ -z "$START_AT_LOGIN" ] && ! grep -q "deploy/kiosk.sh" "$AUTOSTART"; then
  echo "DASHBOARD_PORT=$PORT $DIR/deploy/kiosk.sh &" >> "$AUTOSTART"
fi

echo "==> Adding the dashboard to the app menu and the desktop"
mkdir -p "$HOME/.local/share/applications" "$HOME/Desktop"
cat > "$HOME/.local/share/applications/watcher-dashboard.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Watcher Dashboard
Comment=Open the wall dashboard full-screen (F11 for a window, Alt+F4 to close)
Exec=env DASHBOARD_PORT=$PORT $DIR/deploy/kiosk.sh
Icon=$DIR/static/icon.png
Terminal=false
Categories=Utility;
DESKTOP
cp "$HOME/.local/share/applications/watcher-dashboard.desktop" "$HOME/Desktop/Watcher Dashboard.desktop"
chmod +x "$HOME/Desktop/Watcher Dashboard.desktop"
command -v gio >/dev/null 2>&1 && gio set "$HOME/Desktop/Watcher Dashboard.desktop" metadata::trusted true 2>/dev/null || true
# Older images (X11 / LXDE) use a different autostart file; add it there too if that folder exists.
LX_AUTOSTART="$HOME/.config/lxsession/LXDE-pi/autostart"
if [ -d "$(dirname "$LX_AUTOSTART")" ] && ! grep -qs "deploy/kiosk.sh" "$LX_AUTOSTART"; then
  echo "@$DIR/deploy/kiosk.sh" >> "$LX_AUTOSTART"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "Done. Everything else happens on the settings page, from your phone:"
echo "    http://$(hostname).local:$PORT/manage      (or http://${IP:-<pi-ip>}:$PORT/manage)"
echo "  1. Settings tab -> Secrets: paste your Finnhub key and your Outlook calendar link"
echo "  2. Photos tab: add photos from your phone"
echo "  3. sudo reboot   -> the dashboard opens full screen on this Pi"
echo
echo "The dashboard itself: http://$(hostname).local:$PORT     Logs: journalctl -u dashboard -f"
