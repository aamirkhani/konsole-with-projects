# chromium-rdp

Headless, GPU-accelerated **full Chromium** delivered over **RDP** by
`gnome-remote-desktop`. Multi-tab, full keyboard/mouse, full clipboard
(including images), VA-API hardware video, AVC444 H.264 over the wire, RDPUDP
for sub-RTT input.

The server-side runs without a physical monitor. The GPU is consumed via the
DRM render node (`/dev/dri/renderD128`), composited by a headless Mutter, and
encoded to RDP graphics by `gnome-remote-desktop` using VA-API.

## Architecture

```
                        ┌─────────────── server ───────────────┐
                        │  ┌──────────────────────────────────┐ │
RDP client  ◀── 3389 ──▶│  │ gnome-remote-desktop-daemon      │ │
(mstsc /  ◀── 3389/udp ▶│  │   ├── RDPGFX (H.264 AVC444)      │ │
 FreeRDP /              │  │   ├── RDPECLIP (text + images)   │ │
 Remmina)               │  │   └── RDPSND / RDPEI input       │ │
                        │  └──────────────────────────────────┘ │
                        │              ▲   reads frames         │
                        │  ┌───────────┴──────────────────────┐ │
                        │  │ Mutter --headless --wayland      │ │
                        │  │   (DRM render node, VA-API enc)  │ │
                        │  └───────────┬──────────────────────┘ │
                        │              │ Wayland               │
                        │  ┌───────────┴──────────────────────┐ │
                        │  │ Chromium --ozone-platform=wayland│ │
                        │  │   N tabs, GPU raster, VA-API     │ │
                        │  │   decode, WaylandClipboard       │ │
                        │  └──────────────────────────────────┘ │
                        └───────────────────────────────────────┘
```

## Two deployment paths

### A. Containerised (recommended)

```bash
./scripts/verify-host.sh                                 # pre-flight
docker compose up -d --build                             # build + run
docker compose exec chromium-rdp /usr/local/bin/healthcheck.sh
```

Then point any RDP client at `<host>:3389` with the credentials in
`compose.yaml` (change them first).

The container is Fedora 41 based: latest Mutter (47), latest
gnome-remote-desktop (47), Chromium 131+ with VA-API enabled.

### B. Bare-metal user service

```bash
sudo ./systemd/install-bare-metal.sh
sudo machinectl shell chromium-rdp@ -- systemctl --user edit chromium-rdp
# add: Environment=RDP_PASSWORD=your-password
sudo machinectl shell chromium-rdp@ -- systemctl --user start chromium-rdp
```

Use this when you want the session to share the host's GPU drivers and audio
without nested user namespaces (NVIDIA hosts are easier this way).

## Feature checklist

| Feature                                         | How                                                                  |
|-------------------------------------------------|----------------------------------------------------------------------|
| GPU-accelerated rendering                       | `/dev/dri/renderD128` + Mesa + VA-API + Chromium GPU process         |
| Multiple tabs                                   | Plain Chromium; tabs are an internal concern, no extra wiring        |
| Full keyboard                                   | RDPEI → libei → Mutter → Wayland clients                             |
| Full mouse (incl. side buttons, smooth scroll)  | same path; libei carries all axes                                    |
| Clipboard text                                  | RDPECLIP ↔ wl_data_device (CF_UNICODETEXT)                           |
| **Clipboard images**                            | RDPECLIP CF_DIB / CF_DIBV5 ↔ image/png on Wayland                    |
| Audio out                                       | PipeWire default sink → RDPSND (Opus)                                |
| Hardware H.264 encode                           | `GRD_ENABLE_HW_ACCEL=1` → VA-API encoder in grd                      |
| Sub-RTT input                                   | RDPUDP transport (`-p 3389:3389/udp`)                                |
| Persistent tabs / profiles                      | `/data/profile` volume bind                                          |
| TLS for RDP                                     | self-signed cert auto-generated on first start                       |

## Configuration

All knobs are environment variables, set in `compose.yaml` (container) or via
`systemctl --user edit chromium-rdp` (bare metal).

| Variable              | Default                | Purpose                                |
|-----------------------|------------------------|----------------------------------------|
| `RDP_USER`            | `rdpuser`              | RDP authentication user                |
| `RDP_PASSWORD`        | `changeme`             | RDP authentication password            |
| `RDP_PORT`            | `3389`                 | listening TCP/UDP port                 |
| `SCREEN_GEOMETRY`     | `1920x1080@60`         | virtual monitor size + refresh         |
| `HOME_URL`            | `about:blank`          | start page                             |
| `LIBVA_DRIVER_NAME`   | autodetected           | force VA-API driver (`iHD`, `radeonsi`)|
| `EXTRA_CHROMIUM_FLAGS`| empty                  | appended to Chromium command line      |

