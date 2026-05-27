"""MCP Tool: get_runtime_capabilities - Expose host-level toggles to Kit."""

import logging
from briefcase.mcp_server.config import resolve_tangent_config

logger = logging.getLogger(__name__)


async def get_runtime_capabilities() -> dict:
    """Return runtime capability flags Kit uses to decide its behavior.

    Specifically tells Kit whether it can dispatch auto-run triage items
    to a tangent skill (requires WezTerm + tangent SKILL.md). When not
    available, Kit falls back to resolving auto-run items inline.
    """
    try:
        tangent_cfg = resolve_tangent_config()
        return {
            "status": "success",
            "tangent": {
                "available": tangent_cfg["available"],
                "reason": tangent_cfg["reason"],
                "skill_work": tangent_cfg["skill_work"],
                "skill_research": tangent_cfg["skill_research"],
            },
        }
    except Exception as e:
        logger.error(f"get_runtime_capabilities error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


TOOL_NAME = "get_runtime_capabilities"
TOOL_DESCRIPTION = (
    "Report host-level capability flags that change Kit's triage behavior. "
    "Call this once at the start of any session that will walk the triage "
    "queue. The `tangent.available` flag tells you whether to dispatch "
    "auto-run items by invoking the tangent skill (Skill tool) or fall "
    "back to inline resolution. When available, use skill_work for items "
    "whose flags include any action (jira/reply/meeting/pr-review), and "
    "skill_research when only research flags are set (code/search/web)."
)
TOOL_SCHEMA = {
    "type": "object",
    "properties": {}
}

__all__ = ['get_runtime_capabilities', 'TOOL_NAME', 'TOOL_DESCRIPTION', 'TOOL_SCHEMA']
