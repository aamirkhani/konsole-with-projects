#!/usr/bin/env bash
# Launch Chromium under the headless Mutter Wayland session.
#
# Flag philosophy: keep the surface minimal but enable every accel path the
# user explicitly asked for — GPU rasterisation, VA-API encode + decode,
# Wayland clipboard (which is how image-clipboard reaches grd's RDPECLIP
# bridge), zero-copy buffers, hardware overlays.
#
# Multi-tab is free at the system level: tabs are an internal Chromium concept
# that does not affect Mutter or grd. State persists via --user-data-dir.

set -euo pipefail

: "${HOME_URL:=about:blank}"
: "${EXTRA_CHROMIUM_FLAGS:=}"

# Which Chromium binary did the distro install? Fedora packages it as
# /usr/bin/chromium-browser via the `chromium` package.
if   command -v chromium-browser >/dev/null; then CHROMIUM=chromium-browser
elif command -v chromium         >/dev/null; then CHROMIUM=chromium
elif command -v google-chrome    >/dev/null; then CHROMIUM=google-chrome
else
    printf '[launch-chromium] no Chromium binary found\n' >&2
    exit 1
fi

# We rely on Ozone/Wayland (UseOzonePlatform is on by default in 117+ but we
# pin it for safety across builds). WaylandClipboard turns on the rich-format
# clipboard path Chromium needs to surface images to wl_data_device, which is
# what grd's RDPECLIP bridge consumes.
FEATURES=(
    UseOzonePlatform
    VaapiVideoDecoder
    VaapiVideoEncoder
    VaapiOnNvidiaGPUs
    WaylandClipboard
    WaylandWindowDecorations
    WebRTCPipeWireCapturer
    AcceleratedVideoEncoder
    AcceleratedVideoDecodeLinuxGL
    AcceleratedVideoDecodeLinuxZeroCopyGL
)
DISABLED_FEATURES=(
    UseChromeOSDirectVideoDecoder
)

ENABLE="$(IFS=,; printf '%s' "${FEATURES[*]}")"
DISABLE="$(IFS=,; printf '%s' "${DISABLED_FEATURES[*]}")"

# shellcheck disable=SC2086  # we want word-splitting on EXTRA_CHROMIUM_FLAGS
exec "$CHROMIUM" \
    --ozone-platform=wayland \
    --enable-features="$ENABLE" \
    --disable-features="$DISABLE" \
    --use-gl=egl \
    --ignore-gpu-blocklist \
    --enable-zero-copy \
    --enable-hardware-overlays \
    --enable-gpu-rasterization \
    --canvas-oop-rasterization \
    --no-first-run \
    --no-default-browser-check \
    --disable-session-crashed-bubble \
    --disable-infobars \
    --user-data-dir=/data/profile \
    --disk-cache-dir=/data/cache \
    --password-store=basic \
    --start-maximized \
    $EXTRA_CHROMIUM_FLAGS \
    "$HOME_URL"
