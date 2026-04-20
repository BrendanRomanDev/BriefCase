"""BriefCase Sidecar — local HTTP bridge for the Chrome extension.

This package runs a small FastAPI server on localhost so a browser
extension can POST captures into the triage_queue table. The MCP
server and the sidecar share the same SQLite database at
~/.briefcase/briefcase.db.
"""
