"""Configuration loader for BriefCase."""

from pathlib import Path
from typing import Optional
import yaml


DEFAULTS = {
    "database_path": str(Path.home() / ".briefcase" / "briefcase.db"),
    "obsidian_vault": str(Path.home() / "Notes" / "ThriveNotes"),
    "user_profile": str(Path.home() / ".briefcase" / "user_profile.yaml"),
    "backup_dir": str(Path.home() / ".briefcase" / "backups"),
    "features": {"printing": False, "repo_integration": True},
}


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


def load_user_profile(profile_path: Optional[str] = None) -> dict:
    """Load user profile from YAML."""
    if profile_path is None:
        profile_path = DEFAULTS["user_profile"]

    path = Path(profile_path)
    if not path.exists():
        return {"name": "User", "role": "Unknown", "projects": []}

    with open(path) as f:
        return yaml.safe_load(f) or {}
