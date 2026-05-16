#!/usr/bin/env bash
# Restore the BriefCase SQLite database from a backup.
#
# Behaviour:
#   - With no args, lists local + iCloud backups and prompts you to pick one.
#   - With a path arg, restores from that file.
#   - Always takes a safety snapshot of the current DB (if one exists) into
#     ~/.briefcase/backups/ BEFORE overwriting. So restore is reversible.
#   - Verifies the source file with `sqlite3 ... 'PRAGMA integrity_check;'`
#     before touching the live DB.
#
# This is the script you run on a fresh machine right after setup.sh, with
# the most recent iCloud-mirrored backup as the source. Typical flow:
#
#   scripts/restore-db.sh \
#     "~/Library/Mobile Documents/com~apple~CloudDocs/BriefCase-Backups/briefcase_<stamp>.db"
#
# Usage:
#   scripts/restore-db.sh                 # interactive picker
#   scripts/restore-db.sh <path>          # restore from this file
#   scripts/restore-db.sh --latest        # restore most recent (local or iCloud)
#   scripts/restore-db.sh --force <path>  # skip safety prompts (still takes pre-restore snapshot)

set -euo pipefail

DB_PATH="${HOME}/.briefcase/briefcase.db"
BACKUP_DIR="${HOME}/.briefcase/backups"
ICLOUD_MIRROR="${HOME}/Library/Mobile Documents/com~apple~CloudDocs/BriefCase-Backups"

FORCE=0
LATEST=0
SOURCE=""

for arg in "$@"; do
    case "${arg}" in
        --force)  FORCE=1 ;;
        --latest) LATEST=1 ;;
        -h|--help)
            sed -n '2,/^set -e/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'
            exit 0
            ;;
        *) SOURCE="${arg}" ;;
    esac
done

say()  { echo "  $*"; }
hdr()  { echo ""; echo "=== $* ==="; }
warn() { echo "  [warn] $*"; }

# --- Pick a source if not provided ---
# Newest first by mtime. Filename-sort would mis-order pre-migration backups
# (e.g. briefcase_pre_mcp_migration_*) against timestamped ones.
list_backups() {
    {
        [[ -d "${BACKUP_DIR}" ]]     && find "${BACKUP_DIR}"     -maxdepth 1 -name 'briefcase_*.db' -print 2>/dev/null
        [[ -d "${ICLOUD_MIRROR}" ]]  && find "${ICLOUD_MIRROR}"  -maxdepth 1 -name 'briefcase_*.db' -print 2>/dev/null
    } | while IFS= read -r f; do
        printf "%d\t%s\n" "$(stat -f '%m' "${f}")" "${f}"
    done | sort -rn | cut -f2-
}

if [[ "${LATEST}" -eq 1 ]]; then
    SOURCE="$(list_backups | head -1 || true)"
    if [[ -z "${SOURCE}" ]]; then
        echo "ERROR: no backups found in ${BACKUP_DIR} or ${ICLOUD_MIRROR}" >&2
        exit 1
    fi
    say "Latest backup: ${SOURCE}"
fi

if [[ -z "${SOURCE}" ]]; then
    hdr "Available backups (newest first)"
    mapfile -t BACKUPS < <(list_backups)
    if [[ "${#BACKUPS[@]}" -eq 0 ]]; then
        echo "ERROR: no backups found in ${BACKUP_DIR} or ${ICLOUD_MIRROR}" >&2
        exit 1
    fi
    for i in "${!BACKUPS[@]}"; do
        printf "  [%d] %s\n" "$((i + 1))" "${BACKUPS[$i]}"
    done
    echo ""
    read -r -p "  Pick a number (or path), or Ctrl-C to abort: " choice
    if [[ "${choice}" =~ ^[0-9]+$ ]]; then
        idx=$((choice - 1))
        SOURCE="${BACKUPS[$idx]:-}"
        if [[ -z "${SOURCE}" ]]; then
            echo "ERROR: invalid selection." >&2
            exit 1
        fi
    else
        SOURCE="${choice}"
    fi
fi

# --- Validate source ---
SOURCE="${SOURCE/#\~/${HOME}}"  # expand leading ~

if [[ ! -f "${SOURCE}" ]]; then
    echo "ERROR: source file not found: ${SOURCE}" >&2
    exit 1
fi

if ! command -v sqlite3 &>/dev/null; then
    echo "ERROR: sqlite3 not on PATH. Install via Homebrew: brew install sqlite" >&2
    exit 1
fi

hdr "Verifying source"
say "Source: ${SOURCE}"
result="$(sqlite3 "${SOURCE}" 'PRAGMA integrity_check;' 2>&1 || true)"
if [[ "${result}" != "ok" ]]; then
    echo "ERROR: integrity check failed on ${SOURCE}:" >&2
    echo "${result}" >&2
    exit 1
fi
say "integrity_check: ok"

# --- Confirm overwrite ---
if [[ -f "${DB_PATH}" ]]; then
    current_size=$(du -h "${DB_PATH}" | awk '{print $1}')
    source_size=$(du -h "${SOURCE}"   | awk '{print $1}')
    current_mtime=$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "${DB_PATH}")
    source_mtime=$(stat -f '%Sm' -t '%Y-%m-%d %H:%M' "${SOURCE}")
    hdr "About to overwrite"
    printf "  current: %s  %s  %s\n" "${DB_PATH}" "${current_size}" "${current_mtime}"
    printf "  source : %s  %s  %s\n" "${SOURCE}"  "${source_size}"  "${source_mtime}"

    if [[ "${FORCE}" -ne 1 ]]; then
        read -r -p "  Proceed? [y/N] " confirm
        if [[ ! "${confirm}" =~ ^[yY]$ ]]; then
            echo "  Aborted." >&2
            exit 1
        fi
    fi
fi

# --- Safety snapshot of the existing DB ---
mkdir -p "${BACKUP_DIR}"
if [[ -f "${DB_PATH}" ]]; then
    STAMP="$(date +%Y%m%d_%H%M%S)"
    SAFETY="${BACKUP_DIR}/briefcase_pre_restore_${STAMP}.db"
    hdr "Safety snapshot"
    sqlite3 "${DB_PATH}" ".backup '${SAFETY}'"
    say "  current DB → ${SAFETY}"
fi

# --- Restore ---
hdr "Restoring"
cp "${SOURCE}" "${DB_PATH}"
say "  ${SOURCE} → ${DB_PATH}"

# Verify the live DB after copy.
result="$(sqlite3 "${DB_PATH}" 'PRAGMA integrity_check;' 2>&1 || true)"
if [[ "${result}" != "ok" ]]; then
    warn "post-restore integrity_check failed: ${result}"
    warn "your safety snapshot is in ${BACKUP_DIR} if you need to roll back"
    exit 1
fi
say "  integrity_check: ok"

echo ""
echo "  Restored. Restart the sidecar so it picks up the new DB:"
echo "    launchctl unload ~/Library/LaunchAgents/com.briefcase.sidecar.plist"
echo "    launchctl load -w ~/Library/LaunchAgents/com.briefcase.sidecar.plist"
echo ""
