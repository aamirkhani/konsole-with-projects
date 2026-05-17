#!/usr/bin/env bash
# Pre-flight check, run on the HOST before launching the container.
# Validates: kernel, render node, group membership, container runtime,
# loaded VA-API driver, and a tcp-port probe for collisions.

set -u

ok()   { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
warn() { printf '  \033[33mWARN\033[0m %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$*"; FAIL=1; }

FAIL=0

echo "Host pre-flight for chromium-rdp"
echo

# Kernel: modern DRM + Wayland behaviour stabilised on 6.1+. amdgpu and i915
# both want recent kernels for headless GBM allocations.
kver=$(uname -r)
kmajor=${kver%%.*}
kminor=$(printf '%s' "${kver#*.}" | cut -d. -f1)
if (( kmajor > 6 || (kmajor == 6 && kminor >= 1) )); then
    ok "kernel $kver (>= 6.1)"
else
    warn "kernel $kver is older than 6.1; headless GBM may misbehave"
fi

# Render node presence + permission. Without /dev/dri/renderD128 we will fall
# back to llvmpipe and the whole point of the deliverable evaporates.
if [[ -e /dev/dri/renderD128 ]]; then
    if [[ -r /dev/dri/renderD128 ]]; then
        ok "/dev/dri/renderD128 present and readable"
    else
        fail "/dev/dri/renderD128 not readable by $(id -un); add to render group"
    fi
else
    fail "/dev/dri/renderD128 missing; install GPU userspace + drivers on host"
fi

# Container runtime.
if   command -v podman >/dev/null; then ok "container runtime: podman $(podman --version | awk '{print $3}')"
elif command -v docker >/dev/null; then ok "container runtime: docker $(docker --version | awk '{print $3}' | tr -d ,)"
else fail "no podman or docker on PATH"
fi

# VA-API on the host (sanity; the container has its own libva).
if command -v vainfo >/dev/null; then
    if drv_line=$(vainfo 2>&1 | grep -E 'Driver version|vainfo: Driver'); then
        ok "host VA-API: $drv_line"
    else
        warn "host vainfo present but no driver line; check libva-driver install"
    fi
else
    warn "vainfo not installed on host (optional, but useful for debugging)"
fi

# Port collision. If 3389 is already bound, our default mapping will refuse.
if ss -tln 2>/dev/null | grep -qE ':3389\s'; then
    warn "TCP/3389 already in LISTEN on host; remap with -p 13389:3389"
else
    ok "TCP/3389 free on host"
fi

# Firewall hint.
if command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
    if firewall-cmd --query-port=3389/tcp >/dev/null 2>&1; then
        ok "firewalld: 3389/tcp open"
    else
        warn "firewalld active but 3389/tcp not opened (ok if same-host RDP only)"
    fi
fi

echo
if [[ $FAIL -eq 0 ]]; then
    echo "  Pre-flight passed. You can now: docker compose up -d"
    exit 0
else
    echo "  Pre-flight failed. Fix the FAIL lines above before launching."
    exit 1
fi
