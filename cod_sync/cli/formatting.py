"""ANSI constants, change-summary rendering, and the --info display.

Also home to the filename-sanitizer used by the bare-URL create flow:
it's a pure string-shaping helper with no better-fitting module.
"""

from __future__ import annotations

import sys

from cod_sync import cod, diff, errors, sourcetag

from . import _state

# ANSI colors
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _color(change: diff.Change) -> str:
    return {"add": _GREEN, "remove": _RED, "qty": _YELLOW}[change.kind]


def _print_summary(changes: list[diff.Change], indent: str = "") -> None:
    if _state._QUIET:
        return
    by_zone: dict[str, list[diff.Change]] = {}
    for c in changes:
        by_zone.setdefault(c.zone, []).append(c)
    print(f"{indent}{_BOLD}{len(changes)} change(s):{_RESET}")
    for zone_name, items in by_zone.items():
        print(f"{indent}  {_DIM}[{zone_name}]{_RESET}")
        for c in items:
            print(f"{indent}    {_color(c)}{c.describe()}{_RESET}")
    print()


def _format_source_error(e: errors.SourceError) -> str:
    """Render a source-fetch error with a per-type template.

    Each branch maps to a distinct user remedy, so the message tells the
    user what to do instead of just "something went wrong."
    """
    if isinstance(e, errors.DeckNotFoundError):
        return (
            f"error: deck not found at {e.source} (HTTP 404). "
            f"the deck may have been deleted, or the URL may be wrong."
        )
    if isinstance(e, errors.DeckPrivateError):
        return f"error: deck at {e.source} is private or requires login (HTTP 401/403)."
    if isinstance(e, errors.RateLimitedError):
        hint = f" retry-after: {e.retry_after}s." if e.retry_after else ""
        return (
            f"error: rate limited by source at {e.source} (HTTP 429). try again in a minute.{hint}"
        )
    if isinstance(e, errors.RemoteServerError):
        return (
            f"error: source server error at {e.source} (HTTP {e.status}). "
            f"the site may be having issues; try again later."
        )
    if isinstance(e, errors.NetworkError):
        return f"error: network error reaching {e.source}: {e.cause}. check your connection."
    if isinstance(e, errors.MalformedResponseError):
        return (
            f"error: unexpected response from {e.source}: {e.reason}. "
            f"the source API may have changed; please file a bug."
        )
    if isinstance(e, errors.InvalidSourceError):
        return f"error: invalid source {e.source}: {e.reason}."
    return f"error: failed to fetch {e.source}: {e}"


def _sanitize_filename(title: str) -> str:
    """Lowercase, whitespace → underscore, keep [a-z0-9_-], drop the rest."""
    out: list[str] = []
    for ch in title.lower():
        if ch.isspace():
            out.append("_")
        elif "a" <= ch <= "z" or "0" <= ch <= "9" or ch in "_-":
            out.append(ch)
    s = "".join(out)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_-")


def _show_info(cod_path: str) -> int:
    try:
        deck = cod.load(cod_path)
    except (OSError, ValueError) as e:
        print(f"error: failed to load {cod_path}: {e}", file=sys.stderr)
        return 2

    stored_url = sourcetag.get_source_url(deck.comments)

    title = deck.deckname or "(unnamed deck)"
    print(f"{_BOLD}{title}{_RESET}  {_DIM}{cod_path}{_RESET}")
    print(_DIM + "─" * max(40, len(title) + len(cod_path) + 2) + _RESET)
    print(f"  {_DIM}format:{_RESET} {deck.format or '(unset)'}")
    print(f"  {_DIM}source:{_RESET} {stored_url or '(none stored)'}")
    if deck.banner_card_name:
        print(f"  {_DIM}banner:{_RESET} {deck.banner_card_name}")
    print()

    grand_total = 0
    for zone_name in ("main", "side"):
        zone = deck.zone(zone_name)
        if zone is None or not zone.cards:
            continue
        totals: dict[str, int] = {}
        pinned = 0
        for card in zone.cards:
            totals[card.name] = totals.get(card.name, 0) + card.quantity
            if card.set_short_name or card.collector_number or card.uuid:
                pinned += card.quantity
        zone_total = sum(totals.values())
        grand_total += zone_total
        print(
            f"  {_CYAN}{_BOLD}[{zone_name}]{_RESET} "
            f"{zone_total} cards · {len(totals)} unique · {pinned} pinned"
        )
        max_qty_width = len(str(max(totals.values(), default=1)))
        for name in sorted(totals, key=str.lower):
            print(f"    {totals[name]:>{max_qty_width}} {name}")
        print()

    if grand_total == 0:
        print(f"  {_DIM}(empty deck){_RESET}")
        print()
    print(f"  {_BOLD}total:{_RESET} {grand_total} cards")
    return 0
