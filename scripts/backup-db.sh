#!/usr/bin/env bash
# Back up the BriefCase SQLite database.
#
# Uses SQLite's online backup API (via the sqlite3 CLI's `.backup` command),
# which produces a consistent snapshot even while the DB is being written to.
# Plain `cp` is unsafe here because the sidecar and the MCP server may both
# be holding the DB open.
#
# Backups are written to:
#   ~/.briefcase/backups/briefcase_YYYYMMDD_HHMMSS.db
#
# If an iCloud Drive root is present, the same file is also mirrored to:
#   ~/Library/Mobile Documents/com~apple~CloudDocs/BriefCase-Backups/
#
# That mirror is the recommended off-machine durability story — iCloud Drive
# is already provisioned on the work mac, the file is just a regular file,
# and on a new machine the same path will be syncing before you finish
# logging in. No extra tooling, no private git repo to maintain.
#
# Usage:
#   scripts/backup-db.sh           # standard backup, mirror to iCloud if present
#   scripts/backup-db.sh --local   # local only, skip iCloud
#   scripts/backup-db.sh --quiet   # suppress all but warnings/errors

set -euo pipefail

DB_PATH="${HOME}/.briefcase/briefcase.db"
BACKUP_DIR="${HOME}/.briefcase/backups"
ICLOUD_ROOT="${HOME}/Library/Mobile Documents/com~apple~CloudDocs"
ICLOUD_MIRROR="${ICLOUD_ROOT}/BriefCase-Backups"

LOCAL_ONLY=0
QUIET=0
for arg in "$@"; do
    case "${arg}" in
        --local) LOCAL_ONLY=1 ;;
        --quiet) QUIET=1 ;;
        -h|--help)
            sed -n '2,/^set -e/p' "$0" | sed 's/^# \{0,1\}//' | sed '$d'
            exit 0
            ;;
        *)
            echo "ERROR: unknown arg '${arg}' (try --help)" >&2
            exit 2
            ;;
    esac
done

say() { [[ "${QUIET}" -eq 1 ]] || echo "  $*"; }

if [[ ! -f "${DB_PATH}" ]]; then
    echo "ERROR: ${DB_PATH} does not exist. Nothing to back up." >&2
    exit 1
fi

if ! command -v sqlite3 &>/dev/null; then
    echo "ERROR: sqlite3 not on PATH. Install via Homebrew: brew install sqlite" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

STAMP="$(date +%Y%m%d_%H%M%S)"
LOCAL_DEST="${BACKUP_DIR}/briefcase_${STAMP}.db"

say "Backing up ${DB_PATH}"
sqlite3 "${DB_PATH}" ".backup '${LOCAL_DEST}'"
say "  → ${LOCAL_DEST} ($(du -h "${LOCAL_DEST}" | awk '{print $1}'))"

# Optional iCloud mirror.
if [[ "${LOCAL_ONLY}" -eq 1 ]]; then
    say "  (--local set; skipping iCloud mirror)"
elif [[ -d "${ICLOUD_ROOT}" ]]; then
    mkdir -p "${ICLOUD_MIRROR}"
    ICLOUD_DEST="${ICLOUD_MIRROR}/briefcase_${STAMP}.db"
    cp "${LOCAL_DEST}" "${ICLOUD_DEST}"
    say "  → ${ICLOUD_DEST} (iCloud Drive)"
else
    say "  (no iCloud Drive at ${ICLOUD_ROOT}; local only)"
fi

say "Done."
