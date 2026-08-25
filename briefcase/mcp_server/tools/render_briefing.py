"""MCP Tool: render_briefing - Maintain Brendan's self-updating briefing doc.

The briefing is Brendan's pen-and-paper daily carry-over list, made
self-maintaining. It is a CO-AUTHORED working surface, NOT a projection of the
database. The doc is allowed to lead the DB (it holds backlog scoping threads,
gear tickets, and don't-forget items that aren't initiatives yet), and the DB
is often behind. This tool's job is to give Kit the raw material to reconcile
the two WITH Brendan, then commit the result he approves.

Four modes, matching the read-merge-reconcile flow plus the staged/promote path
the unattended transcript-sync job uses:

  mode='read'  (default) — gather step. Returns:
    - existing_doc: the current briefing.md verbatim (None if it doesn't exist)
    - staged_doc: briefing.staged.md verbatim if a staged proposal is waiting
      (e.g. from the overnight transcript-sync job), else None
    - snapshot: DB-side facts (initiatives + refs w/ assignee/status + members
      + pending decisions + orphan ticket refs + roster)
    - mismatches: batched list of stale/unrecorded things to surface to Brendan
    - scaffold: a starter template (only when the doc doesn't exist yet)
    - profile_buckets: project slugs/names from user_profile.yaml, so the agent
      groups by the same buckets Brendan already thinks in
    The agent treats Brendan's prose as durable truth, layers in what changed
    this conversation, surfaces the mismatches ("DB looks out of date — sync
    any?"), and drafts the merged doc. It NEVER writes without approval.

  mode='write' — commit step. Takes `content` (the approved merged markdown),
    stamps a meta footer (render timestamp), writes briefing.md, and ensures the
    ~/Desktop/Briefing.command launcher (double-click → opens the briefing in
    Obsidian via obsidian:// URI). Only call after Brendan approves.

  mode='staged' — the sub-agent path. Same as 'write' but targets
    briefing.staged.md and does NOT touch the Desktop launcher. The transcript-
    sync sub-agent calls this so Brendan's live Desktop launcher never changes
    under him — the staged proposal waits for his review.

  mode='promote' — accept the staged proposal. Moves briefing.staged.md →
    briefing.md (re-stamping the footer), ensures the launcher, and deletes the
    staged file. Called after Brendan reviews and approves the staged sync via
    the "briefing" / "catch me up" phrase. If `content` is provided, that
    approved-with-edits markdown is written to live instead of a raw copy.
    If the promoted content carries a <!-- sync-log:start/end --> block (the
    transcript-sync sub-agent's per-run summary), that block is archived
    verbatim — newest-first — to general/briefing-sync-log.md before being
    stripped from what actually lands in the live doc. This is the one place
    a sync run's findings persist past this review; the JSON freshness marker
    (briefing_sync_state) only remembers the most recent run, not history.

The DB is never mutated by this tool. Any DB corrections that come out of the
reconciliation happen via the normal tools (manage_initiative, add_external_ref,
update_external_ref, manage_initiative_members) — deliberately, so the write is
always a conscious choice.
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from briefcase.mcp_server.config import load_user_profile
from briefcase.mcp_server.database import (
    get_db_connection, get_briefing_snapshot, compute_briefing_mismatches,
)
from briefcase.mcp_server.obsidian import get_vault_path, read_file, write_file
from briefcase.mcp_server.refs import derive_ref_url

logger = logging.getLogger(__name__)

BRIEFING_RELATIVE_PATH = "briefing.md"
STAGED_RELATIVE_PATH = "briefing.staged.md"
META_FENCE_START = "<!-- briefing:meta"
META_FENCE_END = "-->"

# Permanent, append-only record of what each transcript sync found — durable
# even though the sync-log block itself is stripped from the promoted doc.
SYNC_LOG_RELATIVE_PATH = "general/briefing-sync-log.md"
SYNC_LOG_BLOCK_RE = re.compile(
    r"<!--\s*sync-log:start\s*-->(.*?)<!--\s*sync-log:end\s*-->\s*",
    re.DOTALL,
)

# Desktop launcher: a double-clickable .command that opens the briefing in
# Obsidian via the obsidian:// URI (opens inside the vault — backlinks, reading
# view, clickable ticket links — not as a standalone file).
DESKTOP_LAUNCHER = Path.home() / "Desktop" / "Briefing.command"
# Legacy artifact from the earlier symlink approach — cleaned up on write.
LEGACY_DESKTOP_LINK = Path.home() / "Desktop" / "Briefing.md"


def _scaffold(profile_buckets: list, today: str) -> str:
    """Starter template used only when no briefing.md exists yet. Groups by the
    buckets already in user_profile.yaml, plus the three durable zones."""
    lines = [
        f"# Briefing — {today}",
        "",
        "_Your carry-over list, self-maintaining. Item · owner · open loop · links._",
        "",
    ]
    for b in profile_buckets:
        lines.append(f"## {b['name']}")
        lines.append("- ")
        lines.append("")
    lines += [
        "## Watch / Don't Forget",
        "- ",
        "",
        "## Backlog / Scoping",
        "- ",
        "",
    ]
    return "\n".join(lines)


def _strip_meta(doc: str) -> str:
    """Remove any existing meta footer so re-renders don't stack footers."""
    idx = doc.find(META_FENCE_START)
    if idx == -1:
        return doc.rstrip("\n")
    return doc[:idx].rstrip("\n")


