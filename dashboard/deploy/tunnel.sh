#!/usr/bin/env bash
# Get cloudflared, the Cloudflare Tunnel connector, for "reach the dashboard from away from home".
#
#   bash deploy/tunnel.sh install    use the system cloudflared if there is one, else download the static binary
#   bash deploy/tunnel.sh status     print what is installed, as JSON (used by the dashboard)
#
# The phone settings page runs "install" for you (System → Remote access). Nothing system-wide
# changes: the binary goes to ~/.local/share/watcher-dashboard/bin and runs as a user service.
set -euo pipefail

BIN_DIR="${TUNNEL_BIN_DIR:-$HOME/.local/share/watcher-dashboard/bin}"
RELEASES="${TUNNEL_RELEASES:-https://github.com/cloudflare/cloudflared/releases/latest/download}"

say() { echo "[tunnel] $*"; }

binary() {
  if [ -x "$BIN_DIR/cloudflared" ]; then echo "$BIN_DIR/cloudflared"; return 0; fi
  command -v cloudflared 2>/dev/null && return 0
  return 1
}

cmd_install() {
  local bin
  if bin="$(binary)"; then
    say "cloudflared is already here: $bin ($("$bin" --version 2>/dev/null | head -1))"
    exit 0
  fi
  local arch
  case "$(uname -m)" in
    x86_64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    armv7l|armv6l) arch=arm ;;
    *) say "no cloudflared build for $(uname -m)"; exit 1 ;;
  esac
  command -v curl >/dev/null 2>&1 || { say "curl is missing; install it first"; exit 1; }
  mkdir -p "$BIN_DIR"
  say "downloading cloudflared for linux-$arch (about 40 MB)"
  curl -fsSL -o "$BIN_DIR/cloudflared.tmp" "$RELEASES/cloudflared-linux-$arch"
  chmod 755 "$BIN_DIR/cloudflared.tmp"
  if ! "$BIN_DIR/cloudflared.tmp" --version >/dev/null 2>&1; then
    rm -f "$BIN_DIR/cloudflared.tmp"; say "the download does not run; try again later"; exit 1
  fi
  mv "$BIN_DIR/cloudflared.tmp" "$BIN_DIR/cloudflared"
  say "installed $("$BIN_DIR/cloudflared" --version 2>/dev/null | head -1)"
}

cmd_status() {
  local bin="" ver="" installed=false
  if bin="$(binary)"; then installed=true; ver="$("$bin" --version 2>/dev/null | head -1 | sed -E 's/^cloudflared version ([^ ]+).*/\1/')"; fi
  printf '{"installed":%s,"binary":"%s","version":"%s"}\n' "$installed" "$bin" "$ver"
}

case "${1:-}" in
  install) cmd_install ;;
  status) cmd_status ;;
  *) echo "usage: $0 install|status"; exit 2 ;;
esac
