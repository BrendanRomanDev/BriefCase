"""Obsidian vault read/write/search helpers for BriefCase."""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from briefcase.mcp_server.config import load_settings


def get_vault_path() -> Path:
    """Get the Obsidian vault path from settings."""
    settings = load_settings()
    return Path(settings['obsidian_vault']).expanduser()


def read_file(relative_path: str) -> Optional[str]:
    """Read a file from the vault. Returns None if not found."""
    path = get_vault_path() / relative_path
    if not path.exists():
        return None
    return path.read_text(encoding='utf-8')


def write_file(relative_path: str, content: str, append: bool = False):
    """Write or append to a file in the vault. Creates parent dirs if needed."""
    path = get_vault_path() / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)

    if append and path.exists():
        existing = path.read_text(encoding='utf-8')
        content = existing.rstrip('\n') + '\n\n' + content

    path.write_text(content, encoding='utf-8')
    return str(path)


def list_files(relative_dir: str, extension: str = '.md',
               sort_by_date: bool = True) -> list[dict]:
    """List files in a vault directory. Returns dicts with name, path, modified."""
    dir_path = get_vault_path() / relative_dir
    if not dir_path.exists():
        return []

    files = []
    for f in dir_path.iterdir():
        if f.is_file() and f.suffix == extension and not f.name.startswith('.'):
            files.append({
                'name': f.name,
                'path': str(Path(relative_dir) / f.name),
                'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })

    if sort_by_date:
        files.sort(key=lambda x: x['name'], reverse=True)

    return files


def list_recent_files(relative_dir: str, days: int = 14) -> list[dict]:
    """List files from the last N days, matching YYYY-MM-DD prefix in filename."""
    all_files = list_files(relative_dir)
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    recent = []
    for f in all_files:
        # Extract date from filename if it starts with YYYY-MM-DD
        match = re.match(r'^(\d{4}-\d{2}-\d{2})', f['name'])
        if match:
            file_date = match.group(1)
            if file_date >= cutoff:
                f['date'] = file_date
                recent.append(f)
        else:
            # Include non-dated files (like README.md) — they're always relevant
            recent.append(f)

    return recent


def search_vault(query: str, relative_dir: Optional[str] = None,
                 date_range: Optional[tuple[str, str]] = None,
                 max_results: int = 20) -> list[dict]:
    """Search vault files by keyword. Returns matching files with excerpts.

    Args:
        query: Search term (case-insensitive)
        relative_dir: Scope search to this directory (e.g., "Projects/insurance-management")
        date_range: Tuple of (start_date, end_date) in YYYY-MM-DD format
        max_results: Maximum number of results to return
    """
    vault = get_vault_path()
    search_root = vault / relative_dir if relative_dir else vault

    if not search_root.exists():
        return []

    query_lower = query.lower()
    results = []

    for root, dirs, files in os.walk(search_root):
        # Skip hidden dirs and legacy
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if not filename.endswith('.md'):
                continue

            filepath = Path(root) / filename
            relative = str(filepath.relative_to(vault))

            # Date range filter
            if date_range:
                match = re.match(r'^(\d{4}-\d{2}-\d{2})', filename)
                if match:
                    file_date = match.group(1)
                    if file_date < date_range[0] or file_date > date_range[1]:
                        continue

            try:
                content = filepath.read_text(encoding='utf-8')
            except (UnicodeDecodeError, PermissionError):
                continue

            if query_lower in content.lower():
                # Extract excerpt around the match
                idx = content.lower().find(query_lower)
                start = max(0, idx - 100)
                end = min(len(content), idx + len(query) + 100)
                excerpt = content[start:end].strip()
                if start > 0:
                    excerpt = '...' + excerpt
                if end < len(content):
                    excerpt = excerpt + '...'

                results.append({
                    'path': relative,
                    'filename': filename,
                    'excerpt': excerpt
                })

                if len(results) >= max_results:
                    return results

    return results


def build_meeting_note(title: str, date: str, initiative_slug: Optional[str],
                       attendees: list[str], tags: list[str],
                       summary: str, key_decisions: list[str],
                       action_items: list[str], raw_notes: str) -> str:
    """Build a formatted meeting note with YAML frontmatter."""
    frontmatter_lines = [
        '---',
        f'date: {date}',
    ]
    if initiative_slug:
        frontmatter_lines.append(f'initiative: {initiative_slug}')
    if attendees:
        frontmatter_lines.append(f'attendees: [{", ".join(attendees)}]')
    if tags:
        frontmatter_lines.append(f'tags: [{", ".join(tags)}]')
    frontmatter_lines.append('---')

    sections = ['\n'.join(frontmatter_lines), '']
    sections.append(f'# {title}')
    sections.append('')

    if summary:
        sections.append('## Summary')
        sections.append(summary)
        sections.append('')

    if key_decisions:
        sections.append('## Key Decisions')
        for decision in key_decisions:
            sections.append(f'- {decision}')
        sections.append('')

    if action_items:
        sections.append('## Action Items Discussed')
        for item in action_items:
            sections.append(f'- {item}')
        sections.append('')

    sections.append('## Raw Notes')
    sections.append(raw_notes)
    sections.append('')

    return '\n'.join(sections)


def get_initiative_folder(slug: str) -> str:
    """Get the vault-relative path for an initiative's folder."""
    return f"Projects/{slug}"


def get_meetings_folder(slug: str) -> str:
    """Get the vault-relative path for an initiative's meetings folder."""
    return f"Projects/{slug}/meetings"


def meeting_note_path(slug: Optional[str], date: str, title: str) -> str:
    """Generate the vault-relative path for a meeting note file."""
    # Slugify the title for filename
    safe_title = re.sub(r'[^\w\s-]', '', title.lower())
    safe_title = re.sub(r'[\s]+', '-', safe_title).strip('-')

    if slug:
        return f"Projects/{slug}/meetings/{date}-{safe_title}.md"
    else:
        return f"Meetings/general/{date}-{safe_title}.md"
