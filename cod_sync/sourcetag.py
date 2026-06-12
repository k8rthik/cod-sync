"""Manage cod-sync's marker lines in a deck's <comments> field.

Single-line markers let us find and update our own state without
touching the user's notes; everything outside marker lines is preserved
verbatim. Two markers exist:

    cod-sync-source: <url>     the deck's remote source (one line, replaced)
    cod-sync-ignore: <name>    a card future syncs must not touch
                               (one line per card, appended)

Markers live in the comments deliberately: they are visible and
hand-editable in Cockatrice's comments box, so deleting an ignore line
there is the un-ignore path.
"""

from __future__ import annotations

_MARKER = "cod-sync-source:"
_IGNORE_MARKER = "cod-sync-ignore:"


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


def get_ignored_names(comments: str) -> frozenset[str]:
    """Return the card names marked as ignored in the comments."""
    names: set[str] = set()
    for line in comments.splitlines():
        stripped = line.strip()
        if stripped.startswith(_IGNORE_MARKER):
            name = stripped[len(_IGNORE_MARKER) :].strip()
            if name:
                names.add(name)
    return frozenset(names)


def add_ignored_name(comments: str, name: str) -> str:
    """Return a new comments string with `name` marked as ignored.

    Appends one marker line per card; a name that is already ignored
    returns the comments unchanged.
    """
    if name in get_ignored_names(comments):
        return comments
    lines = comments.splitlines()
    lines.append(f"{_IGNORE_MARKER} {name}")
    return "\n".join(lines)
