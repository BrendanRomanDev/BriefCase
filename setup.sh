#!/usr/bin/env bash
# BriefCase first-run installer.
#
# One command to get a fresh work machine to a working install:
#   - Python venv + requirements
#   - ~/.briefcase/ bootstrap (db, profile, backups, logs)
#   - Claude Code MCP registration (user-scope, available from any cwd)
#   - Sidecar launchd agent
#   - Final report with extension load instructions and the sidecar token
#
# Idempotent. Re-running is safe and only re-does what's missing.
# Style notes: [skip] / [install] / [ok] / [warn] echoes mirror the
# peon-ping dotfiles setup so the output reads consistently across installers.

set -euo pipefail

# --- Paths ---
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
VENV_DIR="${PROJECT_ROOT}/venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
REQUIREMENTS="${PROJECT_ROOT}/requirements.txt"

BRIEFCASE_DIR="${HOME}/.briefcase"
DB_PATH="${BRIEFCASE_DIR}/briefcase.db"
PROFILE_PATH="${BRIEFCASE_DIR}/user_profile.yaml"
BACKUP_DIR="${BRIEFCASE_DIR}/backups"
LOGS_DIR="${BRIEFCASE_DIR}/logs"
TOKEN_PATH="${BRIEFCASE_DIR}/sidecar_token"

MCP_NAME="briefcase"
SIDECAR_INSTALL="${PROJECT_ROOT}/briefcase/sidecar/install.sh"

# --- Helpers ---
say()  { echo "  $*"; }
hdr()  { echo ""; echo "=== $* ==="; }
ok()   { echo "  [ok] $*"; }
add()  { echo "  [install] $*"; }
skip() { echo "  [skip] $*"; }
warn() { echo "  [warn] $*"; }

detect_platform() {
    # Sets PLATFORM to one of: darwin | linux | wsl | windows
    # Used to skip platform-specific phases (launchd) and surface guidance
    # for the /onboard agent. Never bails — the /onboard agent handles
    # platform-specific pivots (systemd on Linux, Scheduled Task on Windows).
    local uname_s
    uname_s="$(uname -s 2>/dev/null || echo unknown)"
    case "${uname_s}" in
        Darwin) PLATFORM="darwin" ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                PLATFORM="wsl"
            else
                PLATFORM="linux"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="windows" ;;
        *) PLATFORM="unknown" ;;
    esac

    case "${PLATFORM}" in
        darwin) ok "platform: macOS (full install supported)" ;;
        linux)  warn "platform: Linux — launchd phase will skip; use systemd via /onboard" ;;
        wsl)    warn "platform: WSL2 — treated as Linux; clipboard via clip.exe" ;;
        windows)
            echo "ERROR: setup.sh is a bash installer. On Windows-native, run /onboard" >&2
            echo "       inside Claude Code instead — it handles winget + Scheduled Task." >&2
            exit 1
            ;;
        *)      warn "platform: unknown ($uname_s) — proceeding, but you may hit issues" ;;
    esac
}

require_cmd() {
    local cmd="$1" hint="${2:-}"
    if ! command -v "${cmd}" &>/dev/null; then
        echo "ERROR: '${cmd}' not found on PATH." >&2
        [[ -n "${hint}" ]] && echo "       ${hint}" >&2
        exit 1
    fi
}

# --- Phase 0: Preflight ---
hdr "0 / Preflight"
detect_platform
# Per-platform install hints (the /onboard agent uses these to pivot):
#   macOS:   brew install python@3.12  /  brew install --cask claude-code
#   Linux:   apt/dnf/pacman install python3.12  /  npm i -g @anthropic-ai/claude-code
#   WSL2:    same as Linux; clipboard via clip.exe; sidecar via systemd --user
#   Windows: winget install Python.Python.3.12  /  winget install Anthropic.ClaudeCode
#            sidecar via Task Scheduler or NSSM (handled by /onboard)
require_cmd python3 "Install Python 3.11+ for your platform (macOS: brew install python@3.12)"
require_cmd claude   "Install Claude Code (macOS: brew install --cask claude-code)"
ok "python3: $(python3 --version)"
ok "claude:  $(claude --version 2>/dev/null || echo 'available')"

# --- Phase 1: Python venv + dependencies ---
hdr "1 / Python venv + dependencies"

if [[ -x "${VENV_PYTHON}" ]]; then
    skip "venv already present at ${VENV_DIR}"
else
    add "creating venv at ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
fi

# Always ensure pip is current and requirements are satisfied. pip is fast
# at no-op installs, so this is cheap on reruns.
add "pip install -r requirements.txt (no-op if already satisfied)"
"${VENV_PYTHON}" -m pip install --upgrade pip --quiet
"${VENV_PYTHON}" -m pip install -r "${REQUIREMENTS}" --quiet
ok "dependencies satisfied"

# --- Phase 2: ~/.briefcase bootstrap ---
hdr "2 / ~/.briefcase bootstrap"

