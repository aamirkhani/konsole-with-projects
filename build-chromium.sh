#!/usr/bin/env bash
# Chromium build script for Ubuntu 22.04/24.04 (x86_64)
# Requirements: ~100GB disk, 16GB+ RAM, 8+ CPU cores
# Reference: https://chromium.googlesource.com/chromium/src/+/main/docs/linux/build_instructions.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROMIUM_DIR="${CHROMIUM_DIR:-$HOME/chromium}"
DEPOT_TOOLS_DIR="${CHROMIUM_DIR}/depot_tools"
BUILD_TYPE="${BUILD_TYPE:-Release}"
JOBS="${JOBS:-$(nproc)}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[chromium-build]${NC} $*"; }
warn() { echo -e "${YELLOW}[chromium-build]${NC} $*"; }
die()  { echo -e "${RED}[chromium-build] ERROR:${NC} $*" >&2; exit 1; }

check_requirements() {
    log "Checking system requirements..."

    local avail_gb
    avail_gb=$(df -BG "$HOME" | awk 'NR==2 {gsub("G",""); print $4}')
    if [[ $avail_gb -lt 80 ]]; then
        die "Need at least 80GB free disk space. Available: ${avail_gb}GB"
    fi

    local ram_gb
    ram_gb=$(free -g | awk '/^Mem:/ {print $2}')
    if [[ $ram_gb -lt 8 ]]; then
        warn "Recommended 16GB RAM. Available: ${ram_gb}GB — build may be slow"
    fi

    log "Disk: ${avail_gb}GB available | RAM: ${ram_gb}GB | CPUs: $(nproc)"
}

install_deps() {
    log "Installing build dependencies..."
    sudo apt-get update -qq
    sudo apt-get install -y --no-install-recommends \
        git curl python3 python3-pip \
        build-essential lsb-release sudo \
        pkg-config \
        2>&1 | tail -5
    log "Base dependencies installed."
}

setup_depot_tools() {
    log "Setting up depot_tools..."
    if [[ ! -d "$DEPOT_TOOLS_DIR" ]]; then
        git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git \
            "$DEPOT_TOOLS_DIR"
    else
        log "depot_tools already present, updating..."
        git -C "$DEPOT_TOOLS_DIR" pull --ff-only
    fi
    export PATH="$DEPOT_TOOLS_DIR:$PATH"
    log "depot_tools ready at $DEPOT_TOOLS_DIR"
}

fetch_chromium() {
    log "Fetching Chromium source (~30GB, this will take 30-90 minutes)..."
    mkdir -p "$CHROMIUM_DIR/src_root"
    cd "$CHROMIUM_DIR/src_root"

    if [[ ! -f .gclient ]]; then
        fetch --nohooks chromium
    else
        log "Chromium already fetched, running gclient sync..."
    fi

    cd src
    log "Installing Chromium-specific build dependencies..."
    sudo bash build/install-build-deps.sh --no-prompt

    log "Running gclient hooks..."
    gclient runhooks
    log "Source fetch complete."
}

configure_build() {
    log "Configuring Chromium build (${BUILD_TYPE})..."
    cd "$CHROMIUM_DIR/src_root/src"

    local out_dir="out/${BUILD_TYPE}"
    mkdir -p "$out_dir"

    # Write GN build args
    cat > "${out_dir}/args.gn" << 'GN_ARGS'
# Build type
is_debug = false
is_component_build = false

# Compiler — use system clang for faster builds
is_clang = true
clang_use_chrome_plugins = false

# Speed up builds
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
enable_nacl = false

# Disable unused features to reduce build time
enable_widevine = false
enable_hangout_services_extension = false
use_cups = true
use_pulseaudio = true
link_pulseaudio = true
GN_ARGS

    gn gen "$out_dir"
    log "Build configured in ${out_dir}. Run: autoninja -C ${out_dir} chrome"
}

build_chromium() {
    log "Building Chromium (this takes 1-4 hours on modern hardware)..."
    cd "$CHROMIUM_DIR/src_root/src"
    local out_dir="out/${BUILD_TYPE}"

    autoninja -C "$out_dir" chrome 2>&1 | tee "$CHROMIUM_DIR/build.log"
    log "Build complete! Binary at: ${out_dir}/chrome"
}

run_chromium() {
    local binary="$CHROMIUM_DIR/src_root/src/out/${BUILD_TYPE}/chrome"
    if [[ ! -f "$binary" ]]; then
        die "Chromium binary not found at $binary. Run the build first."
    fi
    log "Launching Chromium..."
    "$binary" --no-sandbox &
}

usage() {
    cat << EOF
Usage: $0 [COMMAND]

Commands:
  all         Run full pipeline: deps → depot_tools → fetch → configure → build
  deps        Install system dependencies only
  depot_tools Set up depot_tools only
  fetch       Fetch Chromium source only
  configure   Configure GN build only
  build       Build chrome binary only
  run         Launch the built Chromium

Environment variables:
  CHROMIUM_DIR   Where to store source + build (default: ~/chromium)
  BUILD_TYPE     Release or Debug (default: Release)
  JOBS           Parallel jobs (default: nproc)

Examples:
  $0 all
  CHROMIUM_DIR=/mnt/ssd/chromium BUILD_TYPE=Debug $0 all
  $0 build
EOF
}

main() {
    local cmd="${1:-all}"
    case "$cmd" in
        all)
            check_requirements
            install_deps
            setup_depot_tools
            fetch_chromium
            configure_build
            build_chromium
            ;;
        deps)        install_deps ;;
        depot_tools) setup_depot_tools ;;
        fetch)       setup_depot_tools; fetch_chromium ;;
        configure)   configure_build ;;
        build)       build_chromium ;;
        run)         run_chromium ;;
        help|-h|--help) usage ;;
        *) die "Unknown command: $cmd. Run '$0 help' for usage." ;;
    esac
}

main "$@"
