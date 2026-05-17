#!/usr/bin/env bash
# Container health probe. Returns 0 only when all of:
#   - the Wayland socket exists
#   - gnome-remote-desktop is listening on the configured RDP port
#   - the Chromium process is alive
# This is what `docker inspect --format '{{.State.Health.Status}}'` reads.

set -u

socket="${XDG_RUNTIME_DIR:-/tmp/runtime-rdpuser}/${WAYLAND_DISPLAY:-wayland-0}"
port="${RDP_PORT:-3389}"
port_hex="$(printf '%04X' "$port")"

fail() { printf 'unhealthy: %s\n' "$*"; exit 1; }

[[ -S "$socket" ]] \
    || fail "Wayland socket missing at $socket"

grep -qiE ":${port_hex}\s.*:0000 0A " /proc/net/tcp /proc/net/tcp6 2>/dev/null \
    || fail "no LISTEN on RDP port $port"

pgrep -x chromium >/dev/null || pgrep -x chromium-browser >/dev/null \
    || fail "no Chromium process"

printf 'healthy: wayland=ok rdp=%s chromium=ok\n' "$port"
