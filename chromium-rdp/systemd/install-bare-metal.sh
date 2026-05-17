#!/usr/bin/env bash
# Bare-metal installer for hosts that already run a Linux distro with GNOME
# packages available (Fedora 41+, Ubuntu 24.04+, Debian 13+, RHEL 10+).
#
# For most operators the containerised path (compose.yaml at the repo root)
# is simpler and isolates the GNOME stack. Use this script when you want the
# Chromium session to share the host's GPU drivers and audio without nested
# user namespaces.

set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 1; }

USER_NAME="${1:-chromium-rdp}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

echo "==> installing packages"
if   command -v dnf >/dev/null; then
    dnf install -y \
        mutter gnome-remote-desktop gnome-keyring \
        xdg-desktop-portal xdg-desktop-portal-gnome xdg-desktop-portal-gtk \
        pipewire pipewire-pulseaudio wireplumber \
        chromium mesa-dri-drivers mesa-va-drivers-freeworld intel-media-driver \
        libei libei-utils libva-utils dbus-tools openssl
elif command -v apt-get >/dev/null; then
    apt-get update
    apt-get install -y \
        mutter gnome-remote-desktop gnome-keyring \
        xdg-desktop-portal xdg-desktop-portal-gnome xdg-desktop-portal-gtk \
        pipewire pipewire-pulse wireplumber \
        chromium-browser mesa-va-drivers intel-media-va-driver \
        libei1 libei-tools vainfo dbus-x11 openssl
else
    echo "unsupported distro; install packages manually" >&2
    exit 1
fi

echo "==> creating user $USER_NAME"
id "$USER_NAME" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$USER_NAME"
usermod -aG video,render "$USER_NAME"
loginctl enable-linger "$USER_NAME"

echo "==> installing scripts to /usr/local/bin"
install -m 0755 "$REPO_ROOT/scripts/entrypoint.sh"      /usr/local/bin/chromium-rdp-entrypoint.sh
install -m 0755 "$REPO_ROOT/scripts/provision-grd.sh"   /usr/local/bin/provision-grd.sh
install -m 0755 "$REPO_ROOT/scripts/launch-chromium.sh" /usr/local/bin/launch-chromium.sh
install -m 0755 "$REPO_ROOT/scripts/healthcheck.sh"     /usr/local/bin/chromium-rdp-healthcheck.sh

echo "==> installing systemd user unit"
USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0755 \
    "$USER_HOME/.config/systemd/user"
install -o "$USER_NAME" -g "$USER_NAME" -m 0644 \
    "$HERE/chromium-rdp.service" \
    "$USER_HOME/.config/systemd/user/chromium-rdp.service"

echo "==> reload + enable"
runuser -u "$USER_NAME" -- env XDG_RUNTIME_DIR="/run/user/$(id -u "$USER_NAME")" \
    systemctl --user daemon-reload
runuser -u "$USER_NAME" -- env XDG_RUNTIME_DIR="/run/user/$(id -u "$USER_NAME")" \
    systemctl --user enable chromium-rdp.service

cat <<EOF

Installed. Before first start:

  1. Set the RDP password:
       sudo machinectl shell ${USER_NAME}@ -- systemctl --user edit chromium-rdp
     and add:
       [Service]
       Environment=RDP_PASSWORD=your-real-password

  2. Start the service:
       sudo machinectl shell ${USER_NAME}@ -- systemctl --user start chromium-rdp

  3. Confirm RDP is listening:
       ss -tln | grep 3389

EOF
