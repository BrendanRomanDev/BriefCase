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
    target_week TEXT,
    source TEXT,
    source_url TEXT,
    source_metadata TEXT,
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
    source TEXT,
    source_url TEXT,
    source_metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS triage_queue (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    content TEXT NOT NULL,
    metadata TEXT,
    flags TEXT,
    status TEXT DEFAULT 'pending',
    resolution TEXT,
    resolved_at TIMESTAMP,
    claimed_at TIMESTAMP,
    claimed_by TEXT,
    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

CREATE TABLE IF NOT EXISTS external_refs (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    ref_type TEXT NOT NULL,
    ref_key TEXT NOT NULL,
    ref_url TEXT,
    label TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_external_refs_entity
    ON external_refs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_external_refs_ref_key
    ON external_refs(ref_key);

CREATE TABLE IF NOT EXISTS decision_log (
    id INTEGER PRIMARY KEY,
    initiative_id INTEGER NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT,
    decided_at DATE,
    source_url TEXT,
    metadata TEXT,
    status TEXT DEFAULT 'pending',
    consumed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (initiative_id) REFERENCES initiatives(id)
);

CREATE INDEX IF NOT EXISTS idx_decision_log_initiative_status
    ON decision_log(initiative_id, status);
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
    """Create all tables if they don't exist, then run migrations."""
    conn = get_db_connection(db_path)
    conn.executescript(SCHEMA_SQL)
    _migrate(conn)
    conn.close()


def _migrate(conn):
    """Run schema migrations for existing databases."""
    inbox_columns = {row[1] for row in conn.execute("PRAGMA table_info(inbox)").fetchall()}
    if 'target_week' not in inbox_columns:
        conn.execute("ALTER TABLE inbox ADD COLUMN target_week TEXT")
    if 'source' not in inbox_columns:
        conn.execute("ALTER TABLE inbox ADD COLUMN source TEXT")
    if 'source_url' not in inbox_columns:
        conn.execute("ALTER TABLE inbox ADD COLUMN source_url TEXT")
    if 'source_metadata' not in inbox_columns:
        conn.execute("ALTER TABLE inbox ADD COLUMN source_metadata TEXT")
    if 'tags' not in inbox_columns:
        conn.execute("ALTER TABLE inbox ADD COLUMN tags TEXT")

    initiative_columns = {row[1] for row in conn.execute("PRAGMA table_info(initiatives)").fetchall()}
    if 'source' not in initiative_columns:
        conn.execute("ALTER TABLE initiatives ADD COLUMN source TEXT")
    if 'source_url' not in initiative_columns:
        conn.execute("ALTER TABLE initiatives ADD COLUMN source_url TEXT")
    if 'source_metadata' not in initiative_columns:
        conn.execute("ALTER TABLE initiatives ADD COLUMN source_metadata TEXT")

    triage_columns = {row[1] for row in conn.execute("PRAGMA table_info(triage_queue)").fetchall()}
    if 'flags' not in triage_columns:
        conn.execute("ALTER TABLE triage_queue ADD COLUMN flags TEXT")
    if 'claimed_at' not in triage_columns:
        conn.execute("ALTER TABLE triage_queue ADD COLUMN claimed_at TIMESTAMP")
    if 'claimed_by' not in triage_columns:
        conn.execute("ALTER TABLE triage_queue ADD COLUMN claimed_by TEXT")

    conn.commit()


# --- Inbox CRUD ---

def create_inbox_item(conn, title, description=None, complexity=None,
                      urgency=None, initiative_id=None, status='capture',
                      target_week=None, source=None, source_url=None,
                      source_metadata=None, tags=None) -> int:
    """Create inbox item, return its ID. tags accepts a list of strings."""
    if source_metadata is not None and not isinstance(source_metadata, str):
        source_metadata = json.dumps(source_metadata)
    tags_json = None
    if tags:
        if isinstance(tags, list):
            tags_json = json.dumps(tags)
        elif isinstance(tags, str):
            tags_json = tags
    cursor = conn.execute(
        """INSERT INTO inbox (title, description, complexity, urgency,
           initiative_id, status, target_week, source, source_url,
           source_metadata, tags, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, complexity or 1, urgency or 1,
         initiative_id, status, target_week, source, source_url,
         source_metadata, tags_json, datetime.now(UTC).isoformat())
    )
    conn.commit()
    return cursor.lastrowid


def get_inbox_items(conn, initiative_slug=None, status=None,
                    exclude_completed=True, target_week=None,
                    tags=None) -> list:
    """Query inbox items with optional filters.

    tags: list of tag strings. Returns items whose tags JSON contains ALL
    of the given tags (AND match). Pass a single string for a single-tag
    filter.
    """
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
    if target_week:
        conditions.append("i.target_week = ?")
        params.append(target_week)

    tag_filters = []
    if tags:
        tag_filters = [tags] if isinstance(tags, str) else list(tags)
    for t in tag_filters:
        # Naive substring match on the JSON column - good enough for short
        # controlled tag vocabularies. Stored format is '["tag1","tag2"]'.
        conditions.append("i.tags LIKE ?")
        params.append(f'%"{t}"%')

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY i.urgency DESC, i.complexity DESC, i.created_at DESC"

    rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        if d.get('tags'):
            try:
                d['tags'] = json.loads(d['tags'])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)
    return results


def complete_inbox_item(conn, item_id: int) -> bool:
    """Mark an inbox item as completed. Returns True if found."""
    cursor = conn.execute(
        "UPDATE inbox SET status = 'completed', completed_at = ? WHERE id = ?",
        (datetime.now(UTC).isoformat(), item_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def get_inbox_items_by_week_range(conn, week_start: str, week_end: str,
                                  exclude_completed=True) -> list:
    """Get inbox items whose target_week falls within a range (inclusive).

    week_start/week_end are ISO week strings like '2026-W14'.
    """
    query = "SELECT i.*, init.slug as initiative_slug FROM inbox i"
    query += " LEFT JOIN initiatives init ON i.initiative_id = init.id"
    conditions = ["i.target_week IS NOT NULL",
                  "i.target_week >= ?", "i.target_week <= ?"]
    params = [week_start, week_end]

    if exclude_completed:
        conditions.append("i.completed_at IS NULL")

    query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY i.target_week ASC, i.urgency DESC"

    rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        if d.get('tags'):
            try:
                d['tags'] = json.loads(d['tags'])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)
    return results


def delete_inbox_item(conn, item_id: int) -> bool:
    """Permanently delete an inbox item. Returns True if found."""
    cursor = conn.execute("DELETE FROM inbox WHERE id = ?", (item_id,))
    conn.commit()
    return cursor.rowcount > 0


# --- Initiative CRUD ---

def create_initiative(conn, name, slug, description=None, deadline=None,
                      tags=None, repo_path=None, obsidian_folder=None,
                      source=None, source_url=None, source_metadata=None) -> int:
    """Create an initiative, return its ID."""
    now = datetime.now(UTC).isoformat()
    if source_metadata is not None and not isinstance(source_metadata, str):
        source_metadata = json.dumps(source_metadata)
    cursor = conn.execute(
        """INSERT INTO initiatives (name, slug, description, deadline, tags,
           repo_path, obsidian_folder, source, source_url, source_metadata,
           created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, slug, description, deadline,
         json.dumps(tags) if tags else None,
         repo_path, obsidian_folder or f"Projects/{slug}",
         source, source_url, source_metadata, now, now)
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


def update_initiative(conn, slug: str, tags_mode: str = 'append', **kwargs) -> bool:
    """Update initiative fields. Returns True if found.

    tags_mode controls how `tags` is applied when provided:
      - 'append' (default): union of existing + new tags, de-duplicated,
        order preserved (existing first, then new).
      - 'replace': overwrite existing tags entirely with the given list.
      - 'remove': subtract the given tags from existing.
    """
    allowed = {'name', 'description', 'status', 'deadline', 'tags',
               'repo_path', 'obsidian_folder'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    if 'tags' in updates:
        new_tags = updates['tags'] if isinstance(updates['tags'], list) else []

        if tags_mode in ('append', 'remove'):
            row = conn.execute(
                "SELECT tags FROM initiatives WHERE slug = ?", (slug,)
            ).fetchone()
            if row is None:
                return False
            existing_tags = []
            if row['tags']:
                try:
                    existing_tags = json.loads(row['tags'])
                    if not isinstance(existing_tags, list):
                        existing_tags = []
                except (json.JSONDecodeError, TypeError):
                    existing_tags = []

            if tags_mode == 'append':
                merged = list(existing_tags)
                for t in new_tags:
                    if t not in merged:
                        merged.append(t)
                updates['tags'] = json.dumps(merged)
            else:  # remove
                remaining = [t for t in existing_tags if t not in new_tags]
                updates['tags'] = json.dumps(remaining)
        elif tags_mode == 'replace':
            updates['tags'] = json.dumps(new_tags)
        else:
            raise ValueError(f"Unknown tags_mode: {tags_mode}")

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


# --- Triage Queue ---

def _decode_triage_row(row) -> dict:
    """Decode a raw triage_queue row's JSON columns (metadata, flags)."""
    d = dict(row)
    for col in ('metadata', 'flags'):
        if d.get(col):
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def create_triage_item(conn, source: str, content: str, source_url: str = None,
                       title: str = None, metadata=None, flags=None) -> int:
    """Create a triage queue item, return its ID.

    flags is an optional dict of capture-time signals about what work this
    item will need (e.g. {"needs_jira": true, "needs_code_review": false,
    "search_around": true, "epic_hint": "THRIV-13413"}). Stored as JSON.
    Kit reads flags during the triage walk and adapts behavior accordingly.
    """
    if metadata is not None and not isinstance(metadata, str):
        metadata = json.dumps(metadata)
    if flags is not None and not isinstance(flags, str):
        flags = json.dumps(flags)
    cursor = conn.execute(
        """INSERT INTO triage_queue (source, source_url, title, content,
           metadata, flags, captured_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (source, source_url, title, content, metadata, flags,
         datetime.now(UTC).isoformat())
    )
    conn.commit()
    return cursor.lastrowid


def get_triage_items(conn, status: str = 'pending', limit: int = None) -> list:
    """Query triage queue items, optionally filtered by status."""
    query = "SELECT * FROM triage_queue"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY captured_at ASC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [_decode_triage_row(r) for r in rows]


def get_triage_item(conn, item_id: int) -> Optional[dict]:
    """Get a single triage queue item by ID."""
    row = conn.execute(
        "SELECT * FROM triage_queue WHERE id = ?", (item_id,)
    ).fetchone()
    if not row:
        return None
    return _decode_triage_row(row)


def resolve_triage_item(conn, item_id: int, resolution: str) -> bool:
    """Mark a triage queue item as resolved with a resolution label.

    Accepts both 'pending' (typical) and 'in_progress' (after a claim) as
    starting states. Returns True if the resolve happened.

    resolution examples: 'brain_dump', 'initiative', 'thrivenote',
    'daily_note', 'discarded', 'external'.
    """
    cursor = conn.execute(
        """UPDATE triage_queue
           SET status = 'resolved', resolution = ?, resolved_at = ?
           WHERE id = ? AND status IN ('pending', 'in_progress')""",
        (resolution, datetime.now(UTC).isoformat(), item_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def clear_resolved_triage_items(conn) -> int:
    """Delete all resolved triage queue items. Returns count deleted."""
    cursor = conn.execute("DELETE FROM triage_queue WHERE status = 'resolved'")
    conn.commit()
    return cursor.rowcount


def claim_triage_item(conn, item_id: int, claimed_by: str) -> bool:
    """Atomically flip a pending triage item to 'in_progress'. Returns True
    if the claim succeeded (item was pending), False if not (item was
    already claimed/resolved/missing).

    The atomicity is provided by the WHERE status='pending' clause: if
    another agent claimed first, our UPDATE matches zero rows.
    """
    cursor = conn.execute(
        """UPDATE triage_queue
           SET status = 'in_progress',
               claimed_at = ?,
               claimed_by = ?
           WHERE id = ? AND status = 'pending'""",
        (datetime.now(UTC).isoformat(), claimed_by, item_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def release_triage_item(conn, item_id: int) -> bool:
    """Flip an in_progress triage item back to 'pending'. Returns True if
    the release happened (item was in_progress), False if not.

    Use when an agent realizes it shouldn't be the one handling the item,
    or to manually clear a stale claim.
    """
    cursor = conn.execute(
        """UPDATE triage_queue
           SET status = 'pending',
               claimed_at = NULL,
               claimed_by = NULL
           WHERE id = ? AND status = 'in_progress'""",
        (item_id,)
    )
    conn.commit()
    return cursor.rowcount > 0


def get_pending_triage_count(conn) -> int:
    """Count pending triage queue items. Cheap check for startup checklists."""
    row = conn.execute(
        "SELECT COUNT(*) as n FROM triage_queue WHERE status = 'pending'"
    ).fetchone()
    return row['n'] if row else 0


# --- External Refs ---

VALID_ENTITY_TYPES = {'initiative', 'inbox'}


def _entity_exists(conn, entity_type: str, entity_id: int) -> bool:
    """Check whether the referenced entity row exists."""
    table = 'initiatives' if entity_type == 'initiative' else 'inbox'
    row = conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (entity_id,)).fetchone()
    return row is not None


def add_external_ref(conn, entity_type: str, entity_id: int, ref_type: str,
                     ref_key: str, ref_url: str = None,
                     label: str = None) -> int:
    """Attach an external ref (Jira ticket, Confluence page, Figma file, etc.)
    to an initiative or inbox item. Returns the new ref ID.
    """
    if entity_type not in VALID_ENTITY_TYPES:
        raise ValueError(f"entity_type must be one of {VALID_ENTITY_TYPES}")
    if not _entity_exists(conn, entity_type, entity_id):
        raise ValueError(f"{entity_type} #{entity_id} not found")
    cursor = conn.execute(
        """INSERT INTO external_refs
           (entity_type, entity_id, ref_type, ref_key, ref_url, label, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (entity_type, entity_id, ref_type, ref_key, ref_url, label,
         datetime.now(UTC).isoformat())
    )
    conn.commit()
    return cursor.lastrowid


def remove_external_ref(conn, ref_id: int) -> bool:
    """Delete an external ref by its ID. Returns True if found."""
    cursor = conn.execute("DELETE FROM external_refs WHERE id = ?", (ref_id,))
    conn.commit()
    return cursor.rowcount > 0


def get_external_refs(conn, entity_type: str = None, entity_id: int = None,
                      ref_type: str = None, ref_key: str = None) -> list:
    """Query external refs. All filters optional.

    Useful forms:
      - get_external_refs(entity_type='initiative', entity_id=17) -> all refs
        for a specific initiative
      - get_external_refs(ref_key='THRIV-13413') -> reverse lookup: every
        initiative/inbox item linked to this Jira key
      - get_external_refs(ref_type='jira_epic') -> all Jira epics tracked
    """
    query = "SELECT * FROM external_refs"
    conditions = []
    params = []
    if entity_type is not None:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if entity_id is not None:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if ref_type is not None:
        conditions.append("ref_type = ?")
        params.append(ref_type)
    if ref_key is not None:
        conditions.append("ref_key = ?")
        params.append(ref_key)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"

    return [dict(row) for row in conn.execute(query, params).fetchall()]


# --- Decision Log ---

def create_decision(conn, initiative_id: int, decision: str,
                    rationale: str = None, decided_at: str = None,
                    source_url: str = None, metadata=None) -> int:
    """Record a decision against an initiative. Returns the new row id.

    decided_at is an ISO date string ('YYYY-MM-DD'). If None, defaults to
    the current date (UTC).
    """
    if metadata is not None and not isinstance(metadata, str):
        metadata = json.dumps(metadata)
    if not decided_at:
        decided_at = datetime.now(UTC).date().isoformat()
    cursor = conn.execute(
        """INSERT INTO decision_log
           (initiative_id, decision, rationale, decided_at, source_url,
            metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (initiative_id, decision, rationale, decided_at, source_url,
         metadata, datetime.now(UTC).isoformat())
    )
    conn.commit()
    return cursor.lastrowid


def get_decisions(conn, initiative_id: int = None, initiative_slug: str = None,
                  status: str = None) -> list:
    """Query decision log. Filter by initiative (id or slug) and/or status.

    Returns rows with the joined initiative slug for convenience.
    """
    query = ("SELECT d.*, init.slug as initiative_slug, init.name as initiative_name "
             "FROM decision_log d "
             "LEFT JOIN initiatives init ON d.initiative_id = init.id")
    conditions = []
    params = []
    if initiative_id is not None:
        conditions.append("d.initiative_id = ?")
        params.append(initiative_id)
    if initiative_slug:
        conditions.append("init.slug = ?")
        params.append(initiative_slug)
    if status:
        conditions.append("d.status = ?")
        params.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY d.decided_at DESC, d.created_at DESC"

    rows = conn.execute(query, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        if d.get('metadata'):
            try:
                d['metadata'] = json.loads(d['metadata'])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(d)
    return results


def consume_decisions(conn, initiative_id: int = None,
                      initiative_slug: str = None,
                      ids: list = None) -> int:
    """Mark decisions as consumed (status='consumed').

    Filter mode:
      - If `ids` is provided, mark only those specific rows.
      - Else if initiative_id/slug is provided, mark all pending decisions
        for that initiative.
      - At least one filter must be specified to avoid mass-mutation.

    Returns the number of rows updated.
    """
    if not ids and initiative_id is None and not initiative_slug:
        raise ValueError("Must specify ids, initiative_id, or initiative_slug.")

    now = datetime.now(UTC).isoformat()

    if ids:
        placeholders = ",".join("?" for _ in ids)
        cursor = conn.execute(
            f"""UPDATE decision_log
                SET status = 'consumed', consumed_at = ?
                WHERE id IN ({placeholders}) AND status = 'pending'""",
            (now, *ids)
        )
    else:
        if initiative_id is None:
            row = conn.execute(
                "SELECT id FROM initiatives WHERE slug = ?", (initiative_slug,)
            ).fetchone()
            if not row:
                return 0
            initiative_id = row['id']
        cursor = conn.execute(
            """UPDATE decision_log
               SET status = 'consumed', consumed_at = ?
               WHERE initiative_id = ? AND status = 'pending'""",
            (now, initiative_id)
        )
    conn.commit()
    return cursor.rowcount


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
    tables = ['inbox', 'initiatives', 'initiative_members', 'dailies',
              'conversation_notes', 'triage_queue', 'external_refs',
              'decision_log']
    export = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        export[table] = [dict(row) for row in rows]
    conn.close()

    json_path = backup_path.replace('.db', '.json')
    with open(json_path, 'w') as f:
        json.dump(export, f, indent=2, default=str)

    return backup_path
