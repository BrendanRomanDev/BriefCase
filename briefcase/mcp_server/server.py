"""BriefCase MCP Server - Kit's backend for work planning."""

import json
import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

VERSION = "0.9.1"

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """Kit: Your Work Planning Companion

CONVERSATION START CHECKLIST:
1. gcal_list_events (next 14 days) - Google Calendar events
2. get_forecast(days=14) - Initiative deadlines + inbox status + targeted items + current time
3. get_recent_activity(days=3) - Recent dailies and session context
4. get_triage_queue() - Pending captures from the Chrome extension (web clips, Google Chat messages). If count > 0, mention it in the greeting — do NOT auto-walk. Wait for the user to say "triage" before stepping through items.
5. Read ~/.briefcase/user_profile.yaml - Role, team, projects
6. list_pdlc_projects() - PDLC projects in Brendan's lane. If any return with empty briefcase_links, mention unlinked count in the greeting (one line). Do NOT auto-walk — wait for the user to say "walk PDLC" or "align PDLC."
7. Check for current week's rollup - If Monday/Tuesday and no rollup exists, generate with weekly_rollup()

TOOL QUICK GUIDE:
- brain_dump: Capture tasks, optionally link to initiative. target_week param for week-level scheduling. Accepts source, source_url, source_metadata for captures that came from elsewhere (e.g. Google Chat).
- get_capture_list: Query inbox, filter by initiative/status/target_week. Items may carry source_url — render as clickable links back to origin when present.
- complete_task / delete_task: Task lifecycle
- get_triage_queue: List pending captures awaiting triage. Each item has source, source_url, content, metadata.
- triage_item: Resolve a queue item into brain_dump / initiative / thrivenote / daily_note / discard. Source URL + metadata carry forward automatically on brain_dump and initiative destinations.
- clear_triage_queue: Delete resolved items from the queue (history cleanup).
- manage_initiative: CRUD for projects/initiatives. Create action accepts source fields for origins.
- manage_initiative_members: Add/remove/list team members
- add_external_ref / remove_external_ref / list_external_refs: Attach Jira tickets, Confluence pages, Figma files, etc. to initiatives or inbox items. ref_type='jira_epic' or 'jira_ticket' auto-derives the URL from integrations.jira.base_url in settings.yaml. Use for every initiative that has a real-world ticket home and for inbox items that relate to a specific remote artifact.
- plan_daily: Save daily task plan (calendar events handled by agent separately)
- query_daily: Look up a day's task plan
- get_forecast: DB-side forecast (deadlines, inbox, targeted items, current time) - agent merges with gcal
- get_recent_activity: Recent dailies and session notes
- file_meeting_notes: Paste notes → filed in Obsidian → summary + proposed actions
- search_notes: Search Obsidian vault by keyword, scoped to initiative/date
- get_initiative_status: Full status with DB + Obsidian notes + optional gh CLI
- draft_status_update: Gather context for agent to draft stakeholder update
- project_retro: Week-by-week retrospective with velocity trends
- weekly_rollup: Generate weekly executive summary (meetings, decisions, work, look-ahead) → Obsidian
- save_conversation_notes: Save session context at end of conversation
- print_daily_list: Print daily checklist receipt (template adds checkboxes)
- print_custom: Print any markdown content as a receipt
- backup_database: Create timestamped backup
- list_pdlc_projects / get_pdlc_project / resolve_pdlc_project: Read-only bridge into the product team's PDLC repo (~/Programming/pdlc/). Default lane filter: team=client-experience OR tech_lead=Brendan Roman.

PRINTING FORMAT RULES:
- ALWAYS use 12-hour time: "2:00 PM" not "14:00"
- Events: NO checkbox, just "2:00 PM - Meeting Name"
- Tasks: Checkbox added automatically, just pass "Task description"
- Work items: Tag with [initiative-slug]
- DO NOT add manual checkbox characters — the template handles them

BRAIN DUMP vs DAILY NOTES vs TARGET WEEK:
- brain_dump is for LOOSE captures with no specific day — things to triage later.
- brain_dump with target_week (e.g. '2026-W15') is for items that should happen in a specific week but don't have an exact day. These surface in get_forecast and during daily planning for that week.
- plan_daily(notes=...) is for TIME-BOUND work tied to a specific day or sequence.
- If the user describes work for Monday/Tuesday/etc, put it in daily notes, NOT brain dump.
- If the user says "next week" or "this week" without a specific day, use brain_dump with target_week.
- When unsure, ASK: "Brain dump for later, target a specific week, or slot into [day]'s notes?"
- When brain dumping action items from meetings or conversations, ALWAYS include a description with context: which meeting, who said it, why it matters, what depends on it. Titles are short and actionable. Descriptions give enough context to pick up the item cold.

WEEKLY ROLLUP:
- weekly_rollup generates an executive summary saved to ThriveNotes/weeklies/.
- On Monday/Tuesday, if no rollup exists for the previous week, generate one before planning.
- The rollup gathers: meeting notes from Obsidian, dailies, conversation notes, inbox activity.
- Use it to brief the user on what happened last week and what's coming up.
- Also available on-demand: "Roll up last week" or "Give me a summary of W14."

TRIAGE QUEUE FLOW:
- The Chrome extension POSTs captures to a local sidecar which writes to the triage_queue table.
- At conversation start, get_triage_queue is called. If non-empty, mention count in greeting — do NOT auto-walk.
- When the user says "triage" (or similar), walk items 1x1. For each item, surface source, source_url, content, metadata (sender, channel, thread preview), AND any capture-time flags. Ask the user what to do.
- Decisions route via triage_item:
  - brain_dump: creates inbox item, source_url + metadata carry forward automatically.
  - initiative: creates new initiative, source_url + metadata carry forward.
  - thrivenote: YOU file to the vault first (obey global ~/.claude/rules/thrive-notes.md — confirm placement, embed source_url in markdown body as "Source: [link](url)"), THEN call triage_item with action='thrivenote'.
  - daily_note: YOU call plan_daily first, THEN triage_item action='daily_note'.
  - discard / mark_resolved: just route the triage.
- Never silently promote queue items. Every triage action is a user decision.
- When rendering inbox items that carry source_url, include "[open in <source>]" link inline so the user can jump to origin.

CAPTURE-TIME FLAGS:
Each triage_queue item may carry a `flags` dict set in the Chrome extension compose popup. Surface these prominently when presenting the item, and act on them DURING the triage conversation:
- `is_brain_dump: true` → user has pre-decided the destination. Skip the "what should I do with this?" question and route straight to brain_dump. Still confirm title/description/complexity/urgency/initiative_slug/target_week with the user before calling triage_item — the destination is known but the metadata isn't.
- `search_around: true` → BEFORE proposing actions, run search_notes on key terms from the content, run get_capture_list filtered by initiative or relevant terms, and check existing initiatives for related context. Surface what you found ("found 2 related notes, 1 inbox item, possibly relates to <initiative>") so the user has context for their decision.
- `needs_jira: true` → propose drafting a Jira ticket. If `epic_hint` is also set, propose that as the parent epic. If atlassian MCP is available, draft → confirm → create via mcp__atlassian__createJiraIssue → record via add_external_ref on whichever entity gets created. If atlassian MCP is unavailable in the current session, draft the body for paste-out.
- `needs_code_review: true` → after triage resolves into an inbox item or initiative, set tags=['needs_code_context'] on the resulting entity (via brain_dump's tags param or via manage_initiative tags=['needs_code_context'] tags_mode='append'). This is what a future Thriveworks-repo session will query for.
- `needs_meeting: true` → schedule a meeting on Brendan's behalf. Steps: (1) Determine attendees - prefer flags.meeting_attendees if present (already a list of emails); else extract names/handles from content/context and ASK Brendan for emails. (2) Ask Brendan for missing details: duration (default 30 min), timeframe (default 'next 5 business days, work hours, exclude weekends'), agenda/topic (default: pull from captured content). (3) Call mcp__claude_ai_Google_Calendar__suggest_time(attendeeEmails=[brendan + attendees], startTime, endTime, durationMinutes, preferences={startHour:'09:00', endHour:'17:00', excludeWeekends:true}). (4) Present 2-3 proposed times — Brendan picks one or pushes back. (5) On approval, call mcp__claude_ai_Google_Calendar__create_event with summary, startTime/endTime, attendeeEmails, description (use captured content + context as agenda), timeZone='America/New_York'. (6) Confirm with the event link. If gcal MCP is unavailable in this session, draft an availability email Brendan can send instead.
- `needs_reply: true` → the captured content is something Brendan needs to reply to (Google Chat message, email thread, etc.). Ask: "Draft a reply now, or save for later?" If now → Read ~/.claude/rules/brendan-voice-profile.md, then draft the reply inline using the captured message + any user_context as the prompt, present for approval, optionally pbcopy. If later → tag the resulting inbox item with 'needs_reply' (in addition to any other tags) so future triage walks surface it as needing a draft. When walking the queue and you encounter an inbox item already tagged 'needs_reply', proactively offer to draft the reply at that time.
- `is_decision: true` → the captured content represents a decision that should be filed in an initiative-scoped decision log. Determine the initiative: prefer an explicit slug in user_context ('insurance-management — agreed to scrap full edit mode'), otherwise infer from content/source, otherwise ASK. Then synthesize: a one-line `decision`, an optional `rationale` paragraph, and `decided_at` (ISO date — pull from chat timestamps in metadata if present, else today UTC). Confirm with Brendan before filing. Call `record_decision(decision, initiative_slug, rationale, decided_at, source_url, metadata)`. The decision lives at status='pending' until a downstream session consumes it. On the triage_item side, this can either resolve as 'mark_resolved' (decision filed, no inbox item needed) or run alongside brain_dump (capture as both — reference for now, decision filed for the dev session). Brendan's call.
Multiple flags may be set on the same item — handle them in this order: search_around (informs everything else) → triage destination (driven by is_brain_dump if set, else user choice) → needs_jira / needs_code_review / needs_meeting / needs_reply / is_decision (post-resolution side-effects).

DECISION LOG (downstream consumption):
- record_decision adds rows to decision_log table, scoped to an initiative_id. Status starts 'pending'.
- get_decision_log(initiative_slug, status='pending') returns decisions ready to be filed somewhere downstream (e.g. a Thriveworks-repo decisions.md). Default 'pending'; pass 'all' for history.
- consume_decisions(initiative_slug=... OR decision_ids=[...]) flips rows to 'consumed' (keeps history with consumed_at). Use after a downstream session has filed them — typically a Thriveworks-repo dev session that read get_decision_log, updated decisions.md in the branch, and now needs to mark them as filed.
- Brendan's typical workflow: capture decisions throughout the day with is_decision flag, Kit triages and records each, accumulating in pending state per initiative. Later, in the Thriveworks repo on a feature branch, he asks his dev agent to "check briefcase decisions for <initiative> and update decisions.md". Dev agent reads, files, then calls consume_decisions. BriefCase never writes to repo files — the dev agent owns that.

PDLC BRIDGE (READ-ONLY):
- PDLC is the product team's source of truth — phase, gates, PRDs, stakeholders. Lives at ~/Programming/pdlc/ as plain YAML.
- Kit READS PDLC freely. Kit NEVER writes to PDLC files directly.
- Linkage: tag BriefCase initiatives with `pdlc-project:<id>` (e.g. `pdlc-project:ce-004`) or `pdlc-initiative:<id>` (e.g. `pdlc-initiative:ce-i002`) via manage_initiative update. tags_mode defaults to 'append' so existing tags persist.
- When Brendan wants to update PDLC state, hand off to PDLC's own slash commands (available from any cwd): /pdlc:update-context, /pdlc:update-prd, /pdlc:prepare-gate, /pdlc:draft-prd, /pdlc:status, /pdlc:stakeholder-roadmap, /pdlc:start-project.
- On activation, list_pdlc_projects surfaces any lane project without a Kit link — mention the unlinked count in the greeting; wait for user to say "walk PDLC" or "align PDLC" before acting.
- When resolving topic references ("the medicare thing"), use resolve_pdlc_project for fuzzy name-to-id lookup.

EXTERNAL REFS:
- External refs (Jira tickets, Confluence pages, Figma files, etc.) live in the external_refs table and can attach to either an initiative or an inbox item.
- When rendering initiative status, capture-list items, or status updates, always call list_external_refs(entity_type, entity_id) and surface the refs as clickable links inline. ref_url comes back canonical; for Jira keys it is derived from integrations.jira.base_url.
- When Brendan creates a Jira ticket (via the atlassian MCP when available), immediately follow up with add_external_ref to record the linkage.
- When Brendan mentions a Jira key (e.g. "THRIV-12345") in conversation, offer to record it as an external ref on the relevant initiative or inbox item.
- Reverse lookup: list_external_refs(ref_key='THRIV-12345') to find every local entity tied to a given ticket.

CRITICAL RULES:
- Events live in Google Calendar, NOT the database.
- The agent calls gcal_list_events separately and merges with DB data.
- plan_daily stores TASKS only. Events are referenced, not duplicated.
- get_forecast returns current time so the agent can determine past vs upcoming.
- Never auto-create tasks from meeting notes. Always conversational triage.
- Never silently triage queue items. Always walk the user through each decision.
- Never edit files in ~/Programming/pdlc/. All PDLC writes go through /pdlc:* slash commands.
"""


