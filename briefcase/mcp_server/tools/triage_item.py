"""MCP Tool: triage_item - Resolve a triage queue item into its destination."""

import json
import logging
from typing import Optional
from briefcase.mcp_server.database import (
    get_db_connection,
    get_triage_item,
    get_triage_children,
    resolve_triage_item,
    resolve_triage_item_with_children,
    create_inbox_item,
    create_initiative,
    get_initiative_by_slug,
)
from briefcase.mcp_server.obsidian import scaffold_initiative_folder

logger = logging.getLogger(__name__)


VALID_ACTIONS = {"brain_dump", "initiative", "thrivenote", "daily_note",
                 "kudos", "discard", "mark_resolved"}


# Map from queue-item flag key to tag applied to the resulting brain_dump
# or initiative. Flags that don't map to a tag (e.g. epic_hint, person_name,
# auto_file, is_decision) are not in this table - they're handled elsewhere
# or are purely advisory at capture time.
FLAG_TO_TAG = {
    'needs_code_research': 'needs_code_context',
    'needs_code_review': 'needs_code_context',  # legacy alias
    'needs_pr_review': 'needs_pr_review',
    'needs_web_research': 'web-research',
}


def _merge_flags_and_urls(parent_item: dict, children: list) -> tuple[dict, list]:
    """Union flags across parent + children (any-true wins) and collect all
    distinct source_urls in capture order. Returns (merged_flags, urls).
    """
    merged: dict = {}
    urls: list = []
    seen_urls: set = set()

    def _ingest(item: dict) -> None:
        flags = item.get('flags') or {}
        if isinstance(flags, dict):
            for k, v in flags.items():
                # Any-true wins for booleans; first-seen wins for everything else
                if isinstance(v, bool):
                    merged[k] = merged.get(k, False) or v
                elif k not in merged:
                    merged[k] = v
        url = item.get('source_url')
        if url and url not in seen_urls:
            urls.append(url)
            seen_urls.add(url)

    _ingest(parent_item)
    for child in children:
        _ingest(child)
    return merged, urls


def _derive_tags(merged_flags: dict, base_tags: Optional[list]) -> list:
    """Build the effective tag list for the resulting brain_dump/initiative.
    Starts from caller-supplied base_tags (if any), then adds tags from any
    matching flag in FLAG_TO_TAG. Deduplicates while preserving order.
    """
    effective = list(base_tags) if base_tags else []
    for flag_key, tag in FLAG_TO_TAG.items():
        if merged_flags.get(flag_key) and tag not in effective:
            effective.append(tag)
    return effective


def _build_combined_metadata(parent_item: dict, children: list,
                             merged_urls: list) -> dict:
    """Build the source_metadata blob carried onto the resulting
    brain_dump/initiative. Starts from the parent's metadata, layers in
    a list of source_urls (parent + all children) and a child_captures
    array summarizing attached items. If there are no children, the
    parent's metadata is returned essentially unchanged.
    """
    base = parent_item.get('metadata') or {}
    if isinstance(base, str):
        try:
            base = json.loads(base)
        except (json.JSONDecodeError, TypeError):
            base = {}
    if not isinstance(base, dict):
        base = {}

    metadata = dict(base)
    if len(merged_urls) > 1:
        metadata['source_urls'] = merged_urls
    if children:
        metadata['child_captures'] = [
            {
                'id': c['id'],
                'source': c.get('source'),
                'source_url': c.get('source_url'),
                'content': (c.get('content') or '')[:500],
            }
            for c in children
        ]
    return metadata


