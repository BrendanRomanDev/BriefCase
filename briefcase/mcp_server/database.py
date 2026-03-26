"""Database connection management and CRUD helpers for BriefCase."""

import json
import shutil
import sqlite3
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional


# --- Schema ---

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    complexity INTEGER DEFAULT 1,
    urgency INTEGER DEFAULT 1,
    status TEXT DEFAULT 'capture',
    initiative_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    printed_at TIMESTAMP,
    scheduled_at TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (initiative_id) REFERENCES initiatives(id)
);

CREATE TABLE IF NOT EXISTS initiatives (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',
    obsidian_folder TEXT,
    deadline DATE,
    tags TEXT,
    repo_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS initiative_members (
    id INTEGER PRIMARY KEY,
    initiative_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    role TEXT,
    FOREIGN KEY (initiative_id) REFERENCES initiatives(id)
);

CREATE TABLE IF NOT EXISTS dailies (
    id INTEGER PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    tasks TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_notes (
    id INTEGER PRIMARY KEY,
    summary TEXT,
    next_intentions TEXT,
    topics TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# --- Connection ---

def get_db_connection(db_path: str = None) -> sqlite3.Connection:
    """Get database connection with foreign keys enabled."""
    if db_path is None:
        db_path = str(Path.home() / ".briefcase" / "briefcase.db")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_database(db_path: str = None):
    """Create all tables if they don't exist."""
    conn = get_db_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.close()


# --- Inbox CRUD ---

def create_inbox_item(conn, title, description=None, complexity=None,
                      urgency=None, initiative_id=None, status='capture') -> int:
    """Create inbox item, return its ID."""
    cursor = conn.execute(
        """INSERT INTO inbox (title, description, complexity, urgency,
           initiative_id, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (title, description, complexity or 1, urgency or 1,
         initiative_id, status, datetime.now(UTC).isoformat())
    )
    conn.commit()
    return cursor.lastrowid


def get_inbox_items(conn, initiative_slug=None, status=None,
                    exclude_completed=True) -> list:
    """Query inbox items with optional filters."""
    query = "SELECT i.*, init.slug as initiative_slug FROM inbox i"
    query += " LEFT JOIN initiatives init ON i.initiative_id = init.id"
    conditions = []
    params = []

    if exclude_completed and status is None:
        conditions.append("i.completed_at IS NULL")
    if status:
        conditions.append("i.status = ?")
        params.append(status)
    if initiative_slug:
        conditions.append("init.slug = ?")
        params.append(initiative_slug)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY i.urgency DESC, i.complexity DESC, i.created_at DESC"

    return [dict(row) for row in conn.execute(query, params).fetchall()]


def complete_inbox_item(conn, item_id: int) -> bool:
    """Mark an inbox item as completed. Returns True if found."""
    cursor = conn.execute(
        "UPDATE inbox SET status = 'completed', completed_at = ? WHERE id = ?",
        (datetime.now(UTC).isoformat(), item_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_inbox_item(conn, item_id: int) -> bool:
    """Permanently delete an inbox item. Returns True if found."""
    cursor = conn.execute("DELETE FROM inbox WHERE id = ?", (item_id,))
    conn.commit()
    return cursor.rowcount > 0


# --- Initiative CRUD ---

def create_initiative(conn, name, slug, description=None, deadline=None,
                      tags=None, repo_path=None, obsidian_folder=None) -> int:
    """Create an initiative, return its ID."""
    now = datetime.now(UTC).isoformat()
    cursor = conn.execute(
        """INSERT INTO initiatives (name, slug, description, deadline, tags,
           repo_path, obsidian_folder, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, slug, description, deadline,
         json.dumps(tags) if tags else None,
         repo_path, obsidian_folder or f"Projects/{slug}", now, now)
    )
    conn.commit()
    return cursor.lastrowid


def get_initiative_by_slug(conn, slug: str) -> Optional[dict]:
    """Look up an initiative by slug."""
    row = conn.execute(
        "SELECT * FROM initiatives WHERE slug = ?", (slug,)
    ).fetchone()
    return dict(row) if row else None


def get_all_initiatives(conn, status: str = None) -> list:
    """List initiatives, optionally filtered by status."""
    query = "SELECT * FROM initiatives"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY updated_at DESC"
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def update_initiative(conn, slug: str, **kwargs) -> bool:
    """Update initiative fields. Returns True if found."""
    allowed = {'name', 'description', 'status', 'deadline', 'tags',
               'repo_path', 'obsidian_folder'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    if 'tags' in updates and isinstance(updates['tags'], list):
        updates['tags'] = json.dumps(updates['tags'])

    updates['updated_at'] = datetime.now(UTC).isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [slug]

    cursor = conn.execute(
        f"UPDATE initiatives SET {set_clause} WHERE slug = ?", values
    )
    conn.commit()
    return cursor.rowcount > 0


# --- Initiative Members ---

def add_initiative_member(conn, initiative_id: int, name: str,
                          role: str = None) -> int:
    """Add a member to an initiative, return member ID."""
    cursor = conn.execute(
        "INSERT INTO initiative_members (initiative_id, name, role) VALUES (?, ?, ?)",
        (initiative_id, name, role)
    )
    conn.commit()
    return cursor.lastrowid


def remove_initiative_member(conn, initiative_id: int, name: str) -> bool:
    """Remove a member from an initiative. Returns True if found."""
    cursor = conn.execute(
        "DELETE FROM initiative_members WHERE initiative_id = ? AND name = ?",
        (initiative_id, name)
    )
    conn.commit()
    return cursor.rowcount > 0


def get_initiative_members(conn, initiative_id: int) -> list:
    """List members of an initiative."""
    return [dict(row) for row in conn.execute(
        "SELECT * FROM initiative_members WHERE initiative_id = ?",
        (initiative_id,)
    ).fetchall()]


# --- Dailies ---

def upsert_daily(conn, date: str, tasks: list, notes: str = None) -> int:
    """Create or update a daily plan. Returns the daily ID."""
    existing = conn.execute(
        "SELECT id FROM dailies WHERE date = ?", (date,)
    ).fetchone()

    tasks_json = json.dumps(tasks)

    if existing:
        conn.execute(
            "UPDATE dailies SET tasks = ?, notes = ? WHERE date = ?",
            (tasks_json, notes, date)
        )
        conn.commit()
        return existing['id']
    else:
        cursor = conn.execute(
            "INSERT INTO dailies (date, tasks, notes, created_at) VALUES (?, ?, ?, ?)",
            (date, tasks_json, notes, datetime.now(UTC).isoformat())
        )
        conn.commit()
        return cursor.lastrowid


def get_daily(conn, date: str) -> Optional[dict]:
    """Get a daily plan by date."""
    row = conn.execute(
        "SELECT * FROM dailies WHERE date = ?", (date,)
    ).fetchone()
    if row:
        result = dict(row)
        result['tasks'] = json.loads(result['tasks'])
        return result
    return None


def get_dailies_range(conn, start_date: str, end_date: str) -> list:
    """Get dailies in a date range."""
    rows = conn.execute(
        "SELECT * FROM dailies WHERE date BETWEEN ? AND ? ORDER BY date DESC",
        (start_date, end_date)
    ).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d['tasks'] = json.loads(d['tasks'])
        results.append(d)
    return results


# --- Conversation Notes ---

def save_conversation_note(conn, summary: str, next_intentions: str = None,
                           topics: list = None) -> int:
    """Save conversation notes, return note ID."""
    cursor = conn.execute(
        """INSERT INTO conversation_notes (summary, next_intentions, topics, created_at)
           VALUES (?, ?, ?, ?)""",
        (summary, next_intentions,
         json.dumps(topics) if topics else None,
         datetime.now(UTC).isoformat())
    )
    conn.commit()
    return cursor.lastrowid


def get_recent_conversation_notes(conn, days: int = 3) -> list:
    """Get conversation notes from the last N days."""
    rows = conn.execute(
        """SELECT * FROM conversation_notes
           WHERE created_at >= datetime('now', ?)
           ORDER BY created_at DESC""",
        (f"-{days} days",)
    ).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        if d['topics']:
            d['topics'] = json.loads(d['topics'])
        results.append(d)
    return results


# --- Backup ---

def backup_database(db_path: str = None, backup_dir: str = None,
                    note: str = None) -> str:
    """Create a timestamped database backup. Returns backup path."""
    if db_path is None:
        db_path = str(Path.home() / ".briefcase" / "briefcase.db")
    if backup_dir is None:
        backup_dir = str(Path.home() / ".briefcase" / "backups")

    Path(backup_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{note}" if note else ""
    backup_path = str(Path(backup_dir) / f"briefcase_{timestamp}{suffix}.db")

    shutil.copy2(db_path, backup_path)

    # Also export as JSON
    conn = get_db_connection(db_path)
    tables = ['inbox', 'initiatives', 'initiative_members', 'dailies', 'conversation_notes']
    export = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        export[table] = [dict(row) for row in rows]
    conn.close()

    json_path = backup_path.replace('.db', '.json')
    with open(json_path, 'w') as f:
        json.dump(export, f, indent=2, default=str)

    return backup_path
