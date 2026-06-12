"""Interactive prompts.

Every call site is gated by an ``auto_yes`` boolean so non-interactive
runs (``--yes``, ``--quiet``) bypass ``input()`` entirely. ``_review``
also handles the multi-state per-change approval flow used during sync.
"""

from __future__ import annotations

from cod_sync import diff

from .formatting import _DIM, _RESET, _color


def _ask_walk_stored(*, auto_yes: bool) -> str:
    """Tri-state prompt used in the dir walk when a stored URL is present.

    Returns "accept", "skip", or "quit". Under --yes, returns "accept" without
    consuming any input.
    """
    if auto_yes:
        return "accept"
    while True:
        try:
            ans = input("  Sync against stored URL? [Y/n/q]: ").strip().lower()
        except EOFError:
            return "quit"
        if ans in ("", "y", "yes"):
            return "accept"
        if ans in ("n", "no"):
            return "skip"
        if ans in ("q", "quit"):
            return "quit"
        print("    please answer y, n, or q")


def _names_differ(a: str, b: str | None) -> bool:
    """True when two display names are meaningfully different.

    Casing and surrounding whitespace are treated as equivalent.
    """
    return (a or "").strip().casefold() != (b or "").strip().casefold()


def _confirm(prompt: str, *, default: bool, auto_yes: bool) -> bool:
    if auto_yes:
        return True
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        ans = input(prompt + suffix).strip().lower()
    except EOFError:
        return default
    if ans in ("y", "yes"):
        return True
    if ans in ("n", "no"):
        return False
    return default


def _review(changes: list[diff.Change], indent: str = "") -> tuple[list[diff.Change], list[str]]:
    """Walk through changes one by one.

    Returns `(approved, ignored)`: the approved subset, and the card names
    the user marked with `i` — those changes are not applied, and the
    caller persists the names so future syncs stop proposing them.
    Quitting (`q`) discards both.
    """
    approved: list[diff.Change] = []
    ignored: list[str] = []
    apply_all = False
    for i, c in enumerate(changes, start=1):
        if apply_all:
            approved.append(c)
            continue
        prompt = (
            f"{indent}  [{i}/{len(changes)}] {_DIM}({c.zone}){_RESET} "
            f"{_color(c)}{c.describe()}{_RESET}  "
            f"[y/n/a=all/i=ignore-card/s=skip-rest/q=quit] "
        )
        while True:
            try:
                ans = input(prompt).strip().lower()
            except EOFError:
                ans = "q"
            if ans in ("", "y", "yes"):
                approved.append(c)
                break
            if ans in ("n", "no"):
                break
            if ans in ("a", "all"):
                approved.append(c)
                apply_all = True
                break
            if ans in ("i", "ignore"):
                ignored.append(c.name)
                break
            if ans in ("s", "skip"):
                return approved, ignored
            if ans in ("q", "quit"):
                return [], []
            print(f"{indent}    please answer y, n, a, i, s, or q")
    return approved, ignored


def _review_mapping(original: str, proposed: str, indent: str = "") -> str:
    """Ask what to do with a newly-seen alt-name mapping.

    Returns the name to use: the proposed canonical (accept), the
    original printed name (keep), or whatever the user types (edit).
    EOF accepts the proposal — same default as pressing enter.
    """
    prompt = f'{indent}  map "{original}" → "{proposed}"?  [Y=accept/n=keep original/e=edit] '
    while True:
        try:
            ans = input(prompt).strip().lower()
        except EOFError:
            return proposed
        if ans in ("", "y", "yes"):
            return proposed
        if ans in ("n", "no"):
            return original
        if ans in ("e", "edit"):
            try:
                entered = input(f"{indent}    name to use: ").strip()
            except EOFError:
                entered = ""
            if entered:
                return entered
            print(f"{indent}    name can't be empty")
            continue
        print(f"{indent}    please answer y, n, or e")
