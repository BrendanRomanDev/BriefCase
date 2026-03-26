#!/bin/bash
# BriefCase first-time setup
# Creates ~/.briefcase directory, database, vault directories, and user profile template

set -e

BRIEFCASE_DIR="$HOME/.briefcase"
DB_PATH="$BRIEFCASE_DIR/briefcase.db"
BACKUP_DIR="$BRIEFCASE_DIR/backups"
PROFILE_PATH="$BRIEFCASE_DIR/user_profile.yaml"
VAULT_PATH="$HOME/Notes/ThriveNotes"

echo "=== BriefCase Setup ==="

# Create directories
echo "Creating directories..."
mkdir -p "$BRIEFCASE_DIR"
mkdir -p "$BACKUP_DIR"

# Create Obsidian vault project directories
echo "Creating Obsidian vault structure..."
mkdir -p "$VAULT_PATH/Projects/insurance-management/meetings"
mkdir -p "$VAULT_PATH/Projects/symplr/meetings"
mkdir -p "$VAULT_PATH/Projects/credit-card-validation/meetings"
mkdir -p "$VAULT_PATH/Projects/ocr-patient-upload/meetings"
mkdir -p "$VAULT_PATH/Meetings/general"
mkdir -p "$VAULT_PATH/Career"
mkdir -p "$VAULT_PATH/Dailies"

# Initialize database
echo "Initializing database..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
source venv/bin/activate 2>/dev/null || true
python3 -c "
from briefcase.mcp_server.database import init_database
init_database('$DB_PATH')
print('Database initialized at $DB_PATH')
"

# Create user profile template if it doesn't exist
if [ ! -f "$PROFILE_PATH" ]; then
    echo "Creating user profile template..."
    cat > "$PROFILE_PATH" << 'YAML'
# ~/.briefcase/user_profile.yaml
name: Brendan
role: Tech Lead / Acting Product Manager
company: Thriveworks
team_name: ""
reports_to: ""

pm_context: |
  Diana (PM) is out for 3-5 months starting March 2026.
  Brendan is covering PM responsibilities during this period.
  Focus: project status tracking, stakeholder updates, deadline management.

responsibilities:
  - Tech lead across multiple projects
  - Individual contributor on Insurance Management
  - Acting PM: stakeholder updates, deadline tracking, sprint planning
  - Code review and architecture decisions
  - Developer mentorship and unblocking

team:
  - name: Akash
    role: Developer
    projects: [insurance-management, symplr]

projects:
  - slug: insurance-management
    name: Insurance Management
    description: ""
    repo: ""
    status: active
  - slug: symplr
    name: Symplr
    description: ""
    status: active
  - slug: credit-card-validation
    name: Credit Card Validation
    description: ""
    status: active
  - slug: ocr-patient-upload
    name: OCR Patient Upload Flows
    description: ""
    status: active

calendar_id: primary

obsidian_vault: ~/Notes/ThriveNotes

preferences:
  printing: true
  printer_connection: ssh
  ssh_print_host: ""
YAML
    echo "User profile template created at $PROFILE_PATH"
    echo "  -> Fill in team_name, reports_to, descriptions, and repo paths"
else
    echo "User profile already exists at $PROFILE_PATH, skipping."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit $PROFILE_PATH with your real team/project details"
echo "  2. Register the MCP server in Claude Code settings"
echo "  3. Test with: /kit"
