"""Teams links: finding a Meeting's join link, and opening it in Teams for Linux."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

# Join links: the long "/l/meetup-join/..." form and the short "/meet/..." form,
# on the classic and the new Teams domain.
_TEAMS_LINK = re.compile(
    r"https://teams\.(?:microsoft\.com|cloud\.microsoft)/(?:l/meetup-join|meet)/[^\s<>\"'\]\)]+",
    re.IGNORECASE,
)


def find_teams_url(*texts: str) -> str | None:
    """The first Teams join link in these texts, in order."""
    for text in texts:
        match = _TEAMS_LINK.search(text or "")
        if match:
            return match.group(0)
    return None


def msteams_uri(url: str) -> str:
    """The msteams: link Teams for Linux handles (it registers the msteams: scheme)."""
    parts = urlsplit(url)
    return "msteams:" + parts.path + (f"?{parts.query}" if parts.query else "")
