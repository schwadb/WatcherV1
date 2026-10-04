#!/usr/bin/env bash
# One-time setup. Run from the dashboard folder on the computer that will show the dashboard:
#     cd ~/WatcherV1/dashboard && bash deploy/install.sh
# Works on Raspberry Pi OS, Omarchy / Arch Linux (Hyprland), and Debian/Ubuntu-style desktops.
# Safe to run again later (for example after an update).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(id -un)"

# ---- which kind of computer is this? ---------------------------------------------------------
detect_platform() {
  if grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null || command -v raspi-config >/dev/null 2>&1; then
    echo pi
  elif command -v pacman >/dev/null 2>&1; then
    echo arch
  elif command -v apt-get >/dev/null 2>&1; then
    echo debian
  else
    echo unknown
  fi
}
PLATFORM="${DASHBOARD_PLATFORM:-$(detect_platform)}"
if [ "${1:-}" = "--detect" ]; then echo "$PLATFORM"; exit 0; fi
echo "==> Setting up on: $PLATFORM"

# config.yaml must exist before we read the port and time zone from it
mkdir -p "$DIR/photos" "$DIR/cache" "$DIR/data"
if [ ! -f "$DIR/config.yaml" ]; then
  cp "$DIR/config.example.yaml" "$DIR/config.yaml"
  echo "    created $DIR/config.yaml (your settings; edit them from the settings page)"
fi
if [ ! -f "$DIR/.env" ]; then
  cp "$DIR/.env.example" "$DIR/.env"
  echo "    created $DIR/.env (your secrets; fill them in from the settings page)"
fi
PORT="$(grep -E '^\s*port:' "$DIR/config.yaml" | head -1 | sed -E 's/.*port:\s*([0-9]+).*/\1/' || echo 8080)"
PORT="${PORT:-8080}"
TZ_NAME="$(grep -E '^\s*timezone:' "$DIR/config.yaml" | head -1 | sed -E 's/.*timezone:\s*"?([^"#]+)"?.*/\1/' | xargs || true)"

have_browser() {
  command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1 || \
  command -v google-chrome >/dev/null 2>&1 || command -v google-chrome-stable >/dev/null 2>&1 || \
  { command -v flatpak >/dev/null 2>&1 && flatpak info org.chromium.Chromium >/dev/null 2>&1; }
}

# ---- system packages -------------------------------------------------------------------------
echo "==> Installing system packages"
case "$PLATFORM" in
  pi)
    sudo apt-get update -qq
    PKGS="git python3 python3-venv python3-pip curl fonts-noto-color-emoji wlr-randr v4l-utils"
    sudo apt-get install -y -qq $PKGS chromium >/dev/null || sudo apt-get install -y -qq $PKGS chromium-browser >/dev/null
    ;;
  arch)
    sudo pacman -S --needed --noconfirm python git curl noto-fonts-emoji wlr-randr v4l-utils fuse2 >/dev/null   # fuse2: lets AppImages such as ChronAlert run
    have_browser || sudo pacman -S --needed --noconfirm chromium >/dev/null
    ;;
  debian)
    sudo apt-get update -qq
    sudo apt-get install -y -qq git python3 python3-venv python3-pip curl fonts-noto-color-emoji x11-xserver-utils wlr-randr >/dev/null || \
      sudo apt-get install -y -qq git python3 python3-venv python3-pip curl fonts-noto-color-emoji x11-xserver-utils >/dev/null
    if ! have_browser; then
      sudo apt-get install -y -qq chromium >/dev/null || sudo apt-get install -y -qq chromium-browser >/dev/null || \
        echo "    (!) Could not install Chromium with apt. Install Google Chrome or Chromium yourself, then re-run this script."
    fi
    ;;
  *)
    echo "    (!) Unknown Linux flavour: install python3, git, curl and Chromium yourself, then re-run."
    ;;
esac