async def triage_item(
    item_id: int,
    action: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    complexity: Optional[int] = None,
    urgency: Optional[int] = None,
    initiative_slug: Optional[str] = None,
    target_week: Optional[str] = None,
    tags: Optional[list] = None,
    initiative_name: Optional[str] = None,
    initiative_deadline: Optional[str] = None,
    initiative_tags: Optional[list] = None,
    initiative_repo_path: Optional[str] = None,
    scaffold_obsidian_folder: bool = True,
    resolution_note: Optional[str] = None
) -> dict:
    """Resolve a triage queue item by routing it into its destination.

    Actions:
      - brain_dump: create an inbox item. Source URL + metadata from the
        queue item are carried onto the inbox item.
      - initiative: create a new initiative. Source URL + metadata are
        carried onto the initiative row. Use initiative_slug as the slug
        and initiative_name/_deadline/_tags/_repo_path for details.
      - thrivenote: mark the queue item resolved — the agent is expected
        to have filed the note to the vault separately (and must embed
        the source_url in the markdown body per the global thrive-notes
        rule). Use resolution_note to record what was filed.
      - daily_note: mark the queue item resolved — the agent is expected
        to have called plan_daily separately to add this to a day's notes.
      - kudos: mark the queue item resolved — the agent is expected to
        have drafted the kudos in Brendan's voice (destination=google-chat),
        gotten approval, pbcopied, AND appended an entry to
        ~/Notes/ThriveNotes/kudos/YYYY-kudos.md. Use resolution_note to
        record the recipient + file path.
      - discard: mark resolved with no further action.
      - mark_resolved: generic "I handled this externally" — optionally
        pass resolution_note.
    """
    try:
        if action not in VALID_ACTIONS:
            return {
                "status": "error",
                "message": f"Unknown action '{action}'. Valid: {sorted(VALID_ACTIONS)}"
            }

        conn = get_db_connection()
        queue_item = get_triage_item(conn, item_id)
        if not queue_item:
            conn.close()
            return {"status": "error", "message": f"Triage item #{item_id} not found"}
        if queue_item['status'] not in ('pending', 'in_progress'):
            conn.close()
            return {
                "status": "error",
                "message": f"Triage item #{item_id} already resolved as '{queue_item.get('resolution')}'"
            }

        # Refuse to triage a child directly - children resolve via their
        # parent. Surface the parent ID so the caller can redirect.
        if queue_item.get('parent_id'):
            conn.close()
            return {
                "status": "error",
                "message": (
                    f"Triage item #{item_id} is attached to #{queue_item['parent_id']}. "
                    f"Triage the parent instead - children resolve with it."
                )
            }

        children = get_triage_children(conn, item_id)
        merged_flags, merged_urls = _merge_flags_and_urls(queue_item, children)
        combined_metadata = _build_combined_metadata(queue_item, children, merged_urls)
        primary_source_url = merged_urls[0] if merged_urls else queue_item.get('source_url')

        result = {"status": "success", "triage_item_id": item_id, "action": action}
        if children:
            result["children_resolved"] = [c['id'] for c in children]

        if action == "brain_dump":
            if not title:
                conn.close()
                return {"status": "error", "message": "title is required for brain_dump action"}

            initiative_id = None
            if initiative_slug:
                initiative = get_initiative_by_slug(conn, initiative_slug)
                if not initiative:
                    conn.close()
                    return {"status": "error", "message": f"Initiative '{initiative_slug}' not found"}
                initiative_id = initiative['id']

            # Tags come from caller-supplied `tags` plus any tag that
            # FLAG_TO_TAG maps from a flag that's true on the parent or
            # any attached child (any-true wins).
            effective_tags = _derive_tags(merged_flags, tags)

            inbox_id = create_inbox_item(
                conn,
                title=title,
                description=description,
                complexity=complexity,
                urgency=urgency,
                initiative_id=initiative_id,
                target_week=target_week,
                source=queue_item.get('source'),
                source_url=primary_source_url,
                source_metadata=combined_metadata,
                tags=effective_tags or None,
            )
            result["inbox_item_id"] = inbox_id
            result["inbox_tags"] = effective_tags or None
            result["message"] = f"Brain dumped: {title}"

        elif action == "initiative":
            if not initiative_name or not initiative_slug:
                conn.close()
                return {
                    "status": "error",
                    "message": "initiative_name and initiative_slug are required for initiative action"
                }
            existing = get_initiative_by_slug(conn, initiative_slug)
            if existing:
                conn.close()
                return {"status": "error", "message": f"Initiative '{initiative_slug}' already exists"}

            effective_init_tags = _derive_tags(merged_flags, initiative_tags)

            initiative_id = create_initiative(
                conn,
                name=initiative_name,
                slug=initiative_slug,
                description=description,
                deadline=initiative_deadline,
                tags=effective_init_tags or None,
                repo_path=initiative_repo_path,
                source=queue_item.get('source'),
                source_url=primary_source_url,
                source_metadata=combined_metadata,
            )
            result["initiative_id"] = initiative_id
            result["initiative_slug"] = initiative_slug
            result["initiative_tags"] = effective_init_tags or None
            result["message"] = f"Created initiative: {initiative_name}"

            if scaffold_obsidian_folder:
                project_dir = scaffold_initiative_folder(
                    initiative_slug, initiative_name, description
                )
                result["obsidian_folder"] = str(project_dir)

        elif action == "thrivenote":
            result["message"] = "Marked as filed to ThriveNotes"
            if resolution_note:
                result["resolution_note"] = resolution_note

        elif action == "daily_note":
            result["message"] = "Marked as added to a daily"
            if resolution_note:
                result["resolution_note"] = resolution_note

        elif action == "kudos":
            result["message"] = "Marked as filed to kudos log"
            if resolution_note:
                result["resolution_note"] = resolution_note

        elif action == "discard":
            result["message"] = "Discarded"

        elif action == "mark_resolved":
            result["message"] = "Marked resolved"
            if resolution_note:
                result["resolution_note"] = resolution_note

        resolution_label = "discarded" if action == "discard" else action
        if children:
            cascaded = resolve_triage_item_with_children(
                conn, item_id, resolution_label
            )
            resolved = cascaded > 0
        else:
            resolved = resolve_triage_item(conn, item_id, resolution_label)
        conn.close()

        if not resolved:
            return {
                "status": "error",
                "message": f"Failed to mark triage item #{item_id} as resolved"
            }

        return result

    except Exception as e:
        logger.error(f"triage_item error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "triage_item"
TOOL_DESCRIPTION = (
    "Resolve a triage queue item by routing it into a destination: "
    "brain_dump (new inbox item), initiative (new project), thrivenote "
    "(agent filed externally), daily_note (agent added to a daily), "
    "kudos (agent drafted shout-out + appended to ~/Notes/ThriveNotes/kudos/"
    "YYYY-kudos.md), discard, or mark_resolved. Source URL + metadata are "
    "automatically carried onto brain_dump and initiative destinations. "
    "Always walks the user through the decision — do not call without their input."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "item_id": {"type": "integer", "description": "Triage queue item ID"},
        "action": {
            "type": "string",
            "enum": sorted(list(VALID_ACTIONS)),
            "description": "How to resolve this item"
        },
        "title": {"type": "string", "description": "Title for brain_dump action"},
        "description": {"type": "string", "description": "Description for brain_dump or initiative"},
        "complexity": {"type": "integer", "minimum": 1, "maximum": 3},
        "urgency": {"type": "integer", "minimum": 1, "maximum": 3},
        "initiative_slug": {
            "type": "string",
            "description": "For brain_dump: link to this existing initiative. For initiative: slug of the new initiative."
        },
        "target_week": {
            "type": "string",
            "description": "ISO week for brain_dump action (e.g. '2026-W15')"
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Tags for brain_dump action. The tag 'needs_code_context' is auto-added when the queue item's flags.needs_code_review is true; pass other tags here to extend."
        },
        "initiative_name": {"type": "string", "description": "Required for initiative action"},
        "initiative_deadline": {"type": "string", "description": "YYYY-MM-DD deadline for new initiative"},
        "initiative_tags": {"type": "array", "items": {"type": "string"}},
        "initiative_repo_path": {"type": "string", "description": "Path to git repo for new initiative"},
        "scaffold_obsidian_folder": {
            "type": "boolean",
            "description": "On initiative action, also create Projects/<slug>/ in the Obsidian vault. Defaults to true."
        },
        "resolution_note": {
            "type": "string",
            "description": "Freeform note about how the item was resolved (e.g. the path of a filed thrivenote)"
        }
    },
    "required": ["item_id", "action"]
}

__all__ = ['triage_item', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
