"""External reference helpers.

Derives canonical URLs for short reference keys (e.g. Jira ticket keys) based
on integration settings, so the stored `ref_key` can stay short and human-
readable while we still render clickable URLs wherever Kit surfaces refs.
"""

from typing import Optional

from briefcase.mcp_server.config import load_settings


KNOWN_REF_TYPES = {
    'jira_epic',
    'jira_ticket',
    'jira',         # alias for ambiguous jira refs
    'confluence',
    'figma',
    'github_pr',
    'github_issue',
    'doc',
    'url',
}


def derive_ref_url(ref_type: str, ref_key: str,
                   explicit_url: Optional[str] = None) -> Optional[str]:
    """Return the best canonical URL for a ref.

    Precedence:
      1. explicit_url (as given by the caller)
      2. ref_key itself, if it's already a full URL
      3. Derived from ref_type + integration settings (Jira base URL, etc.)
      4. None if nothing can be derived.
    """
    if explicit_url:
        return explicit_url
    if not ref_key:
        return None
    if ref_key.startswith(('http://', 'https://')):
        return ref_key

    settings = load_settings()
    integrations = settings.get('integrations') or {}

    if ref_type in ('jira_epic', 'jira_ticket', 'jira'):
        base = ((integrations.get('jira') or {}).get('base_url') or '').rstrip('/')
        if base:
            return f"{base}/browse/{ref_key}"

    return None