def _meta_footer(now: str) -> str:
    return (
        f"\n\n{META_FENCE_START}\n"
        f"  last_rendered: {now}\n"
        f"  source_of_truth: ~/Notes/ThriveNotes/{BRIEFING_RELATIVE_PATH}\n"
        f"  Edit this file freely — Kit reads it and treats your edits as truth.\n"
        f"{META_FENCE_END}\n"
    )


def _obsidian_uri() -> str:
    """Build the obsidian://open URI for the briefing. Vault name is the vault
    directory's basename (e.g. 'ThriveNotes'); file is the vault-relative path.
    URL-encode both so spaces/odd chars don't break the URI."""
    from urllib.parse import quote
    vault_name = get_vault_path().name
    return (f"obsidian://open?vault={quote(vault_name)}"
            f"&file={quote(BRIEFING_RELATIVE_PATH)}")


def _ensure_desktop_launcher() -> dict:
    """Idempotently maintain a double-clickable ~/Desktop/Briefing.command that
    opens the briefing in Obsidian via the obsidian:// URI. Also cleans up the
    legacy .md symlink from the earlier approach. Never raises out of the tool —
    a launcher failure shouldn't block the doc write.

    Requires the vault to be registered in Obsidian (i.e. ~/Notes/ThriveNotes
    added as a vault so it has a .obsidian folder). If it isn't, the .command is
    still created but Obsidian will report an unknown vault when clicked — we
    surface that as a hint rather than failing.
    """
    try:
        if not DESKTOP_LAUNCHER.parent.exists():
            return {"launched": False, "reason": "~/Desktop does not exist"}

        # Clean up the legacy symlink from the earlier approach.
        legacy_cleaned = False
        if LEGACY_DESKTOP_LINK.is_symlink():
            try:
                LEGACY_DESKTOP_LINK.unlink()
                legacy_cleaned = True
            except OSError:
                pass

        uri = _obsidian_uri()
        script = (
            "#!/bin/bash\n"
            "# Auto-generated by BriefCase render_briefing. Opens the briefing in Obsidian.\n"
            f"open '{uri}'\n"
        )

        # Idempotent: only rewrite if the content changed (e.g. vault renamed).
        existing = DESKTOP_LAUNCHER.read_text() if DESKTOP_LAUNCHER.exists() else None
        action = "already-current"
        if existing != script:
            DESKTOP_LAUNCHER.write_text(script)
            action = "updated" if existing is not None else "created"
        DESKTOP_LAUNCHER.chmod(0o755)  # executable so double-click runs it

        result = {
            "launched": True,
            "path": str(DESKTOP_LAUNCHER),
            "action": action,
            "uri": uri,
        }
        if legacy_cleaned:
            result["legacy_symlink_removed"] = True

        # Warn if the vault isn't actually registered in Obsidian.
        if not (get_vault_path() / ".obsidian").exists():
            result["hint"] = (
                f"{get_vault_path().name} has no .obsidian folder — it isn't registered "
                f"as an Obsidian vault yet. Open Obsidian → 'Open folder as vault' → "
                f"{get_vault_path()} so the launcher's obsidian:// URI resolves."
            )
        return result
    except OSError as e:
        return {"launched": False, "reason": str(e)}


def _extract_sync_log(doc: str) -> tuple:
    """Split a sync-log block out of a staged/promoted doc. Returns
    (doc_without_block, block_inner_text_or_None). The block is the
    <!-- sync-log:start/end --> comment the transcript-sync sub-agent
    prepends to its staged proposal — it's a review aid, not meant to
    live permanently in the briefing doc."""
    match = SYNC_LOG_BLOCK_RE.search(doc)
    if not match:
        return doc, None
    inner = match.group(1).strip()
    stripped = (doc[:match.start()] + doc[match.end():]).strip("\n")
    return stripped, inner


_SYNC_LOG_HEADER = (
    "# Briefing Sync Log\n\n"
    "_Append-only history of what each transcript sync found — newest first. "
    "Written automatically when a staged briefing is promoted; the sync-log "
    "block itself is stripped out of the live briefing.md at that point._\n"
)
_SYNC_LOG_ENTRY_MARKER = "\n\n<!-- entries below -->\n\n"


