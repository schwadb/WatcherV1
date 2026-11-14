#!/usr/bin/env bash
# Install or update God's Eye View (github.com/bilawalsidhu/gods-eye-view), the 3D globe the
# dashboard shows behind the ☰ → Globe button.
#
#   bash deploy/globe.sh install    clone/update the app, get Node.js 24 if needed, install its packages
#   bash deploy/globe.sh status     print what is installed, as JSON (used by the dashboard)
#   bash deploy/globe.sh node-bin   print the folder holding the node/npm to use
#
# The phone settings page runs "install" for you (Settings → God's Eye View globe → Install).
# Nothing system-wide is changed: the app lives in ~/Applications/gods-eye-view and, when the
# computer has no Node.js 24/26, a private copy of Node 24 goes to ~/.local/share/watcher-dashboard/node.
set -euo pipefail

REPO="https://github.com/bilawalsidhu/gods-eye-view.git"
APP_DIR="${GLOBE_DIR:-$HOME/Applications/gods-eye-view}"
NODE_DIR="${GLOBE_NODE_DIR:-$HOME/.local/share/watcher-dashboard/node}"
NODE_DIST="${GLOBE_NODE_DIST:-https://nodejs.org/dist/latest-v24.x}"
PORT="${GLOBE_PORT:-4173}"

say() { echo "[globe] $*"; }

node_major() { "$1" -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/'; }

# The node/npm to use: a private Node 24 if one was downloaded, else the system one if it is 24 or 26.
node_bin() {
  if [ -x "$NODE_DIR/bin/node" ]; then echo "$NODE_DIR/bin"; return 0; fi
  local sys; sys="$(command -v node 2>/dev/null || true)"
  if [ -n "$sys" ]; then
    local major; major="$(node_major "$sys")"
    case "$major" in 24|26) dirname "$sys"; return 0 ;; esac
  fi
  return 1
}

fetch_node() {
  local arch
  case "$(uname -m)" in
    x86_64) arch=x64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) say "no Node.js download for $(uname -m); install Node.js 24 yourself and run this again"; exit 1 ;;
  esac
  local sums tarball
  say "downloading Node.js 24 (the app needs Node 24 or 26; this computer has $(node -v 2>/dev/null || echo none))"
  sums="$(curl -fsSL "$NODE_DIST/SHASUMS256.txt")"
  tarball="$(echo "$sums" | grep -oE "node-v24\.[0-9]+\.[0-9]+-linux-$arch\.tar\.xz" | head -1)"
  [ -n "$tarball" ] || { say "could not find a linux-$arch build at $NODE_DIST"; exit 1; }
  local tmp; tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/$tarball" "$NODE_DIST/$tarball"
  (cd "$tmp" && echo "$sums" | grep " $tarball\$" | sha256sum -c --quiet -) || { say "checksum mismatch for $tarball"; rm -rf "$tmp"; exit 1; }
  rm -rf "$NODE_DIR"; mkdir -p "$NODE_DIR"
  tar -xJf "$tmp/$tarball" -C "$NODE_DIR" --strip-components=1
  rm -rf "$tmp"
  say "Node.js $("$NODE_DIR/bin/node" -v) is in $NODE_DIR (used only by the globe)"
}

cmd_install() {
  for tool in git curl tar xz; do command -v "$tool" >/dev/null 2>&1 || { say "$tool is missing; install it first (Arch: sudo pacman -S $tool)"; exit 1; }; done
  mkdir -p "$(dirname "$APP_DIR")"
  if [ -d "$APP_DIR/.git" ]; then
    say "updating $APP_DIR"
    git -C "$APP_DIR" pull --ff-only --quiet || say "could not fast-forward; keeping the current version"
  else
    say "downloading God's Eye View into $APP_DIR (about 450 MB with its packages)"
    git clone --depth 1 --quiet "$REPO" "$APP_DIR"
  fi
  local bin
  if ! bin="$(node_bin)"; then fetch_node; bin="$NODE_DIR/bin"; fi
  say "using Node.js $("$bin/node" -v) from $bin"
  say "installing the app's packages (a few minutes the first time)"
  (cd "$APP_DIR" && PATH="$bin:$PATH" npm ci --no-audit --no-fund --loglevel=error)
  if [ ! -f "$APP_DIR/.env" ]; then cp "$APP_DIR/.env.example" "$APP_DIR/.env"; fi
  if grep -qE '^PORT=' "$APP_DIR/.env"; then sed -i -E "s/^PORT=.*/PORT=$PORT/" "$APP_DIR/.env"; else printf '\nPORT=%s\n' "$PORT" >> "$APP_DIR/.env"; fi
  say "done. God's Eye View is installed; the dashboard can start it now."
}

cmd_status() {
  local installed=false bin="" ver=""
  [ -f "$APP_DIR/package.json" ] && [ -d "$APP_DIR/node_modules" ] && installed=true
  if bin="$(node_bin 2>/dev/null)"; then ver="$("$bin/node" -v)"; else bin=""; fi
  printf '{"dir":"%s","installed":%s,"node":"%s","node_version":"%s"}\n' "$APP_DIR" "$installed" "$bin" "$ver"
}

case "${1:-}" in
  install) cmd_install ;;
  status) cmd_status ;;
  node-bin) node_bin ;;
  *) echo "usage: $0 install|status|node-bin"; exit 2 ;;
esac
