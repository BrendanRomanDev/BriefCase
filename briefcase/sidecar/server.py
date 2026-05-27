"""FastAPI sidecar server — local HTTP bridge for the Chrome extension.

Receives capture POSTs from the extension and writes them to the same
SQLite database (~/.briefcase/briefcase.db) the MCP server uses. Runs
independently of Claude Code so the extension always has a target.

Run directly for local testing:
    python -m briefcase.sidecar.server

Normal operation is via launchd (see briefcase/sidecar/README.md).
"""

import logging
import os
import secrets
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from briefcase.mcp_server.config import load_settings
from briefcase.mcp_server.database import (
    init_database,
    get_db_connection,
    create_triage_item,
    get_pending_triage_count,
    get_triage_items,
)

VOICE_PROFILE_PATH = Path.home() / ".claude" / "rules" / "brendan-voice-profile.md"
LAST_DRAFT_PATH = Path.home() / ".briefcase" / "last_draft.txt"
CLAUDE_CLI_FALLBACKS = [
    Path.home() / ".local" / "bin" / "claude",
    Path("/opt/homebrew/bin/claude"),
    Path("/usr/local/bin/claude"),
]
CLAUDE_TIMEOUT_SECONDS = 60

VERSION = "0.3.0"

logger = logging.getLogger("briefcase.sidecar")

TOKEN_PATH = Path.home() / ".briefcase" / "sidecar_token"


# --- Config resolution ---

def _resolve_port() -> int:
    """Port precedence: env var > settings.yaml > 8989 default."""
    env = os.environ.get("BRIEFCASE_SIDECAR_PORT")
    if env:
        try:
            return int(env)
        except ValueError:
            logger.warning("Invalid BRIEFCASE_SIDECAR_PORT=%s, ignoring", env)
    settings = load_settings()
    sidecar_cfg = settings.get("sidecar") or {}
    return int(sidecar_cfg.get("port") or 8989)


def _resolve_host() -> str:
    """Bind to 127.0.0.1 only. Do not expose to the network."""
    return "127.0.0.1"


def _read_token() -> Optional[str]:
    """Read the shared auth token from disk. Returns None if not set."""
    if not TOKEN_PATH.exists():
        return None
    token = TOKEN_PATH.read_text().strip()
    return token or None