# ---- python environment ----------------------------------------------------------------------
echo "==> Creating the Python environment in $DIR/.venv"
if [ ! -x "$DIR/.venv/bin/python" ]; then
  python3 -m venv "$DIR/.venv"
fi
"$DIR/.venv/bin/pip" install --quiet --upgrade pip
"$DIR/.venv/bin/pip" install --quiet -r "$DIR/requirements.txt"

# ---- reboot button -----------------------------------------------------------------------------
REBOOT_BIN="$(command -v reboot || echo /sbin/reboot)"
echo "==> Allowing the Reboot button on the settings page (sudo rule limited to $REBOOT_BIN)"
echo "$USER_NAME ALL=(root) NOPASSWD: $REBOOT_BIN" | sudo tee /etc/sudoers.d/dashboard-reboot >/dev/null
sudo chmod 440 /etc/sudoers.d/dashboard-reboot

if [ -n "$TZ_NAME" ] && command -v timedatectl >/dev/null 2>&1; then
  echo "==> Setting the time zone to $TZ_NAME"
  sudo timedatectl set-timezone "$TZ_NAME" || true
fi

# ---- background service ----------------------------------------------------------------------
echo "==> Installing the systemd service (starts the server at boot)"
sed -e "s|__USER__|$USER_NAME|g" -e "s|__DIR__|$DIR|g" -e "s|__PORT__|$PORT|g" \
  "$DIR/deploy/dashboard.service" | sudo tee /etc/systemd/system/dashboard.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable dashboard >/dev/null
sudo systemctl restart dashboard

if [ "$PLATFORM" = "pi" ] && command -v raspi-config >/dev/null 2>&1; then
  echo "==> Turning off screen blanking"
  sudo raspi-config nonint do_blanking 1 || true
fi

# ---- firewall (Omarchy turns on ufw; phones can't reach the page until the port is open) ---------
if command -v ufw >/dev/null 2>&1 && sudo ufw status 2>/dev/null | grep -qi "status: active"; then
  echo "==> Opening port $PORT in the firewall so phones on your Wi-Fi can reach the dashboard"
  sudo ufw allow "$PORT/tcp" >/dev/null 2>&1 || true
fi

# ---- full-screen dashboard at login ---------------------------------------------------------
chmod +x "$DIR/deploy/kiosk.sh" "$DIR/deploy/screen.sh"
START_AT_LOGIN="$(grep -E '^\s*start_at_login:\s*false' "$DIR/config.yaml" | head -1 || true)"
if [ -z "$START_AT_LOGIN" ]; then
  echo "==> Opening the dashboard full-screen at login"
  DASHBOARD_DIR="$DIR" DASHBOARD_PORT="$PORT" "$DIR/.venv/bin/python" - <<'PY'
import os, sys
sys.path.insert(0, os.environ.get("DASHBOARD_DIR", os.getcwd()))
from app.screen import set_autostart
print("    " + set_autostart(True, int(os.environ.get("DASHBOARD_PORT", "8080"))))
PY
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
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# Find this computer's LAN address (hostname -I is Debian-only; Arch uses ip route).
IP="$( (hostname -I 2>/dev/null || true) | awk '{print $1}' || true)"
[ -z "$IP" ] && IP="$( (ip -4 route get 1.1.1.1 2>/dev/null || true) | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' | head -1 || true)"
HOST="$(hostname 2>/dev/null || echo localhost)"
echo
echo "Done. Everything else happens on the settings page, from your phone:"
echo "    http://$HOST.local:$PORT/manage      (or http://${IP:-<this-computer-ip>}:$PORT/manage)"
echo "  1. Settings tab -> Keys & links: paste your Finnhub key and your Outlook calendar link"
echo "  2. Photos tab: add photos from your phone"
echo "  3. Log out and back in (or reboot) -> the dashboard opens full screen on this computer"
echo
echo "The dashboard itself: http://$HOST.local:$PORT     Logs: journalctl -u dashboard -f"
echo "Open it full-screen right now without logging out:  $DIR/deploy/kiosk.sh &"
