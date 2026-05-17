#!/usr/bin/env bash
# Configure gnome-remote-desktop before its daemon starts.
#
# grdctl writes to GSettings (org.gnome.desktop.remote-desktop.rdp) and stores
# credentials via libsecret (which is why gnome-keyring must already be running
# and unlocked at this point).

set -euo pipefail

log() { printf '[provision-grd] %s\n' "$*" >&2; }

: "${RDP_USER:?RDP_USER must be set}"
: "${RDP_PASSWORD:?RDP_PASSWORD must be set}"
: "${RDP_PORT:?RDP_PORT must be set}"

# Credentials. grdctl will encrypt and persist via libsecret.
grdctl rdp set-credentials "$RDP_USER" "$RDP_PASSWORD"

# Listening port. Default is 3389 but operators may need to relocate it.
grdctl rdp set-port "$RDP_PORT"

# Generate a self-signed TLS cert+key if none provided. RDP mandates TLS for
# the security negotiation; without these grd refuses to start.
CERT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-remote-desktop/rdp"
mkdir -p "$CERT_DIR"
if [[ ! -s "$CERT_DIR/tls.crt" || ! -s "$CERT_DIR/tls.key" ]]; then
    log "generating self-signed TLS cert for RDP"
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -subj "/CN=chromium-rdp" \
        -keyout "$CERT_DIR/tls.key" \
        -out    "$CERT_DIR/tls.crt" 2>/dev/null
    chmod 0600 "$CERT_DIR/tls.key"
fi
grdctl rdp set-tls-cert "$CERT_DIR/tls.crt"
grdctl rdp set-tls-key  "$CERT_DIR/tls.key"

# Interaction model: the user is driving the session, not just observing.
grdctl rdp disable-view-only

# Enable the RDP service so the daemon serves on start.
grdctl rdp enable

log "grd configured: port=$RDP_PORT user=$RDP_USER cert=$CERT_DIR/tls.crt"
log "current status:"
grdctl status --show-credentials=no 2>&1 | sed 's/^/    /'
