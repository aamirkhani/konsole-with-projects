#!/usr/bin/env bash
# Run all Linux PowerToys tests
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="${PYTHON:-python3.12}"

echo "════════════════════════════════════════════════════════"
echo "  Linux PowerToys - Test Suite"
echo "════════════════════════════════════════════════════════"
echo ""
echo "Python: $($PYTHON --version)"
echo ""

# Run each test module
TESTS=(
    "tests.test_powerrename"
    "tests.test_imageresizer"
    "tests.test_hostseditor"
    "tests.test_filelocksmith"
    "tests.test_colorpicker"
    "tests.test_fancyzones"
    "tests.test_config"
)

PASSED=0
FAILED=0

for test_module in "${TESTS[@]}"; do
    echo "─── $test_module ─────────────────────────────────────"
    if $PYTHON -m pytest "$test_module" -v --tb=short 2>/dev/null || \
       $PYTHON -m unittest "$test_module" -v 2>&1; then
        PASSED=$((PASSED + 1))
    else
        FAILED=$((FAILED + 1))
    fi
    echo ""
done

echo "════════════════════════════════════════════════════════"
echo "  Results: $PASSED test modules passed, $FAILED failed"
echo "════════════════════════════════════════════════════════"

[ $FAILED -eq 0 ]