def _archive_sync_log(inner: str, today: str) -> str:
    """Prepend a completed sync-log entry (newest-first) to the permanent
    sync-log file, so review history survives past the promote that
    discards the block from the live briefing. The file header is written
    once and never duplicated — only entries accumulate. Returns the
    written path."""
    entry = f"## {today} sync\n\n{inner}\n"

    existing = read_file(SYNC_LOG_RELATIVE_PATH)
    if existing and _SYNC_LOG_ENTRY_MARKER in existing:
        _, prior_entries = existing.split(_SYNC_LOG_ENTRY_MARKER, 1)
        combined = (_SYNC_LOG_HEADER + _SYNC_LOG_ENTRY_MARKER
                    + entry + "\n---\n\n" + prior_entries.lstrip("\n"))
    else:
        # No marker means either a fresh file or a pre-existing file from
        # before this format existed — treat any prior content as the first
        # (oldest) entry rather than dropping it.
        prior_entries = existing.lstrip("\n") if existing else ""
        combined = _SYNC_LOG_HEADER + _SYNC_LOG_ENTRY_MARKER + entry
        if prior_entries:
            combined += "\n---\n\n" + prior_entries
    return write_file(SYNC_LOG_RELATIVE_PATH, combined, append=False)


def _profile_buckets() -> list:
    """Active project buckets from user_profile.yaml (slug + name)."""
    profile = load_user_profile()
    buckets = []
    for p in profile.get("projects", []) or []:
        if p.get("status") in ("archived", "completed", "done"):
            continue
        buckets.append({"slug": p.get("slug"), "name": p.get("name") or p.get("slug")})
    return buckets


def _enrich_ref_urls(snapshot: dict) -> None:
    """Back-fill ref_url on every ref so the agent can render links directly."""
    for init in snapshot.get("initiatives", []):
        for ref in init.get("refs", []):
            if not ref.get("ref_url"):
                ref["ref_url"] = derive_ref_url(ref.get("ref_type"), ref.get("ref_key"))
    for ref in snapshot.get("orphan_refs", []):
        if not ref.get("ref_url"):
            ref["ref_url"] = derive_ref_url(ref.get("ref_type"), ref.get("ref_key"))


