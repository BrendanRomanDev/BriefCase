"""BriefCase MCP Server - Kit's backend for work planning."""

import json
import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

VERSION = "0.2.0"

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """Kit: Your Work Planning Companion

CONVERSATION START CHECKLIST:
1. gcal_list_events (next 14 days) - Google Calendar events
2. get_forecast(days=14) - Initiative deadlines + inbox status + current time
3. get_recent_activity(days=3) - Recent dailies and session context
4. Read ~/.briefcase/user_profile.yaml - Role, team, projects

TOOL QUICK GUIDE:
- brain_dump: Capture tasks, optionally link to initiative
- get_capture_list: Query inbox, filter by initiative/status
- complete_task / delete_task: Task lifecycle
- manage_initiative: CRUD for projects/initiatives
- manage_initiative_members: Add/remove/list team members
- plan_daily: Save daily task plan (calendar events handled by agent separately)
- query_daily: Look up a day's task plan
- get_forecast: DB-side forecast (deadlines, inbox, current time) - agent merges with gcal
- get_recent_activity: Recent dailies and session notes
- file_meeting_notes: Paste notes → filed in Obsidian → summary + proposed actions
- search_notes: Search Obsidian vault by keyword, scoped to initiative/date
- get_initiative_status: Full status with DB + Obsidian notes + optional gh CLI
- save_conversation_notes: Save session context at end of conversation
- backup_database: Create timestamped backup

CRITICAL RULES:
- Events live in Google Calendar, NOT the database.
- The agent calls gcal_list_events separately and merges with DB data.
- plan_daily stores TASKS only. Events are referenced, not duplicated.
- get_forecast returns current time so the agent can determine past vs upcoming.
- Never auto-create tasks from meeting notes. Always conversational triage.
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


def _import_initiative_tools():
    """Import initiative management tools."""
    from briefcase.mcp_server.tools.manage_initiative import (
        manage_initiative, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, manage_initiative

    from briefcase.mcp_server.tools.manage_initiative_members import (
        manage_initiative_members, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, manage_initiative_members


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


def _import_system_tools():
    """Import system tools."""
    from briefcase.mcp_server.tools.save_conversation_notes import (
        save_conversation_notes, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, save_conversation_notes

    from briefcase.mcp_server.tools.backup_database import (
        backup_database, TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA)
    yield TOOL_NAME, TOOL_DESCRIPTION, TOOL_SCHEMA, backup_database


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
        self._register_tool_batch(_import_initiative_tools())
        self._register_tool_batch(_import_daily_tools())
        self._register_tool_batch(_import_meeting_tools())
        self._register_tool_batch(_import_system_tools())

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