# --- Tool import generators ---

def _import_brain_dump_tools():
    """Import brain dump and task tools."""
    from briefcase.mcp_server.tools.brain_dump import (
        brain_dump, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, brain_dump

    from briefcase.mcp_server.tools.get_capture_list import (
        get_capture_list, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, get_capture_list

    from briefcase.mcp_server.tools.complete_task import (
        complete_task, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, complete_task

    from briefcase.mcp_server.tools.delete_task import (
        delete_task, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, delete_task


def _import_triage_tools():
    """Import triage queue tools (inbound captures from Chrome extension)."""
    from briefcase.mcp_server.tools.get_triage_queue import (
        get_triage_queue, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, get_triage_queue

    from briefcase.mcp_server.tools.triage_item import (
        triage_item, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, triage_item

    from briefcase.mcp_server.tools.clear_triage_queue import (
        clear_triage_queue, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, clear_triage_queue


def _import_initiative_tools():
    """Import initiative management tools."""
    from briefcase.mcp_server.tools.manage_initiative import (
        manage_initiative, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, manage_initiative

    from briefcase.mcp_server.tools.manage_initiative_members import (
        manage_initiative_members, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, manage_initiative_members


def _import_external_ref_tools():
    """Import external-ref tools (Jira/Confluence/Figma links on initiatives and inbox)."""
    from briefcase.mcp_server.tools.add_external_ref import (
        add_external_ref, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, add_external_ref

    from briefcase.mcp_server.tools.remove_external_ref import (
        remove_external_ref, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, remove_external_ref

    from briefcase.mcp_server.tools.list_external_refs import (
        list_external_refs, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, list_external_refs


def _import_decision_log_tools():
    """Import decision-log tools (per-initiative decision capture/consume)."""
    from briefcase.mcp_server.tools.record_decision import (
        record_decision, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, record_decision

    from briefcase.mcp_server.tools.get_decision_log import (
        get_decision_log, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, get_decision_log

    from briefcase.mcp_server.tools.consume_decisions import (
        consume_decisions, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, consume_decisions


def _import_daily_tools():
    """Import daily planning tools."""
    from briefcase.mcp_server.tools.plan_daily import (
        plan_daily, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, plan_daily

    from briefcase.mcp_server.tools.query_daily import (
        query_daily, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, query_daily

    from briefcase.mcp_server.tools.get_forecast import (
        get_forecast, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, get_forecast

    from briefcase.mcp_server.tools.get_recent_activity import (
        get_recent_activity, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, get_recent_activity


def _import_meeting_tools():
    """Import meeting intelligence tools."""
    from briefcase.mcp_server.tools.file_meeting_notes import (
        file_meeting_notes, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, file_meeting_notes

    from briefcase.mcp_server.tools.search_notes import (
        search_notes, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, search_notes

    from briefcase.mcp_server.tools.get_initiative_status import (
        get_initiative_status, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, get_initiative_status


def _import_reporting_tools():
    """Import status and reporting tools."""
    from briefcase.mcp_server.tools.draft_status_update import (
        draft_status_update, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, draft_status_update

    from briefcase.mcp_server.tools.project_retro import (
        project_retro, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, project_retro

    from briefcase.mcp_server.tools.weekly_rollup import (
        weekly_rollup, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, weekly_rollup


def _import_printing_tools():
    """Import printing tools (behind features.printing flag)."""
    from briefcase.mcp_server.tools.print_daily_list import (
        print_daily_list, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, print_daily_list

    from briefcase.mcp_server.tools.print_custom import (
        print_custom, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, print_custom


def _import_system_tools():
    """Import system tools."""
    from briefcase.mcp_server.tools.save_conversation_notes import (
        save_conversation_notes, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, save_conversation_notes

    from briefcase.mcp_server.tools.backup_database import (
        backup_database, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, backup_database


def _import_pdlc_tools():
    """Import read-only PDLC bridge tools."""
    from briefcase.mcp_server.tools.get_pdlc_project import (
        get_pdlc_project, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, get_pdlc_project

    from briefcase.mcp_server.tools.list_pdlc_projects import (
        list_pdlc_projects, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, list_pdlc_projects

    from briefcase.mcp_server.tools.resolve_pdlc_project import (
        resolve_pdlc_project, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, resolve_pdlc_project


# --- Server class ---

class BriefCaseServer:
    def __init__(self):
        self._tool_handlers = {}
        self._tool_definitions = []

        self.server = Server(
            name="briefcase",
            version=VERSION,
            instructions=SERVER_INSTRUCTIONS
        )

        self._register_tool_batch(_import_brain_dump_tools())
        self._register_tool_batch(_import_triage_tools())
        self._register_tool_batch(_import_initiative_tools())
        self._register_tool_batch(_import_external_ref_tools())
        self._register_tool_batch(_import_decision_log_tools())
        self._register_tool_batch(_import_daily_tools())
        self._register_tool_batch(_import_meeting_tools())
        self._register_tool_batch(_import_reporting_tools())
        self._register_tool_batch(_import_printing_tools())
        self._register_tool_batch(_import_system_tools())
        self._register_tool_batch(_import_pdlc_tools())

        self._register_mcp_handlers()

        logger.info(f"BriefCase MCP Server v{VERSION} initialized with {len(self._tool_definitions)} tools")

    def _register_tool_batch(self, tool_generator):
        for name, description, schema, handler in tool_generator:
            self._tool_definitions.append(types.Tool(
                name=name, description=description, inputSchema=schema
            ))
            self._tool_handlers[name] = handler

    def _register_mcp_handlers(self):
        tool_definitions = self._tool_definitions
        tool_handlers = self._tool_handlers

        @self.server.list_tools()
        async def list_tools() -> list[types.Tool]:
            return tool_definitions

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list:
            if name not in tool_handlers:
                raise ValueError(f"Unknown tool: {name}")
            handler = tool_handlers[name]
            result = await handler(**arguments)
            text = json.dumps(result, indent=2, default=str)
            return [types.TextContent(type="text", text=text)]

    async def run(self):
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream,
                self.server.create_initialization_options()
            )


async def main():
    logging.basicConfig(level=logging.INFO)
    server = BriefCaseServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