for d in "${BRIEFCASE_DIR}" "${BACKUP_DIR}" "${LOGS_DIR}"; do
    if [[ -d "${d}" ]]; then
        skip "${d}"
    else
        add "${d}"
        mkdir -p "${d}"
    fi
done

# Initialise the DB schema. The init_database() function in
# briefcase/mcp_server/database.py is idempotent — it runs CREATE TABLE
# IF NOT EXISTS for every table — so re-running is a no-op against an
# existing DB.
if [[ -f "${DB_PATH}" ]]; then
    skip "database already exists at ${DB_PATH}"
else
    add "initialising database at ${DB_PATH}"
fi
PYTHONPATH="${PROJECT_ROOT}" "${VENV_PYTHON}" -c "
from briefcase.mcp_server.database import init_database
init_database('${DB_PATH}')
"
ok "database schema verified"

# User profile template. Only write if missing — we never overwrite a
# real profile.
if [[ -f "${PROFILE_PATH}" ]]; then
    skip "user profile already exists at ${PROFILE_PATH}"
else
    add "writing user profile template to ${PROFILE_PATH}"
    cat > "${PROFILE_PATH}" << 'YAML'
# ~/.briefcase/user_profile.yaml
# Edit this with your real details. Kit reads it at the start of every
# conversation to know who you are, what you're working on, and where.
name: ""
role: ""
company: ""
team_name: ""
reports_to: ""

responsibilities:
  - ""

team: []

projects:
  - slug: example-project
    name: Example Project
    description: ""
    repo: ""
    status: active

calendar_id: primary

# Absolute path to your Obsidian vault. Leave null to skip vault-dependent
# features (kudos, weekly rollup, meeting note filing). The /onboard agent
# will prompt you for this if you haven't set it.
obsidian_vault: null

# Optional PDLC lane filter. Drop a `team` or `tech_lead` string to scope
# `list_pdlc_projects(my_lane=true)` to your slice. Leave empty for "all".
pdlc:
  team: ""
  tech_lead: ""

preferences:
  printing: false
YAML
    warn "edit ${PROFILE_PATH} or run /onboard to populate your details"
fi

# --- Phase 3: Register MCP server with Claude Code (user scope) ---
hdr "3 / Claude Code MCP registration"

# `claude mcp list` lines start with "<name>: ..." — grep for an exact match.
# Registering at user scope so Kit is reachable from every working directory.
if claude mcp list 2>/dev/null | grep -qE "^${MCP_NAME}:"; then
    skip "MCP server '${MCP_NAME}' already registered (claude mcp list)"
else
    add "registering MCP server '${MCP_NAME}' at user scope"
    # `--env` is a variadic flag — must come AFTER the positional name,
    # otherwise commander.js eats the name as another env value and errors.
    # The `--` separator is required so the command path isn't parsed as flags.
    claude mcp add \
        --scope user \
        "${MCP_NAME}" \
        --env "PYTHONPATH=${PROJECT_ROOT}" \
        -- \
        "${VENV_PYTHON}" "${PROJECT_ROOT}/briefcase/mcp_server/server.py"
    ok "registered. Restart any running Claude Code session to pick it up."
fi

# --- Phase 4: Sidecar (launchd agent — macOS only) ---
hdr "4 / Sidecar HTTP bridge"

if [[ "${PLATFORM}" != "darwin" ]]; then
    warn "Skipping launchd sidecar install on ${PLATFORM}."
    warn "Run /onboard inside Claude Code to install a systemd user service (Linux/WSL)"
    warn "or a Scheduled Task (Windows-native). The sidecar code itself is platform-neutral."
elif [[ ! -x "${SIDECAR_INSTALL}" ]]; then
    warn "${SIDECAR_INSTALL} not found or not executable — skipping sidecar"
else
    add "running ${SIDECAR_INSTALL}"
    # The sidecar installer is itself idempotent and prints its own report.
    # We run it inline so the user sees the token at the end of this script.
    bash "${SIDECAR_INSTALL}"
fi

# --- Phase 5: Final report ---
hdr "Done"

echo ""
echo "  BriefCase is installed."
echo ""
echo "  Next steps:"
echo "    1. Edit ${PROFILE_PATH} with your real role/team/projects."
echo "    2. Load the Chrome extension:"
echo "         - Open chrome://extensions"
echo "         - Toggle Developer mode"
echo "         - Load unpacked → ${PROJECT_ROOT}/extension"
echo "    3. Paste the sidecar auth token into the extension options:"
if [[ -s "${TOKEN_PATH}" ]]; then
    echo "         $(cat "${TOKEN_PATH}")"
    echo "       (or: cat ${TOKEN_PATH} | pbcopy)"
else
    echo "         (token will be at ${TOKEN_PATH} after the sidecar starts)"
fi
echo "    4. Restore your database from a backup if you have one:"
echo "         scripts/restore-db.sh <path-to-backup>"
echo "    5. Open Claude Code from any directory and run /kit to verify."
echo ""
echo "  Health checks:"
echo "    curl http://127.0.0.1:8989/health     # sidecar"
echo "    claude mcp list | grep ${MCP_NAME}    # MCP registration"
echo ""
