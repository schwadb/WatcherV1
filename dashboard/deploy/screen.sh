#!/usr/bin/env bash
# Turn the dashboard's screen off or on.  Usage: deploy/screen.sh on|off|status
# Works from the dashboard service, cron, SSH, or a terminal on the Pi.
#
# How: on Raspberry Pi OS Bookworm (Wayland/labwc) it switches the HDMI output with wlr-randr.
# If the TV supports HDMI-CEC (Samsung "Anynet+", LG "SimpLink", Sony "Bravia Sync", usually on
# by default) it also puts the TV itself into standby and wakes it again with cec-ctl.
# On Hyprland (Omarchy) it uses hyprctl's dpms switch; on an X11 desktop it falls back to xrandr.
set -u
ACTION="${1:-status}"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -z "${WAYLAND_DISPLAY:-}" ]; then
  # labwc names its socket wayland-0; the older Wayfire desktop used wayland-1
  WAYLAND_DISPLAY="$(ls "$XDG_RUNTIME_DIR" 2>/dev/null | grep -E '^wayland-[0-9]+$' | head -1)"
  export WAYLAND_DISPLAY
fi
OUTPUT="${SCREEN_OUTPUT:-}"
# Hyprland: find the running instance so hyprctl works from the dashboard service too.
if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && [ -d "$XDG_RUNTIME_DIR/hypr" ]; then
  HYPRLAND_INSTANCE_SIGNATURE="$(ls -t "$XDG_RUNTIME_DIR/hypr" 2>/dev/null | head -1)"
  export HYPRLAND_INSTANCE_SIGNATURE
fi
# X11 from a service: point at the user's display.
[ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ] && export DISPLAY=:0
[ -z "${XAUTHORITY:-}" ] && [ -f "$HOME/.Xauthority" ] && export XAUTHORITY="$HOME/.Xauthority"

have() { command -v "$1" >/dev/null 2>&1; }

cec() {  # best effort on every CEC adapter (Pi 4 has /dev/cec0; Pi 5 has one per HDMI port); ignore errors
  have cec-ctl || return 0
  for dev in /dev/cec*; do
    [ -e "$dev" ] || continue
    case "$1" in
      off) cec-ctl -d "$dev" -s --to 0 --standby >/dev/null 2>&1 || true ;;
      on)  cec-ctl -d "$dev" -s --to 0 --image-view-on >/dev/null 2>&1 || true
           cec-ctl -d "$dev" -s --to 0 --active-source phys-addr=1.0.0.0 >/dev/null 2>&1 || true ;;
    esac
  done
}

wayland_output() {
  if [ -n "$OUTPUT" ]; then echo "$OUTPUT"; return; fi
  wlr-randr 2>/dev/null | grep -E '^[A-Za-z]' | awk '{print $1}' | grep -E '^(HDMI|DSI|DP)' | head -1
}

relaunch_kiosk() {
  # After the output comes back, make sure the full-screen browser is still there.
  if ! pgrep -f -- "--class=watcher-dashboard" >/dev/null 2>&1; then
    nohup "$DIR/deploy/kiosk.sh" >/dev/null 2>&1 &
  fi
}

if have hyprctl && [ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ] && hyprctl monitors >/dev/null 2>&1; then
  case "$ACTION" in
    off) hyprctl dispatch dpms off >/dev/null && cec off && echo "screen off (hyprland)" ;;
    on)  cec on; hyprctl dispatch dpms on >/dev/null; relaunch_kiosk; echo "screen on (hyprland)" ;;
    status) hyprctl monitors | grep -E "Monitor|dpmsStatus" ;;
    *) echo "usage: $0 on|off|status"; exit 1 ;;
  esac
elif have wlr-randr && [ -n "${WAYLAND_DISPLAY:-}" ] && [ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; then
  OUT="$(wayland_output)"
  [ -z "$OUT" ] && { echo "no HDMI output found (wlr-randr)"; exit 2; }
  case "$ACTION" in
    off) wlr-randr --output "$OUT" --off && cec off && echo "screen off ($OUT)" ;;
    on)  cec on; wlr-randr --output "$OUT" --on || wlr-randr --output "$OUT" --on --mode 1920x1080; relaunch_kiosk; echo "screen on ($OUT)" ;;
    status) wlr-randr | grep -A3 "^$OUT" ;;
    *) echo "usage: $0 on|off|status"; exit 1 ;;
  esac
elif have xrandr && [ -n "${DISPLAY:-}" ] && xrandr >/dev/null 2>&1; then
  OUT="${OUTPUT:-$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')}"
  case "$ACTION" in
    off) xrandr --output "$OUT" --off && cec off && echo "screen off ($OUT)" ;;
    on)  cec on; xrandr --output "$OUT" --auto; relaunch_kiosk; echo "screen on ($OUT)" ;;
    status) xrandr | grep "$OUT" ;;
    *) echo "usage: $0 on|off|status"; exit 1 ;;
  esac
else
  echo "no display control available here (needs hyprctl, wlr-randr or xrandr with a running desktop)"; exit 2
fi
