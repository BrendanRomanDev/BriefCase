"""Configuration loader for BriefCase."""

from pathlib import Path
from typing import Optional
import yaml


DEFAULTS = {
    "database_path": str(Path.home() / ".briefcase" / "briefcase.db"),
    # No vault default — set during /onboard. Tools requiring it must
    # check for None and surface a "run /onboard" message.
    "obsidian_vault": None,
    "user_profile": str(Path.home() / ".briefcase" / "user_profile.yaml"),
    "backup_dir": str(Path.home() / ".briefcase" / "backups"),
    # PDLC is an optional, opinionated integration. If the path doesn't
    # exist on disk the PDLC tools degrade gracefully.
    "pdlc_repo": str(Path.home() / "Programming" / "pdlc"),
    "features": {"printing": False, "repo_integration": True},
}


VAULT_NOT_CONFIGURED_MSG = (
    "Obsidian vault is not configured. Run `/onboard` to set up your vault, "
    "or add `obsidian_vault: /path/to/vault` to settings.yaml."
)


def require_vault(settings: Optional[dict] = None) -> str:
    """Return the configured vault path or raise with a clear /onboard prompt."""
    if settings is None:
        settings = load_settings()
    vault = settings.get("obsidian_vault")
    if not vault:
        raise RuntimeError(VAULT_NOT_CONFIGURED_MSG)
    return vault


def load_settings(settings_path: Optional[str] = None) -> dict:
    """Load settings from settings.yaml with defaults."""
    if settings_path is None:
        settings_path = str(Path(__file__).parent.parent.parent / "settings.yaml")

    settings = dict(DEFAULTS)

    path = Path(settings_path)
    if path.exists():
        with open(path) as f:
            user_settings = yaml.safe_load(f) or {}
        settings.update(user_settings)

    return settings


def resolve_tangent_config(settings: Optional[dict] = None) -> dict:
    """Resolve the runtime tangent dispatch config.

    Reads `tangent.enabled` (auto | true | false) from settings.yaml. When
    `auto`, performs the same wezterm + SKILL.md detection the sidecar
    uses. Returns a dict with the boolean `available`, the source `reason`
    if unavailable, and the resolved skill names for work vs research.
    """
    if settings is None:
        settings = load_settings()
    cfg = settings.get("tangent") or {}
    skill_work = cfg.get("skill_work") or "tangent"
    skill_research = cfg.get("skill_research") or "tangent-teach"
    attach_limit = int(cfg.get("attach_dropdown_limit") or 10)

    enabled_setting = cfg.get("enabled", "auto")
    if enabled_setting is False or enabled_setting == "false":
        return {
            "available": False,
            "reason": "tangent.enabled is false in settings.yaml",
            "skill_work": skill_work,
            "skill_research": skill_research,
            "attach_dropdown_limit": attach_limit,
        }

    # Both `true` and `auto` perform detection; `true` ignores the result
    # for the boolean but the reason is still surfaced as informational.
    from briefcase.sidecar.server import detect_tangent_available
    detected, reason = detect_tangent_available()
    available = True if enabled_setting is True or enabled_setting == "true" else detected
    return {
        "available": available,
        "reason": reason if not detected else None,
        "skill_work": skill_work,
        "skill_research": skill_research,
        "attach_dropdown_limit": attach_limit,
    }


def load_user_profile(profile_path: Optional[str] = None) -> dict:
    """Load user profile from YAML."""
    if profile_path is None:
        profile_path = DEFAULTS["user_profile"]

    path = Path(profile_path)
    if not path.exists():
        return {"name": "User", "role": "Unknown", "projects": []}

    with open(path) as f:
        return yaml.safe_load(f) or {}