## Performance

| Network | Encoder       | Glass-to-glass latency |
|---------|---------------|------------------------|
| LAN     | AVC444 + RDPUDP | 40–60 ms             |
| WAN     | AVC420 H.264   | 80–120 ms              |

Latency depends primarily on (a) whether VA-API encode is actually engaged
(check `chrome://media-internals` from inside the session and `vainfo` inside
the container), and (b) whether the RDP client negotiates RDPUDP.

## GPU support matrix

| Vendor / arch          | Status   | Notes                                        |
|------------------------|----------|----------------------------------------------|
| Intel Gen11+           | works    | `iHD` driver via `intel-media-driver`        |
| Intel Gen7–Gen10       | works    | `i965` driver via `libva-intel-driver`       |
| AMD Vega / RDNA / RDNA2/3 | works | `radeonsi` in Mesa, AVC444 encode via VAAPI  |
| NVIDIA (recent)        | works\*  | needs `nvidia-vaapi-driver`, `nvidia-drm.modeset=1`, driver ≥ 555. Prefer the bare-metal install path on NVIDIA hosts. |
| llvmpipe (software)    | works    | for CI/testing only; <10 fps at 1080p        |

## Verification ladder

Run these in order when bringing up a host. Each step verifies one layer.

```bash
# 0. Orchestration logic (no GPU, no GNOME needed; runs anywhere with bash + python3)
./tests/run-tests.sh

# 1. Host pre-flight (kernel, render node, perms, runtime)
./scripts/verify-host.sh

# 2. Build the image
docker compose build

# 3. Bring it up
export RDP_PASSWORD='something-real'
docker compose up -d

# 4. Container health (Wayland socket, RDP port, Chromium PID)
docker compose exec chromium-rdp /usr/local/bin/healthcheck.sh

# 5. Confirm VA-API engaged inside the container
docker compose exec chromium-rdp vainfo | head -20

# 6. Confirm grd is advertising RDPGFX/AVC444 capability
docker compose exec chromium-rdp grdctl status

# 7. Connect from a real RDP client and check:
#    - browser renders smoothly under scroll
#    - middle-click pastes selection
#    - copy image from a webpage, paste into a local image editor
#    - youtube.com plays without dropping frames
```

### What `tests/run-tests.sh` covers

Stub-driven integration tests for `entrypoint.sh`, `provision-grd.sh`,
`launch-chromium.sh`, and `healthcheck.sh`. They substitute every external
binary (mutter, grd-daemon, chromium, grdctl, dbus-launch, gnome-keyring,
pipewire, portal, vainfo) with a stub that simulates the relevant behaviour
— socket creation, port bind, intentional death, etc. — and verify:

| Scenario                                                     | Asserts                                       |
|--------------------------------------------------------------|-----------------------------------------------|
| unset `RDP_PASSWORD`                                         | entrypoint exits 1 with the expected message  |
| placeholder `RDP_PASSWORD=changeme`                          | same                                          |
| happy path                                                   | reaches "all subsystems up", binds RDP port, opens Wayland socket |
| mutter dies during startup                                   | supervisor catches it, reports                |
| grd-daemon dies during startup                               | same                                          |
| `provision-grd.sh` with no pre-existing cert                 | generates self-signed TLS cert at the expected path |
| `healthcheck.sh` with all predicates holding                 | exit 0, logs "healthy"                        |
| `healthcheck.sh` with Wayland socket absent                  | exit 1, names the failing predicate           |
| `launch-chromium.sh` with only `chromium-browser` on PATH    | picks it; passes Wayland, profile, clipboard, and VA-API flags |

## What is NOT included

- **Multi-tenancy**. One container = one Chromium profile = one concurrent
  session. For N concurrent sessions, run N containers, each with its own
  port mapping and profile volume.
- **GPU partitioning**. All containers share the same render node.
- **SSO / OIDC**. The RDP authentication is local username/password; put an
  RDP gateway (Apache Guacamole, FreeRDP-WebConnect) in front for federation.
- **Persistent extensions across image rebuilds**. They live in
  `/data/profile`, which is on a named Docker volume, so they survive
  container restarts but a `docker volume rm` wipes them.
