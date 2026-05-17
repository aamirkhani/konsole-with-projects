#!/usr/bin/env bash
# Stub-driven integration tests for the chromium-rdp entrypoint orchestration.
#
# These do not require a GPU, real GNOME, or any compositor — they substitute
# every external binary with a stub that simulates the relevant behaviour
# (Wayland-socket creation, port bind, intentional death, etc.). The point is
# to verify the BASH LOGIC in entrypoint.sh / healthcheck.sh / provision-grd.sh:
#
#   * fail-fast on missing or placeholder RDP_PASSWORD
#   * startup ordering (no subsystem starts before its prerequisites)
#   * the Wayland-socket readiness wait
#   * the RDP-port bind detection (parsing /proc/net/tcp)
#   * the supervisor loop catching crashed subsystems
#   * healthcheck.sh's three predicates (socket, port, chromium)
#
# Run:  ./tests/run-tests.sh
# CI:   exit code is the number of failing tests (0 = green).

set -u

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$TESTS_DIR/.." && pwd)"
STUBS="$TESTS_DIR/stubs"

# --- one-time setup -------------------------------------------------------

chmod +x "$STUBS"/* "$REPO"/scripts/*.sh

# Symlink the generic sleeper stub to every "just sleep" binary we substitute.
for name in pipewire wireplumber pipewire-pulse xdg-desktop-portal xdg-desktop-portal-gnome; do
    ln -sf sleeper "$STUBS/$name"
done

# Chromium stubs must be REAL binaries (pgrep -x reads /proc/PID/comm which
# reflects the executable's basename, not argv[0] or script name).
cp /usr/bin/sleep "$STUBS/chromium"
cp /usr/bin/sleep "$STUBS/chromium-browser"

# --- harness --------------------------------------------------------------

PASS=0
FAIL=0
FAILED_TESTS=()

c_red()   { printf '\033[31m%s\033[0m' "$*"; }
c_green() { printf '\033[32m%s\033[0m' "$*"; }
c_bold()  { printf '\033[1m%s\033[0m'  "$*"; }

start_test() { printf '\n%s\n' "$(c_bold "== $* ==")"; }
ok()    { printf '   %s %s\n' "$(c_green '✓')" "$*"; PASS=$((PASS+1)); }
notok() { printf '   %s %s\n' "$(c_red '✗')"  "$*"; FAIL=$((FAIL+1)); FAILED_TESTS+=("${CURRENT_TEST:-?}: $*"); }

assert_grep() {
    local pattern="$1" file="$2" msg="$3"
    if grep -qE "$pattern" "$file"; then ok "$msg"
    else
        notok "$msg (pattern: $pattern not found)"
        printf '       --- captured log ---\n'
        sed 's/^/       /' "$file" | tail -20
    fi
}

assert_exit() {
    local want="$1" got="$2" msg="$3"
    if [[ "$got" == "$want" ]]; then ok "$msg (exit=$got)"
    else notok "$msg (expected exit=$want, got=$got)"
    fi
}

# Run entrypoint.sh with stubbed binaries, in a clean runtime dir, with a
# timeout. Returns the entrypoint's exit code via $? and writes stderr+stdout
# to $LOG_FILE.
run_entrypoint() {
    local timeout_s="$1"; shift
    LOG_FILE=$(mktemp)
    RUNTIME_DIR=$(mktemp -d)
    chmod 0700 "$RUNTIME_DIR"

    # No set +e / -e juggling: the top-level script never enables errexit,
    # so timeout's nonzero exit is just a normal value we capture below.
    timeout --signal=TERM "$timeout_s" \
        env -i \
            PATH="$STUBS:/usr/bin:/bin" \
            HOME="$RUNTIME_DIR/home" \
            XDP_BIN="$STUBS/xdg-desktop-portal" \
            XDP_GNOME_BIN="$STUBS/xdg-desktop-portal-gnome" \
            GRD_DAEMON_BIN="$STUBS/gnome-remote-desktop-daemon" \
            PROVISION_GRD="$REPO/scripts/provision-grd.sh" \
            LAUNCH_CHROMIUM="$REPO/scripts/launch-chromium.sh" \
            XDG_RUNTIME_DIR="$RUNTIME_DIR" \
            WAYLAND_DISPLAY="wayland-test" \
            RDP_USER="testuser" \
            RDP_PORT="13389" \
            SCREEN_GEOMETRY="1024x768@30" \
            HOME_URL="about:blank" \
            KEYRING_PASSWORD="test" \
            "$@" \
            bash "$REPO/scripts/entrypoint.sh" \
        > "$LOG_FILE" 2>&1
    LAST_EXIT=$?

    # Clean up any lingering stub processes from this test's runtime dir.
    pkill -f "$RUNTIME_DIR" 2>/dev/null || true
    pkill -f "wayland-test"  2>/dev/null || true
    pkill -f "stub-grd"      2>/dev/null || true
    # Free port 13389 in case the grd stub is still bound.
    fuser -k 13389/tcp 2>/dev/null || true
    sleep 0.3
}

cleanup_global() {
    # shellcheck disable=SC2317  # invoked via EXIT trap
    pkill -f "wayland-test"  2>/dev/null || true
    # shellcheck disable=SC2317
    pkill -f "stub-grd"      2>/dev/null || true
    # shellcheck disable=SC2317
    fuser -k 13389/tcp 2>/dev/null || true
}
trap cleanup_global EXIT

# --- tests ----------------------------------------------------------------

CURRENT_TEST="fail-fast: unset RDP_PASSWORD"
start_test "$CURRENT_TEST"
run_entrypoint 5
assert_exit 1 "$LAST_EXIT" "exits non-zero"
assert_grep "RDP_PASSWORD is not set" "$LOG_FILE" "emits expected fatal"

CURRENT_TEST="fail-fast: placeholder RDP_PASSWORD"
start_test "$CURRENT_TEST"
run_entrypoint 5 RDP_PASSWORD=changeme
assert_exit 1 "$LAST_EXIT" "exits non-zero"
assert_grep "still the placeholder" "$LOG_FILE" "emits expected fatal"

CURRENT_TEST="happy path: all subsystems reach steady state"
start_test "$CURRENT_TEST"
run_entrypoint 8 RDP_PASSWORD=real-test-password
# timeout(1) returns 124 when it had to send the signal -> proves we got far enough
# that the supervisor loop was running when killed.
assert_exit 124 "$LAST_EXIT" "supervisor loop reached and killed by timeout"
assert_grep "all subsystems up" "$LOG_FILE" "logs 'all subsystems up'"
assert_grep "RDP port 13389 bound" "$LOG_FILE" "detects RDP port bind"
assert_grep "Wayland socket ready" "$LOG_FILE" "detects Wayland socket"

CURRENT_TEST="failure: mutter dies during startup"
start_test "$CURRENT_TEST"
run_entrypoint 8 RDP_PASSWORD=real STUB_MUTTER_MODE=die_immediately
assert_exit 1 "$LAST_EXIT" "exits non-zero"
assert_grep "mutter died during startup" "$LOG_FILE" "detects mutter death"

CURRENT_TEST="failure: grd daemon dies during startup"
start_test "$CURRENT_TEST"
run_entrypoint 8 RDP_PASSWORD=real STUB_GRD_MODE=die_immediately
assert_exit 1 "$LAST_EXIT" "exits non-zero"
assert_grep "gnome-remote-desktop-daemon died" "$LOG_FILE" "detects grd death"

CURRENT_TEST="provision-grd: generates TLS cert if absent"
start_test "$CURRENT_TEST"
TMP_HOME=$(mktemp -d)
( cd "$TMP_HOME" && \
    PATH="$STUBS:$PATH" HOME="$TMP_HOME" \
    RDP_USER=u RDP_PASSWORD=p RDP_PORT=13389 \
    bash "$REPO/scripts/provision-grd.sh" >/dev/null 2>&1 )
if [[ -s "$TMP_HOME/.local/share/gnome-remote-desktop/rdp/tls.crt" ]]; then
    ok "TLS cert generated"
else
    notok "TLS cert NOT generated at expected path"
fi
rm -rf "$TMP_HOME"

CURRENT_TEST="healthcheck: passes when all predicates hold"
start_test "$CURRENT_TEST"
RUNTIME_DIR=$(mktemp -d); chmod 0700 "$RUNTIME_DIR"
# Synthesize each predicate ourselves; we don't need entrypoint for this.
python3 -c "
import socket, os, sys, time
os.environ['XDG_RUNTIME_DIR'] = '$RUNTIME_DIR'
s_unix = socket.socket(socket.AF_UNIX); s_unix.bind('$RUNTIME_DIR/wayland-0'); s_unix.listen(1)
s_tcp = socket.socket(); s_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s_tcp.bind(('0.0.0.0', 13389)); s_tcp.listen(1)
print('ready', flush=True)
time.sleep(15)
" &
SYNTH_PID=$!
# Wait for "ready" then launch a sleep-as-chromium and probe.
sleep 1
cp /usr/bin/sleep "$RUNTIME_DIR/chromium" && "$RUNTIME_DIR/chromium" 10 &
CHROMIUM_PID=$!
sleep 0.3
PATH="$RUNTIME_DIR:$STUBS:$PATH" \
    XDG_RUNTIME_DIR="$RUNTIME_DIR" WAYLAND_DISPLAY="wayland-0" RDP_PORT=13389 \
    bash "$REPO/scripts/healthcheck.sh" >/tmp/hc.out 2>&1
HC_EXIT=$?
kill $CHROMIUM_PID $SYNTH_PID 2>/dev/null; wait 2>/dev/null
assert_exit 0 "$HC_EXIT" "healthcheck returns 0"
assert_grep "healthy" /tmp/hc.out "logs 'healthy'"
rm -rf "$RUNTIME_DIR"

CURRENT_TEST="healthcheck: fails when Wayland socket missing"
start_test "$CURRENT_TEST"
RUNTIME_DIR=$(mktemp -d); chmod 0700 "$RUNTIME_DIR"
XDG_RUNTIME_DIR="$RUNTIME_DIR" WAYLAND_DISPLAY="wayland-0" \
    bash "$REPO/scripts/healthcheck.sh" >/tmp/hc.out 2>&1
HC_EXIT=$?
assert_exit 1 "$HC_EXIT" "healthcheck returns 1"
assert_grep "Wayland socket missing" /tmp/hc.out "names the failing predicate"
rm -rf "$RUNTIME_DIR"

CURRENT_TEST="launch-chromium: chooses chromium-browser when available"
start_test "$CURRENT_TEST"
# Make ONLY chromium-browser visible on PATH, no chromium.
TMP_PATH_DIR=$(mktemp -d)
cp /usr/bin/echo "$TMP_PATH_DIR/chromium-browser"
PATH="$TMP_PATH_DIR:/usr/bin:/bin" \
    HOME_URL="about:blank" \
    bash "$REPO/scripts/launch-chromium.sh" >/tmp/lc.out 2>&1 || true
assert_grep "ozone-platform=wayland" /tmp/lc.out "passes Wayland flag"
assert_grep "user-data-dir=/data/profile" /tmp/lc.out "passes profile dir"
assert_grep "WaylandClipboard" /tmp/lc.out "enables Wayland clipboard feature"
assert_grep "VaapiVideoDecoder" /tmp/lc.out "enables VA-API decoder feature"
assert_grep "VaapiVideoEncoder" /tmp/lc.out "enables VA-API encoder feature"
rm -rf "$TMP_PATH_DIR"

# --- summary --------------------------------------------------------------

echo
printf '%s\n' "$(c_bold "==================== SUMMARY ====================")"
printf '%s passed   %s failed\n' "$(c_green "$PASS")" "$(c_red "$FAIL")"
if [[ $FAIL -gt 0 ]]; then
    echo
    echo "Failed assertions:"
    printf '  - %s\n' "${FAILED_TESTS[@]}"
fi
exit "$FAIL"