async def render_briefing(
    mode: str = "read",
    content: Optional[str] = None,
    skip_launcher: bool = False,
) -> dict:
    """read (gather) / write (commit live) / staged (commit proposal) / promote
    (staged → live). See module docstring for the reconciliation flow."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")

        if mode in ("write", "staged"):
            if not content or not content.strip():
                return {
                    "status": "error",
                    "message": f"mode='{mode}' requires the merged markdown in `content`.",
                }
            body = _strip_meta(content)
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            full = body + _meta_footer(now)
            if mode == "staged":
                # Unattended path: write the staged proposal only, never the
                # live file, never the launcher. Brendan's Desktop stays put.
                written_path = write_file(STAGED_RELATIVE_PATH, full, append=False)
                return {
                    "status": "success",
                    "mode": "staged",
                    "path": written_path,
                    "relative_path": STAGED_RELATIVE_PATH,
                    "rendered_at": now,
                    "note": "Staged proposal written. Brendan reviews it via the "
                            "'briefing' phrase, then render_briefing(mode='promote').",
                }
            written_path = write_file(BRIEFING_RELATIVE_PATH, full, append=False)
            launcher = {"launched": False, "reason": "skipped"} if skip_launcher \
                else _ensure_desktop_launcher()
            return {
                "status": "success",
                "mode": "write",
                "path": written_path,
                "relative_path": BRIEFING_RELATIVE_PATH,
                "launcher": launcher,
                "rendered_at": now,
            }

        if mode == "promote":
            # Accept the staged proposal into the live doc. If `content` is
            # given (approved-with-edits), that wins over a raw copy.
            source = content if (content and content.strip()) else read_file(STAGED_RELATIVE_PATH)
            if not source or not source.strip():
                return {
                    "status": "error",
                    "message": "Nothing to promote — no briefing.staged.md and no `content` provided.",
                }
            # The sync-log block is a review aid, not durable briefing prose —
            # archive it to the permanent sync-log file, then strip it before
            # it lands in the live doc.
            body, sync_log_inner = _extract_sync_log(_strip_meta(source))
            sync_log_archived = None
            if sync_log_inner:
                sync_log_archived = _archive_sync_log(sync_log_inner, today)

            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            full = body + _meta_footer(now)
            written_path = write_file(BRIEFING_RELATIVE_PATH, full, append=False)
            launcher = _ensure_desktop_launcher()
            # Clear the staged file so it doesn't linger and re-surface.
            staged_path = get_vault_path() / STAGED_RELATIVE_PATH
            staged_cleared = False
            try:
                if staged_path.exists():
                    staged_path.unlink()
                    staged_cleared = True
            except OSError:
                pass
            return {
                "status": "success",
                "mode": "promote",
                "path": written_path,
                "relative_path": BRIEFING_RELATIVE_PATH,
                "launcher": launcher,
                "staged_cleared": staged_cleared,
                "sync_log_archived": sync_log_archived,
                "rendered_at": now,
            }

        if mode != "read":
            return {
                "status": "error",
                "message": f"Unknown mode '{mode}'. Use 'read', 'write', 'staged', or 'promote'.",
            }

        # --- read / gather ---
        existing_doc = read_file(BRIEFING_RELATIVE_PATH)
        staged_doc = read_file(STAGED_RELATIVE_PATH)
        buckets = _profile_buckets()

        conn = get_db_connection()
        try:
            snapshot = get_briefing_snapshot(conn)
            mismatches = compute_briefing_mismatches(conn, existing_doc or "", snapshot)
        finally:
            conn.close()

        _enrich_ref_urls(snapshot)

        result = {
            "status": "success",
            "mode": "read",
            "exists": existing_doc is not None,
            "existing_doc": existing_doc,
            "staged_doc": staged_doc,
            "has_staged": staged_doc is not None,
            "snapshot": snapshot,
            "mismatches": mismatches,
            "profile_buckets": buckets,
            "guidance": (
                "Reconcile, don't regenerate. Treat existing_doc's prose as durable truth. "
                "Layer in what changed this conversation + relevant snapshot facts. Surface "
                "`mismatches` to Brendan as a batched 'DB looks out of date — sync any?' "
                "checklist; act on his picks via manage_initiative / add_external_ref / "
                "update_external_ref / manage_initiative_members. The doc write NEVER blocks "
                "on DB sync. Present the merged draft for approval, THEN call "
                "render_briefing(mode='write', content=<approved markdown>). "
                "If has_staged is true, a proposal (e.g. overnight transcript sync) is "
                "waiting — walk Brendan through staged_doc vs existing_doc + the latest "
                "transcript-sync note, then render_briefing(mode='promote') on approval."
            ),
        }
        if existing_doc is None:
            result["scaffold"] = _scaffold(buckets, today)
        return result

    except Exception as e:
        logger.error(f"render_briefing error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "render_briefing"
TOOL_DESCRIPTION = (
    "Maintain Brendan's self-updating briefing doc (~/Notes/ThriveNotes/briefing.md, "
    "openable from a ~/Desktop/Briefing.command launcher) — his pen-and-paper carry-over list made "
    "self-maintaining. It's a CO-AUTHORED working surface, NOT a DB projection: it may "
    "hold backlog/scoping threads and don't-forget items that aren't initiatives yet, and "
    "it's allowed to lead a stale DB. mode='read' (default) gathers: existing doc verbatim, "
    "DB snapshot (initiatives + refs w/ assignee/status + members + pending decisions + "
    "orphan ticket refs), a batched mismatch report to reconcile with Brendan, and a "
    "scaffold if none exists, and a staged_doc if an unattended proposal is waiting. "
    "mode='write' commits approved markdown to the live doc + ensures the Desktop launcher. "
    "mode='staged' writes a proposal to briefing.staged.md WITHOUT touching the live file or "
    "launcher (the transcript-sync sub-agent's path). mode='promote' accepts a staged proposal "
    "into the live doc, clears the staged file, and — if the content carries a "
    "<!-- sync-log:start/end --> block — archives that block newest-first to "
    "general/briefing-sync-log.md (the durable record of past sync runs) before stripping it "
    "from the live doc. This tool NEVER mutates the DB — do that via the normal tools based "
    "on Brendan's picks."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["read", "write", "staged", "promote"],
            "description": "'read' (default) gathers doc + staged_doc + DB snapshot + "
                           "mismatches. 'write' commits approved markdown to the live "
                           "briefing.md + Desktop launcher. 'staged' commits a proposal to "
                           "briefing.staged.md (no launcher) — the sub-agent sync path. "
                           "'promote' moves staged → live (or writes `content` if given) "
                           "and clears the staged file.",
        },
        "content": {
            "type": "string",
            "description": "The merged briefing markdown. Required for 'write' and 'staged'. "
                           "Optional for 'promote' (approved-with-edits overrides the raw "
                           "staged copy). A meta footer is appended automatically.",
        },
        "skip_launcher": {
            "type": "boolean",
            "description": "mode='write' only. If true, don't touch the ~/Desktop launcher "
                           "(default false — the launcher is ensured idempotently).",
        },
    },
}

__all__ = ['render_briefing', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
