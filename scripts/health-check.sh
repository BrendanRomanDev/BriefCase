#!/usr/bin/env bash
# Doctor script for a local BriefCase install. Reports the health of every
# piece: venv, deps, DB, MCP registration, sidecar, token, launchd, extension
# bridge. Useful right after setup.sh and as the first stop when something
# looks off.
#
# Continues past failures so you see the full picture in one pass. Exits 0 if
# everything looks healthy, 1 if any check failed.
#
# Style matches setup.sh: [ok] / [fail] / [warn] / [skip].

set -uo pipefail   # no -e — we want to run every check

# --- Paths ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/venv/bin/python"

BRIEFCASE_DIR="${HOME}/.briefcase"
DB_PATH="${BRIEFCASE_DIR}/briefcase.db"
TOKEN_PATH="${BRIEFCASE_DIR}/sidecar_token"
PROFILE_PATH="${BRIEFCASE_DIR}/user_profile.yaml"
PLIST_PATH="${HOME}/Library/LaunchAgents/com.briefcase.sidecar.plist"
SIDECAR_URL="http://127.0.0.1:8989"

FAILED=0
WARNED=0

ok()   { echo "  [ok] $*"; }
fail() { echo "  [fail] $*"; FAILED=$((FAILED + 1)); }
warn() { echo "  [warn] $*"; WARNED=$((WARNED + 1)); }
hdr()  { echo ""; echo "=== $* ==="; }

# --- 1. Python venv + dependencies ---
hdr "venv + dependencies"

if [[ ! -x "${VENV_PYTHON}" ]]; then
    fail "venv missing at ${VENV_PYTHON} — run ./setup.sh"
else
    ok "venv python: $("${VENV_PYTHON}" --version 2>&1)"
    for pkg in fastapi mcp pydantic uvicorn; do
        if "${VENV_PYTHON}" -c "import ${pkg}" 2>/dev/null; then
            ok "${pkg} importable"
        else
            fail "${pkg} not importable — re-run ./setup.sh (pip install)"
        fi
    done
fi

# --- 2. ~/.briefcase layout ---
hdr "~/.briefcase layout"

for d in "${BRIEFCASE_DIR}" "${BRIEFCASE_DIR}/backups" "${BRIEFCASE_DIR}/logs"; do
    if [[ -d "${d}" ]]; then
        ok "${d}"
    else
        fail "${d} missing — run ./setup.sh"
    fi
done

if [[ -f "${PROFILE_PATH}" ]]; then
    if grep -qE '^name:\s*""\s*$' "${PROFILE_PATH}" || grep -qE '^name:\s*$' "${PROFILE_PATH}"; then
        warn "${PROFILE_PATH} exists but 'name' is empty — edit it"
    else
        ok "user profile present and non-empty"
    fi
else
    fail "${PROFILE_PATH} missing — run ./setup.sh"
fi

# --- 3. Database ---
hdr "database"

if [[ ! -f "${DB_PATH}" ]]; then
    fail "${DB_PATH} missing — run ./setup.sh"
elif ! command -v sqlite3 &>/dev/null; then
    warn "sqlite3 CLI not on PATH — can't verify integrity (brew install sqlite)"
else
    db_size=$(du -h "${DB_PATH}" | awk '{print $1}')
    result="$(sqlite3 "${DB_PATH}" 'PRAGMA integrity_check;' 2>&1 || true)"
    if [[ "${result}" == "ok" ]]; then
        ok "DB integrity: ok (${db_size})"
    else
        fail "DB integrity check failed: ${result}"
    fi

    # Sanity-check that core tables exist.
    tables="$(sqlite3 "${DB_PATH}" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" 2>/dev/null | tr '\n' ' ')"
    for t in initiatives inbox dailies triage_queue decision_log; do
        if echo " ${tables} " | grep -q " ${t} "; then
            ok "table '${t}' present"
        else
            fail "table '${t}' missing from DB schema"
        fi
    done
fi

# --- 4. MCP registration ---
hdr "Claude Code MCP registration"

if ! command -v claude &>/dev/null; then
    fail "'claude' CLI not on PATH — install Claude Code"
else
    mcp_line="$(claude mcp list 2>/dev/null | grep -E '^briefcase:' || true)"
    if [[ -z "${mcp_line}" ]]; then
        fail "MCP server 'briefcase' not registered — run ./setup.sh"
    else
        ok "MCP server registered"
        if echo "${mcp_line}" | grep -q "Connected"; then
            ok "MCP server reports Connected"
        elif echo "${mcp_line}" | grep -q "Failed\|Error"; then
            fail "MCP server registered but failing — check path in 'claude mcp list'"
        else
            warn "MCP server registered, connection state unclear: ${mcp_line}"
        fi
    fi
fi

# --- 5. Sidecar ---
hdr "sidecar"

if [[ ! -f "${TOKEN_PATH}" ]]; then
    fail "${TOKEN_PATH} missing — run briefcase/sidecar/install.sh"
else
    perms="$(stat -f '%Lp' "${TOKEN_PATH}" 2>/dev/null || echo '???')"
    if [[ "${perms}" == "600" ]]; then
        ok "auth token present (mode 600)"
    else
        warn "auth token present but mode is ${perms} (expected 600) — chmod 600 ${TOKEN_PATH}"
    fi
fi

if [[ ! -f "${PLIST_PATH}" ]]; then
    fail "launchd plist missing at ${PLIST_PATH} — run briefcase/sidecar/install.sh"
else
    ok "launchd plist installed"
    if launchctl list 2>/dev/null | grep -q "com.briefcase.sidecar"; then
        last_status=$(launchctl list 2>/dev/null | awk '/com\.briefcase\.sidecar$/ {print $2}')
        if [[ "${last_status}" == "0" ]]; then
            ok "launchd shows clean last exit (status 0)"
        else
            warn "launchd last exit was ${last_status} — check ~/.briefcase/logs/sidecar.err"
        fi
    else
        fail "launchd doesn't show com.briefcase.sidecar — load with launchctl load -w ${PLIST_PATH}"
    fi
fi

if command -v curl &>/dev/null; then
    health="$(curl -sf -m 3 "${SIDECAR_URL}/health" 2>/dev/null || true)"
    if [[ -n "${health}" ]]; then
        ok "sidecar /health responding: ${health}"
    else
        fail "sidecar not responding at ${SIDECAR_URL}/health"
    fi
else
    warn "curl not on PATH — can't probe sidecar HTTP"
fi

# --- Summary ---
hdr "summary"

if [[ "${FAILED}" -eq 0 && "${WARNED}" -eq 0 ]]; then
    echo "  Everything is healthy."
    exit 0
elif [[ "${FAILED}" -eq 0 ]]; then
    echo "  ${WARNED} warning(s), no failures. Mostly healthy."
    exit 0
else
    echo "  ${FAILED} failure(s), ${WARNED} warning(s). Something needs attention."
    exit 1
fi
