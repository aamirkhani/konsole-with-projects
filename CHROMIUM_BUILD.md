# Building Chromium from Source

## System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| Disk     | 80 GB   | 150 GB      |
| RAM      | 8 GB    | 16 GB+      |
| CPU      | 4 cores | 16+ cores   |
| OS       | Ubuntu 22.04/24.04 x86_64 | same |

Build times (16-core machine): ~1.5 hours (Release, symbol_level=0)

---

## Quick Start

```bash
# Full pipeline (installs deps, fetches source, configures, builds)
./build-chromium.sh all

# Custom location
CHROMIUM_DIR=/mnt/ssd/chromium ./build-chromium.sh all

# Individual steps
./build-chromium.sh deps           # install system packages
./build-chromium.sh depot_tools    # set up gclient/ninja/etc
./build-chromium.sh fetch          # fetch ~30 GB source
./build-chromium.sh configure      # gn gen out/Release
./build-chromium.sh build          # autoninja -C out/Release chrome
./build-chromium.sh run            # launch the built browser
```

---

## Docker Build

If you don't want to install dependencies on the host:

```bash
# Build the image
docker build -f chromium-build.dockerfile -t chromium-builder .

# Run — mount a volume with 100+ GB free
docker run --rm \
  -v /mnt/ssd/chromium:/chromium \
  chromium-builder
```

---

## Step-by-Step (manual)

### 1. depot_tools

```bash
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
export PATH="$PWD/depot_tools:$PATH"
```

### 2. Fetch source

```bash
mkdir ~/chromium && cd ~/chromium
fetch --nohooks chromium     # ~30 GB download, 30-90 min
cd src
build/install-build-deps.sh  # installs Ubuntu packages
gclient runhooks
```

### 3. Configure

```bash
gn gen out/Release
# Or with custom args:
gn args out/Release          # opens $EDITOR
```

Recommended `args.gn` for fast builds:

```gn
is_debug = false
is_component_build = false
is_clang = true
clang_use_chrome_plugins = false
symbol_level = 0
blink_symbol_level = 0
v8_symbol_level = 0
enable_nacl = false
enable_widevine = false
use_cups = true
use_pulseaudio = true
link_pulseaudio = true
```

### 4. Build

```bash
autoninja -C out/Release chrome
# or for all targets:
autoninja -C out/Release
```

### 5. Run

```bash
out/Release/chrome --no-sandbox
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `fatal: could not read Username` | Run inside a network with access to chromium.googlesource.com |
| Out of disk mid-build | Use `is_component_build = true` to reduce disk usage |
| OOM during link | Add `use_thin_lto = false` and reduce `-j` jobs |
| Missing sysroot | Re-run `gclient runhooks` |
| `clang: error: no such file` | Re-run `build/install-build-deps.sh` |

---

## References

- [Official Linux build instructions](https://chromium.googlesource.com/chromium/src/+/main/docs/linux/build_instructions.md)
- [GN build configuration](https://www.chromium.org/developers/gn-build-configuration/)
- [depot_tools tutorial](https://commondatastorage.googleapis.com/chrome-infra-docs/flat/depot_tools/docs/html/depot_tools_tutorial.html)
