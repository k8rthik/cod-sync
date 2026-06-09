"""Embed/extract a remote-source URL in a deck's <comments> field.

We use a single-line marker so we can find and update it without touching
the user's own notes. Format:

    cod-sync-source: <url>

If a marker line already exists it is replaced; otherwise a new line is
appended. The rest of the comments string is preserved verbatim.
"""

from __future__ import annotations

_MARKER = "cod-sync-source:"


def get_source_url(comments: str) -> str | None:
    """Return the URL stored in the marker line, or None if absent."""
    for line in comments.splitlines():
        stripped = line.strip()
        if stripped.startswith(_MARKER):
            url = stripped[len(_MARKER) :].strip()
            return url or None
    return None


def set_source_url(comments: str, url: str) -> str:
    """Return a new comments string with the URL embedded as a marker line.

    Replaces any existing marker line (the first one wins; later duplicates
    are dropped). User-written lines are kept in their original order.
    """
    out: list[str] = []
    replaced = False
    for line in comments.splitlines():
        if line.strip().startswith(_MARKER):
            if not replaced:
                out.append(f"{_MARKER} {url}")
                replaced = True
            # duplicates are dropped
        else:
            out.append(line)
    if not replaced:
        out.append(f"{_MARKER} {url}")
    return "\n".join(out)
