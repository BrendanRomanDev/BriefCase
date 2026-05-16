#!/usr/bin/env bash
# Deprecated location — the canonical installer is now at the repo root.
# This shim exists so existing muscle memory (`bash scripts/setup.sh`)
# keeps working.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

echo "  [info] scripts/setup.sh has moved to ${PROJECT_ROOT}/setup.sh"
echo "  [info] forwarding..."
echo ""

exec "${PROJECT_ROOT}/setup.sh" "$@"
