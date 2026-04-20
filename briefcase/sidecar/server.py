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
)

VERSION = "0.1.0"

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


class ClipOut(BaseModel):
    status: str
    triage_item_id: int


class HealthOut(BaseModel):
    status: str
    version: str
    pending_count: int


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
            )
        finally:
            conn.close()
        logger.info("Enqueued triage item #%s from source=%s", item_id, body.source)
        return ClipOut(status="success", triage_item_id=item_id)

    return app


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
