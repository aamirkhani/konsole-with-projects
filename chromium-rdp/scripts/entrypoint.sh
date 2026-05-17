#!/usr/bin/env bash
# PID2 inside the container (PID1 is dumb-init). Orchestrates startup of the
# headless GNOME stack so gnome-remote-desktop can serve Chromium over RDP.
#
# Failure model: every subsystem must come up in order. We probe for readiness
# (Wayland socket, RDP port bind) rather than sleep-and-pray, and we surface
# clear errors so healthcheck.sh can identify which subsystem regressed.

set -euo pipefail

log() { printf '[entrypoint %s] %s\n' "$(date -u +%H:%M:%S)" "$*" >&2; }
die() { log "FATAL: $*"; exit 1; }

# Fail fast on missing / default-placeholder RDP_PASSWORD. We do this before
# any subsystem starts so the container exits cleanly rather than booting a
# wide-open service.
[[ -n "${RDP_PASSWORD:-}" ]] || die "RDP_PASSWORD is not set. Pass -e RDP_PASSWORD=... or set it in compose.yaml."
[[ "$RDP_PASSWORD" != "changeme" ]] || die "RDP_PASSWORD is still the placeholder 'changeme'. Pick a real password."

# ---------------------------------------------------------------------------
# 1. Runtime directories
# ---------------------------------------------------------------------------
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"

# Render node must be present and accessible. We don't fail hard here because
# the user may legitimately want llvmpipe for testing, but we log loudly.
if [[ ! -e /dev/dri/renderD128 ]]; then
    log "WARN: /dev/dri/renderD128 not present. GPU acceleration will fall back"
    log "WARN: to software rendering. Pass --device /dev/dri to the container."
elif [[ ! -r /dev/dri/renderD128 ]]; then
    log "WARN: /dev/dri/renderD128 not readable by uid $(id -u). Add render gid."
fi

# Auto-detect VA-API driver if the operator did not pin one.
if [[ -z "${LIBVA_DRIVER_NAME:-}" ]]; then
    if [[ -e /dev/dri/renderD128 ]] && command -v vainfo >/dev/null; then
        # Probe order: iHD (Intel Gen11+), i965 (older Intel), radeonsi (AMD), nvidia.
        for drv in iHD i965 radeonsi nvidia; do
            if LIBVA_DRIVER_NAME="$drv" vainfo >/dev/null 2>&1; then
                export LIBVA_DRIVER_NAME="$drv"
                log "VA-API driver auto-detected: $drv"
                break
            fi
        done
    fi
fi

# ---------------------------------------------------------------------------
# 2. D-Bus session bus
# ---------------------------------------------------------------------------
log "starting session D-Bus"
eval "$(dbus-launch --sh-syntax)"
export DBUS_SESSION_BUS_ADDRESS

# ---------------------------------------------------------------------------
# 3. gnome-keyring (libsecret backend for grdctl credentials storage)
# ---------------------------------------------------------------------------
log "starting gnome-keyring"
# Unlock the keyring non-interactively. The keyring passphrase only protects
# data inside the ephemeral container; the user-facing secret is RDP_PASSWORD.
eval "$(printf '%s' "$KEYRING_PASSWORD" \
    | gnome-keyring-daemon --unlock --components=secrets,pkcs11 --daemonize)"
export GNOME_KEYRING_CONTROL SSH_AUTH_SOCK

# ---------------------------------------------------------------------------
# 4. PipeWire (audio for RDPSND + ScreenCast IPC backend)
# ---------------------------------------------------------------------------
log "starting pipewire stack"
pipewire &
wireplumber &
pipewire-pulse &

# ---------------------------------------------------------------------------
# 5. xdg-desktop-portal + GNOME backend (ScreenCast + RemoteDesktop portals)
# ---------------------------------------------------------------------------
log "starting xdg-desktop-portal"
/usr/libexec/xdg-desktop-portal -r &
/usr/libexec/xdg-desktop-portal-gnome &

# ---------------------------------------------------------------------------
# 6. Mutter as headless Wayland compositor with one virtual monitor
# ---------------------------------------------------------------------------
log "starting mutter headless ($SCREEN_GEOMETRY)"
mutter --headless --wayland --no-x11 \
       --virtual-monitor "$SCREEN_GEOMETRY" \
       --wayland-display "$WAYLAND_DISPLAY" &
# shellcheck disable=SC2034  # read via indirect expansion in the supervisor loop
MUTTER_PID=$!

# Wait for the Wayland socket. Mutter creates it once the headless backend is
# fully initialised; if this never appears, every downstream client will fail.
for i in {1..60}; do
    if [[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]]; then
        log "Wayland socket ready after ${i}*0.5s"
        break
    fi
    sleep 0.5
    if ! kill -0 "$MUTTER_PID" 2>/dev/null; then
        die "mutter died during startup (check logs above; likely missing /dev/dri)"
    fi
    [[ $i -eq 60 ]] && die "Wayland socket never appeared at $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY"
done

# ---------------------------------------------------------------------------
# 7. Provision gnome-remote-desktop (credentials, transport, port)
# ---------------------------------------------------------------------------
log "provisioning gnome-remote-desktop"
/usr/local/bin/provision-grd.sh

# ---------------------------------------------------------------------------
# 8. gnome-remote-desktop daemon (RDP server)
# ---------------------------------------------------------------------------
log "starting gnome-remote-desktop-daemon"
# Force VA-API encode path when available; falls back gracefully otherwise.
export GRD_ENABLE_HW_ACCEL=1
/usr/libexec/gnome-remote-desktop-daemon &
# shellcheck disable=SC2034  # read via indirect expansion in the supervisor loop
GRD_PID=$!

# Wait for grd to bind the RDP port. We use /proc/net/tcp to avoid relying on
# any utility being installed (ss/netstat may be absent in slim derivatives).
port_hex=$(printf '%04X' "$RDP_PORT")
for i in {1..60}; do
    if grep -qiE ":${port_hex}\s.*:0000 0A " /proc/net/tcp /proc/net/tcp6 2>/dev/null; then
        log "RDP port $RDP_PORT bound after ${i}*0.5s"
        break
    fi
    sleep 0.5
    if ! kill -0 "$GRD_PID" 2>/dev/null; then
        die "gnome-remote-desktop-daemon died during startup"
    fi
    [[ $i -eq 60 ]] && die "grd never bound port $RDP_PORT"
done

# ---------------------------------------------------------------------------
# 9. Chromium (the payload)
# ---------------------------------------------------------------------------
log "starting chromium"
/usr/local/bin/launch-chromium.sh &
# shellcheck disable=SC2034  # read via indirect expansion in the supervisor loop
CHROMIUM_PID=$!

# ---------------------------------------------------------------------------
# 10. Supervise
# ---------------------------------------------------------------------------
log "all subsystems up. RDP listening on $RDP_PORT, user=$RDP_USER"
log "supervising; will exit if any critical subsystem dies"

# We treat mutter, grd, and chromium as critical. PipeWire/portal restarts are
# survivable but currently not auto-restarted (out of scope for v1).
trap 'log "received signal, shutting down"; kill 0; wait; exit 0' INT TERM

while true; do
    for pid_name in MUTTER_PID GRD_PID CHROMIUM_PID; do
        pid="${!pid_name}"
        if ! kill -0 "$pid" 2>/dev/null; then
            log "FATAL: $pid_name ($pid) exited"
            kill 0 2>/dev/null || true
            wait 2>/dev/null || true
            exit 1
        fi
    done
    sleep 2
done
