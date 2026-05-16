#!/usr/bin/env bash
# BriefCase Sidecar installer
#
# Does the following:
#   1. Ensures the Python venv has FastAPI installed
#   2. Generates ~/.briefcase/sidecar_token if missing
#   3. Renders the launchd plist template with this machine's paths
#   4. Installs it to ~/Library/LaunchAgents/
#   5. Loads it (launchctl) so the sidecar starts now and at every login
#
# Idempotent — safe to run multiple times.

set -euo pipefail

# --- Paths ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/venv/bin/python"
PYTHON_BIN_DIR="${PROJECT_ROOT}/venv/bin"

LABEL="com.briefcase.sidecar"
PLIST_TEMPLATE="${SCRIPT_DIR}/launchd/${LABEL}.plist.template"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

TOKEN_PATH="${HOME}/.briefcase/sidecar_token"
LOGS_DIR="${HOME}/.briefcase/logs"

# --- Preflight ---
if [[ ! -x "${VENV_PYTHON}" ]]; then
    echo "ERROR: Python venv not found at ${VENV_PYTHON}"
    echo "Run ./setup.sh from the repo root — it creates the venv,"
    echo "then runs this sidecar installer automatically."
    exit 1
fi

if [[ ! -f "${PLIST_TEMPLATE}" ]]; then
    echo "ERROR: plist template missing: ${PLIST_TEMPLATE}"
    exit 1
fi

# --- Ensure FastAPI is installed ---
if ! "${VENV_PYTHON}" -c "import fastapi" 2>/dev/null; then
    echo "Installing FastAPI into venv..."
    "${VENV_PYTHON}" -m pip install fastapi
fi

# --- Ensure logs dir ---
mkdir -p "${LOGS_DIR}"

# --- Ensure token (sidecar also does this at startup; we do it here so install.sh can print it) ---
mkdir -p "$(dirname "${TOKEN_PATH}")"
if [[ ! -s "${TOKEN_PATH}" ]]; then
    "${VENV_PYTHON}" -c "from briefcase.sidecar.server import ensure_token; print(ensure_token())" > /dev/null
    echo "Generated new auth token at ${TOKEN_PATH}"
fi
chmod 600 "${TOKEN_PATH}"

# --- Render plist ---
mkdir -p "$(dirname "${PLIST_DEST}")"
sed \
    -e "s|__PYTHON__|${VENV_PYTHON}|g" \
    -e "s|__PROJECT_PATH__|${PROJECT_ROOT}|g" \
    -e "s|__PYTHON_BIN_DIR__|${PYTHON_BIN_DIR}|g" \
    -e "s|__HOME__|${HOME}|g" \
    "${PLIST_TEMPLATE}" > "${PLIST_DEST}"
echo "Installed plist: ${PLIST_DEST}"

# --- (Re)load with launchctl ---
# Unload first if already loaded; ignore errors.
launchctl unload "${PLIST_DEST}" 2>/dev/null || true
launchctl load -w "${PLIST_DEST}"
echo "Loaded: ${LABEL}"

# --- Report ---
echo ""
echo "========================================"
echo "BriefCase Sidecar installed."
echo "  Label:  ${LABEL}"
echo "  Port:   \${BRIEFCASE_SIDECAR_PORT:-8989}  (override via env or settings.yaml)"
echo "  Token:  ${TOKEN_PATH}"
echo "  Logs:   ${LOGS_DIR}/sidecar.{log,err}"
echo ""
echo "Auth token (for the Chrome extension):"
cat "${TOKEN_PATH}"
echo ""
echo "Verify it's alive:"
echo "  curl http://127.0.0.1:8989/health"
echo ""
echo "To stop:    launchctl unload ${PLIST_DEST}"
echo "To restart: launchctl unload ${PLIST_DEST} && launchctl load -w ${PLIST_DEST}"
echo "========================================"
