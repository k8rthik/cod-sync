"""Interactive CLI: diff a .cod against a remote source and apply approved changes."""
from __future__ import annotations

import argparse
import sys

from cod_sync import cod, diff, sources


# ANSI colors
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cod-sync",
        description="Sync a Cockatrice .cod decklist against a Moxfield/Archidekt URL or text file.",
    )
    parser.add_argument("cod_file", help="Path to the local .cod file to update")
    parser.add_argument(
        "source",
        help="Remote URL (moxfield.com, archidekt.com) or path to a plain-text decklist",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Apply all changes without prompting",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Print the diff and exit without modifying the file",
    )
    args = parser.parse_args(argv)

    try:
        deck = cod.load(args.cod_file)
    except (OSError, ValueError) as e:
        print(f"error: failed to load {args.cod_file}: {e}", file=sys.stderr)
        return 2

    try:
        remote = sources.fetch(args.source)
    except Exception as e:
        print(f"error: failed to fetch {args.source}: {e}", file=sys.stderr)
        return 2

    changes = diff.compute(deck, remote)
    if not changes:
        print(f"{_DIM}No differences.{_RESET}")
        return 0

    _print_summary(changes)

    if args.dry_run:
        return 0

    approved = changes if args.yes else _review(changes)
    if not approved:
        print(f"{_DIM}No changes applied.{_RESET}")
        return 0

    new_deck = _apply(deck, approved)
    cod.save(new_deck, args.cod_file)
    print(f"{_BOLD}Wrote {len(approved)} change(s) to {args.cod_file}{_RESET}")
    return 0


def _color(change: diff.Change) -> str:
    return {"add": _GREEN, "remove": _RED, "qty": _YELLOW}[change.kind]


def _print_summary(changes: list[diff.Change]) -> None:
    by_zone: dict[str, list[diff.Change]] = {}
    for c in changes:
        by_zone.setdefault(c.zone, []).append(c)
    print(f"{_BOLD}{len(changes)} change(s):{_RESET}")
    for zone_name, items in by_zone.items():
        print(f"  {_DIM}[{zone_name}]{_RESET}")
        for c in items:
            print(f"    {_color(c)}{c.describe()}{_RESET}")
    print()


def _review(changes: list[diff.Change]) -> list[diff.Change]:
    """Walk through changes one by one. Returns the approved subset."""
    approved: list[diff.Change] = []
    apply_all = False
    for i, c in enumerate(changes, start=1):
        if apply_all:
            approved.append(c)
            continue
        prompt = (
            f"  [{i}/{len(changes)}] {_DIM}({c.zone}){_RESET} "
            f"{_color(c)}{c.describe()}{_RESET}  "
            f"[y/n/a=all/s=skip-rest/q=quit] "
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
            if ans in ("s", "skip"):
                return approved
            if ans in ("q", "quit"):
                return []
            print("    please answer y, n, a, s, or q")
    return approved


def _apply(deck: cod.Deck, changes: list[diff.Change]) -> cod.Deck:
    """Apply changes to the deck, preserving printing pins on untouched/edited cards."""
    new_zones: list[cod.Zone] = list(deck.zones)

    by_zone: dict[str, list[diff.Change]] = {}
    for c in changes:
        by_zone.setdefault(c.zone, []).append(c)

    for zone_name, zone_changes in by_zone.items():
        zone = _get_or_create_zone(new_zones, zone_name)
        cards = list(zone.cards)

        removes = {c.name for c in zone_changes if c.kind == "remove"}
        qty_updates = {c.name: c.remote_qty for c in zone_changes if c.kind == "qty"}
        adds = [c for c in zone_changes if c.kind == "add"]

        # Remove and update in place to preserve printing pins.
        next_cards: list[cod.Card] = []
        for card in cards:
            if card.name in removes:
                continue
            if card.name in qty_updates:
                next_cards.append(card.with_quantity(qty_updates[card.name]))
            else:
                next_cards.append(card)

        # Appends — no printing pins; user picks the printing in Cockatrice.
        for c in adds:
            next_cards.append(cod.Card(name=c.name, quantity=c.remote_qty))

        new_zone = zone.with_cards(tuple(next_cards))
        idx = next(i for i, z in enumerate(new_zones) if z.name == zone_name)
        new_zones[idx] = new_zone

    return deck.with_zones(tuple(new_zones))


def _get_or_create_zone(zones: list[cod.Zone], name: str) -> cod.Zone:
    for z in zones:
        if z.name == name:
            return z
    new = cod.Zone(name=name)
    zones.append(new)
    return new


if __name__ == "__main__":
    sys.exit(main())