def ensure_token() -> str:
    """Generate a new auth token if one doesn't exist. Returns the token."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_token()
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    TOKEN_PATH.write_text(token + "\n")
    TOKEN_PATH.chmod(0o600)
    logger.info("Generated new sidecar auth token at %s", TOKEN_PATH)
    return token


# --- Request/response models ---

class ClipIn(BaseModel):
    """A single capture from the browser extension."""
    source: str = Field(..., min_length=1, max_length=64,
                        description="Origin type, e.g. 'google_chat', 'web_clip'")
    content: str = Field(..., min_length=1, max_length=50_000,
                         description="The captured text/message")
    source_url: Optional[str] = Field(None, max_length=2_000,
                                      description="Permalink back to the origin")
    title: Optional[str] = Field(None, max_length=500,
                                 description="Page title, channel name, etc.")
    metadata: Optional[dict] = Field(None,
                                     description="Free-form extra fields (sender, timestamp, thread preview, etc.)")
    flags: Optional[dict] = Field(None,
                                  description="Capture-time signals about what work this needs (e.g. {'needs_jira': true, 'needs_code_review': false, 'search_around': true, 'needs_web_research': true, 'epic_hint': 'THRIV-13413', 'auto_file': true}). Kit reads these during triage.")
    attach_to_id: Optional[int] = Field(None,
                                        description="Optional ID of an existing pending triage_queue item to attach this capture to. Children are surfaced as composite context under their parent at triage time and resolve together. The attachment is collapsed to one-deep if the target itself has a parent.")


class ClipOut(BaseModel):
    status: str
    triage_item_id: int


class HealthOut(BaseModel):
    status: str
    version: str
    pending_count: int


class TriagePendingItem(BaseModel):
    id: int
    title: Optional[str]
    content_preview: str
    source: str
    source_url: Optional[str]
    captured_at: str


class TangentAvailabilityOut(BaseModel):
    available: bool
    reason: Optional[str]


class DraftIn(BaseModel):
    """A draft request from the extension."""
    content: str = Field(..., min_length=1, max_length=20_000,
                         description="The original message Brendan is replying to (or topic of the new message).")
    context: Optional[str] = Field(None, max_length=10_000,
                                   description="Brendan's notes/intent for the reply: tone, points to hit, deadlines, etc.")
    tone: str = Field("informal", pattern="^(informal|formal)$",
                      description="Voice mode. 'informal' for Chat/Slack/email, 'formal' for RFCs/docs.")
    mode: str = Field("reply", pattern="^(reply|new|cleanup)$",
                      description="What we're doing: replying to the content, drafting a new message about the topic, or cleaning up Brendan's word-vomit.")
    destination: str = Field("google-chat", pattern="^(markdown|google-chat|slack|plaintext)$",
                             description="Where the drafted text will be pasted. Controls formatting rules: 'google-chat'/'slack'/'plaintext' emit NO markdown chars (no *bold*, no [text](url) links — bare URLs only). 'markdown' is full Github-flavored markdown. Defaults to 'google-chat' because that's the dominant extension use case and the most common formatting-noise pain point.")


class DraftOut(BaseModel):
    status: str
    draft: str
    elapsed_ms: int


# --- claude CLI resolution ---

def _resolve_claude_cli() -> Optional[Path]:
    """Find the claude CLI. Tries PATH first, then known install locations."""
    via_path = shutil.which("claude")
    if via_path:
        return Path(via_path)
    for candidate in CLAUDE_CLI_FALLBACKS:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


_DESTINATION_RULES = {
    "markdown": (
        "DESTINATION: markdown. Full Github-flavored markdown is fair game — "
        "**bold**, _italic_, [text](url) links, bullet lists, headings, code fences."
    ),
    "google-chat": (
        "DESTINATION: google-chat. Google Chat does NOT render markdown. "
        "Output MUST follow these rules:\n"
        "- NO *bold*, **bold**, _italic_, __italic__, ~strike~, ~~strike~~. Express emphasis "
        "through word choice and structure (short sentences, paragraph breaks), not formatting chars.\n"
        "- NO [text](url) markdown link syntax. Emit bare URLs only — Chat auto-linkifies them.\n"
        "- NO markdown headings (#, ##). Use a 'Label:' line if structure is needed.\n"
        "- NO code fences (```). For code/commands, drop a paragraph break and write the code on its own line.\n"
        "- Bullets are OK as plain '-' or '•' at line start (Chat renders them as text, fine).\n"
        "- Paragraph breaks (blank line between paragraphs) are preserved by Chat — use them.\n"
        "If a markdown character ends up in the output, Brendan has to clean it up by hand. Do not make him."
    ),
    "slack": (
        "DESTINATION: slack. Treat like google-chat: NO *bold*, NO _italic_, NO [text](url) syntax. "
        "Emit bare URLs. Plain '-' bullets and paragraph breaks are fine. "
        "(Slack has its own mrkdwn dialect, but Brendan's usage doesn't lean on it — keep formatting "
        "characters out unless he asked for them.)"
    ),
    "plaintext": (
        "DESTINATION: plaintext. NO formatting characters at all — no *bold*, no _italic_, "
        "no [text](url), no bullets, no headings. Just paragraphs and bare URLs."
    ),
}


def _build_draft_prompt(body: "DraftIn") -> str:
    """Construct the prompt sent to `claude -p`. Inlines the voice profile
    and applies destination-specific formatting rules so the output renders
    cleanly where it will be pasted."""
    voice_profile = ""
    if VOICE_PROFILE_PATH.exists():
        voice_profile = VOICE_PROFILE_PATH.read_text()

    if body.mode == "reply":
        task = "Brendan needs to reply to the following message. Draft his reply."
        target_label = "Message Brendan is replying to"
    elif body.mode == "cleanup":
        task = "Brendan wrote the following rough draft. Clean it up in his voice without changing his meaning or points."
        target_label = "Brendan's rough draft"
    else:
        task = "Brendan wants to send a message. The topic and intent follow."
        target_label = "Topic / intent"

    parts = []
    if voice_profile:
        parts.append(
            "You are drafting a message in Brendan Roman's authentic voice. "
            "Internalize this voice profile completely before writing:"
        )
        parts.append("---")
        parts.append(voice_profile)
        parts.append("---")
    parts.append(f"Tone: {body.tone}")
    parts.append("")
    parts.append(_DESTINATION_RULES.get(body.destination, _DESTINATION_RULES["markdown"]))
    parts.append("")
    parts.append(task)
    parts.append("")
    parts.append(f"## {target_label}")
    parts.append(body.content.strip())
    if body.context:
        parts.append("")
        parts.append("## Brendan's notes / context for the draft")
        parts.append(body.context.strip())
    parts.append("")
    parts.append(
        "Output ONLY the draft body — no preamble, no 'Here's the draft:', "
        "no markdown wrappers (no leading ```), no signature, no closing remarks. "
        "Just the exact text Brendan would paste at the destination. "
        "Preserve paragraph breaks where they help readability. "
        "Re-read the DESTINATION rules above one more time before finalizing — "
        "no markdown characters slip through when the destination forbids them."
    )
    return "\n".join(parts)


# --- App ---

def create_app() -> FastAPI:
    app = FastAPI(
        title="BriefCase Sidecar",
        version=VERSION,
        description="Local HTTP bridge. Writes extension captures to the triage queue.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    init_database()
    ensure_token()

    def _require_auth(token_header: Optional[str]) -> None:
        expected = _read_token()
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Sidecar auth token is missing. Run install.sh to generate one."
            )
        if not token_header or not secrets.compare_digest(token_header, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-BriefCase-Token header."
            )

    @app.get("/health", response_model=HealthOut)
    def health() -> HealthOut:
        """Unauthenticated heartbeat. Useful for the extension to detect the sidecar."""
        conn = get_db_connection()
        try:
            count = get_pending_triage_count(conn)
        finally:
            conn.close()
        return HealthOut(status="ok", version=VERSION, pending_count=count)

    @app.post("/draft", response_model=DraftOut)
    def draft(
        body: DraftIn,
        x_briefcase_token: Optional[str] = Header(default=None, alias="X-BriefCase-Token"),
    ) -> DraftOut:
        """Draft a message in Brendan's voice via `claude -p`. Uses the user's
        existing Claude Code subscription auth (no separate API key)."""
        _require_auth(x_briefcase_token)

        claude_bin = _resolve_claude_cli()
        if claude_bin is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="`claude` CLI not found on PATH or in known fallback locations. "
                       "Install Claude Code or update _resolve_claude_cli."
            )

        prompt = _build_draft_prompt(body)
        logger.info("Drafting via %s (prompt: %d chars, mode=%s tone=%s)",
                    claude_bin, len(prompt), body.mode, body.tone)

        import time
        t0 = time.monotonic()
        try:
            result = subprocess.run(
                [str(claude_bin), "-p", prompt],
                capture_output=True,
                text=True,
                timeout=CLAUDE_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail=f"`claude -p` timed out after {CLAUDE_TIMEOUT_SECONDS}s."
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not exec {claude_bin} - file vanished?"
            )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()[:500]
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"claude -p exited {result.returncode}: {stderr or 'no stderr'}"
            )

        draft_text = (result.stdout or "").strip()
        if not draft_text:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="claude -p produced empty output."
            )

        # Persist as the latest draft so `recopy` can restore it from any terminal.
        try:
            LAST_DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
            LAST_DRAFT_PATH.write_text(draft_text)
        except OSError as e:
            logger.warning("Could not persist draft to %s: %s", LAST_DRAFT_PATH, e)

        logger.info("Drafted %d chars in %dms", len(draft_text), elapsed_ms)
        return DraftOut(status="success", draft=draft_text, elapsed_ms=elapsed_ms)

    @app.post("/clip", response_model=ClipOut, status_code=status.HTTP_201_CREATED)
    def clip(
        body: ClipIn,
        x_briefcase_token: Optional[str] = Header(default=None, alias="X-BriefCase-Token"),
    ) -> ClipOut:
        """Accept a capture from the extension and enqueue it for triage."""
        _require_auth(x_briefcase_token)
        conn = get_db_connection()
        try:
            item_id = create_triage_item(
                conn,
                source=body.source,
                content=body.content,
                source_url=body.source_url,
                title=body.title,
                metadata=body.metadata,
                flags=body.flags,
                parent_id=body.attach_to_id,
            )
        finally:
            conn.close()
        flag_summary = (
            ",".join(k for k, v in body.flags.items() if v)
            if isinstance(body.flags, dict) else ""
        )
        attach_note = f" attached_to=#{body.attach_to_id}" if body.attach_to_id else ""
        logger.info(
            "Enqueued triage item #%s from source=%s flags=[%s]%s",
            item_id, body.source, flag_summary, attach_note
        )
        return ClipOut(status="success", triage_item_id=item_id)

    @app.get("/triage-pending", response_model=list[TriagePendingItem])
    def triage_pending(
        limit: int = 10,
        x_briefcase_token: Optional[str] = Header(default=None, alias="X-BriefCase-Token"),
    ) -> list[TriagePendingItem]:
        """Recent pending triage items, newest first. Used by the compose
        form to populate the 'attach to existing capture' dropdown.

        Only top-level items (no parent) are returned — children can't be
        attached to (the form collapses to one-deep anyway).
        """
        _require_auth(x_briefcase_token)
        limit = max(1, min(limit, 50))
        conn = get_db_connection()
        try:
            items = get_triage_items(conn, status='pending', limit=limit)
        finally:
            conn.close()
        items.sort(key=lambda r: r.get('captured_at') or '', reverse=True)
        out: list[TriagePendingItem] = []
        for item in items:
            content = item.get('content') or ''
            preview = content.strip().replace('\n', ' ')
            if len(preview) > 80:
                preview = preview[:77] + '...'
            out.append(TriagePendingItem(
                id=item['id'],
                title=item.get('title'),
                content_preview=preview,
                source=item['source'],
                source_url=item.get('source_url'),
                captured_at=item.get('captured_at') or '',
            ))
        return out

    @app.get("/tangent-available", response_model=TangentAvailabilityOut)
    def tangent_available() -> TangentAvailabilityOut:
        """Whether Kit can dispatch auto-run items to a tangent skill.

        Detection: `wezterm` must be on PATH AND at least one tangent
        SKILL.md must exist under ~/.dotfiles or ~/.claude. Unauthenticated
        because it's a host-level capability check, not user data."""
        avail, reason = detect_tangent_available()
        return TangentAvailabilityOut(available=avail, reason=reason)

    return app


def detect_tangent_available() -> tuple[bool, Optional[str]]:
    """Return (available, reason). reason is None on success, a short
    explanation on failure. Used by the sidecar endpoint and the MCP
    server at startup."""
    if shutil.which("wezterm") is None:
        return False, "wezterm not found on PATH"
    candidate_skills = [
        Path.home() / ".dotfiles" / "claude" / "skills" / "tangent" / "SKILL.md",
        Path.home() / ".claude" / "skills" / "tangent" / "SKILL.md",
    ]
    if not any(p.exists() for p in candidate_skills):
        return False, "tangent SKILL.md not found in ~/.dotfiles or ~/.claude"
    return True, None


app = create_app()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = _resolve_host()
    port = _resolve_port()
    logger.info("Starting BriefCase sidecar on http://%s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
