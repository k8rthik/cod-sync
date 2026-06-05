"""Interactive CLI.

Two subcommands:

  cod-sync sync FILE SOURCE       diff one .cod against one URL/text file
  cod-sync dir  DIRECTORY         walk every .cod in a directory, prompting
                                  for a source per file
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import replace
from pathlib import Path

from cod_sync import cod, diff, sources, sourcetag


# ANSI colors
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cod-sync",
        description="Sync Cockatrice .cod decklists against Moxfield/Archidekt URLs or text files.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sync_p = sub.add_parser("sync", help="Sync a single .cod file")
    sync_p.add_argument("cod_file", help="Path to the local .cod file")
    sync_p.add_argument(
        "source",
        help="Remote URL (moxfield.com, archidekt.com) or path to a plain-text decklist",
    )
    _add_common_flags(sync_p)

    dir_p = sub.add_parser("dir", help="Walk a directory of .cod files interactively")
    dir_p.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory containing .cod files (default: current directory)",
    )
    dir_p.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Recurse into subdirectories",
    )
    _add_common_flags(dir_p)

    args = parser.parse_args(argv)

    if args.cmd == "sync":
        return run_sync(args.cod_file, args.source, yes=args.yes, dry_run=args.dry_run)
    if args.cmd == "dir":
        return run_dir(
            args.directory,
            recursive=args.recursive,
            yes=args.yes,
            dry_run=args.dry_run,
        )
    return 2


def _add_common_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Apply all changes without prompting",
    )
    p.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Print the diff and do not modify any file",
    )


# ----- sync mode ------------------------------------------------------------


def run_sync(cod_path: str, source: str, *, yes: bool, dry_run: bool) -> int:
    try:
        deck = cod.load(cod_path)
    except (OSError, ValueError) as e:
        print(f"error: failed to load {cod_path}: {e}", file=sys.stderr)
        return 2

    try:
        remote = sources.fetch(source)
    except Exception as e:
        print(f"error: failed to fetch {source}: {e}", file=sys.stderr)
        return 2

    _sync_one(
        deck,
        cod_path,
        remote,
        url_to_remember=source if _is_url(source) else None,
        yes=yes,
        dry_run=dry_run,
    )
    return 0


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _is_url(s: str) -> bool:
    return bool(_URL_RE.match(s))


def _sync_one(
    deck: cod.Deck,
    cod_path: str,
    remote: dict[str, dict[str, int]],
    *,
    url_to_remember: str | None,
    yes: bool,
    dry_run: bool,
    indent: str = "",
) -> str:
    """Diff → review → apply for a single deck.

    Returns one of: "no_change", "skipped", "updated".
    """
    changes = diff.compute(deck, remote)
    if changes:
        _print_summary(changes, indent=indent)

    if dry_run:
        if not changes:
            print(f"{indent}{_DIM}No differences.{_RESET}")
        return "no_change"

    approved = (changes if yes else _review(changes, indent=indent)) if changes else []
    final_deck = _apply(deck, approved) if approved else deck

    marker_changed = False
    if url_to_remember is not None:
        new_comments = sourcetag.set_source_url(final_deck.comments, url_to_remember)
        if new_comments != final_deck.comments:
            final_deck = replace(final_deck, comments=new_comments)
            marker_changed = True

    if not approved and not marker_changed:
        if not changes:
            print(f"{indent}{_DIM}No differences.{_RESET}")
            return "no_change"
        print(f"{indent}{_DIM}No changes applied.{_RESET}")
        return "skipped"

    cod.save(final_deck, cod_path)
    parts: list[str] = []
    if approved:
        parts.append(f"{len(approved)} change(s)")
    if marker_changed:
        parts.append("source URL")
    print(f"{indent}{_BOLD}Wrote {' + '.join(parts)} to {cod_path}{_RESET}")
    return "updated"


# ----- dir mode -------------------------------------------------------------


def run_dir(directory: str, *, recursive: bool, yes: bool, dry_run: bool) -> int:
    root = Path(directory)
    if not root.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    files = _find_cod_files(root, recursive=recursive)
    if not files:
        print(f"{_DIM}No .cod files found in {directory}{_RESET}")
        return 0

    print(f"{_BOLD}{len(files)} .cod file(s) in {directory}{_RESET}\n")

    stats = {"updated": 0, "no_change": 0, "skipped": 0, "errors": 0}

    for i, path in enumerate(files, start=1):
        header = f"[{i}/{len(files)}]"
        try:
            deck = cod.load(str(path))
        except (OSError, ValueError) as e:
            print(f"{_RED}{header} {path.name}: failed to load ({e}){_RESET}\n")
            stats["errors"] += 1
            continue

        rel = path.relative_to(root) if path.is_relative_to(root) else path
        print(f"{_CYAN}{_BOLD}{header} {rel}{_RESET}  {_DIM}— {deck.deckname or '(no name)'}{_RESET}")

        stored = sourcetag.get_source_url(deck.comments)
        if stored:
            print(f"  {_DIM}stored: {stored}{_RESET}")
            prompt = "  source URL/path (empty=use stored, s=skip, q=quit): "
        else:
            prompt = "  source URL/path (empty=skip, q=quit): "

        try:
            entered = input(prompt).strip()
        except EOFError:
            entered = "q"

        if entered.lower() == "q":
            print(f"  {_DIM}quitting walk{_RESET}\n")
            break
        if entered.lower() == "s":
            print(f"  {_DIM}skipped{_RESET}\n")
            stats["skipped"] += 1
            continue

        if not entered:
            if stored:
                source = stored
            else:
                print(f"  {_DIM}skipped{_RESET}\n")
                stats["skipped"] += 1
                continue
        else:
            source = entered

        try:
            remote = sources.fetch(source)
        except Exception as e:
            print(f"  {_RED}fetch failed: {e}{_RESET}\n")
            stats["errors"] += 1
            continue

        url_to_remember = source if _is_url(source) else None
        outcome = _sync_one(
            deck, str(path), remote,
            url_to_remember=url_to_remember,
            yes=yes, dry_run=dry_run, indent="  ",
        )
        print()
        stats[outcome] = stats.get(outcome, 0) + 1

    print(
        f"{_BOLD}Done.{_RESET} "
        f"updated={stats['updated']}  "
        f"no-change={stats['no_change']}  "
        f"skipped={stats['skipped']}  "
        f"errors={stats['errors']}"
    )
    return 0 if stats["errors"] == 0 else 1


def _find_cod_files(root: Path, *, recursive: bool) -> list[Path]:
    pattern = "**/*.cod" if recursive else "*.cod"
    return sorted(p for p in root.glob(pattern) if p.is_file())


# ----- shared helpers -------------------------------------------------------


def _color(change: diff.Change) -> str:
    return {"add": _GREEN, "remove": _RED, "qty": _YELLOW}[change.kind]


def _print_summary(changes: list[diff.Change], indent: str = "") -> None:
    by_zone: dict[str, list[diff.Change]] = {}
    for c in changes:
        by_zone.setdefault(c.zone, []).append(c)
    print(f"{indent}{_BOLD}{len(changes)} change(s):{_RESET}")
    for zone_name, items in by_zone.items():
        print(f"{indent}  {_DIM}[{zone_name}]{_RESET}")
        for c in items:
            print(f"{indent}    {_color(c)}{c.describe()}{_RESET}")
    print()


def _review(changes: list[diff.Change], indent: str = "") -> list[diff.Change]:
    """Walk through changes one by one. Returns the approved subset."""
    approved: list[diff.Change] = []
    apply_all = False
    for i, c in enumerate(changes, start=1):
        if apply_all:
            approved.append(c)
            continue
        prompt = (
            f"{indent}  [{i}/{len(changes)}] {_DIM}({c.zone}){_RESET} "
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
            print(f"{indent}    please answer y, n, a, s, or q")
    return approved


def _apply(deck: cod.Deck, changes: list[diff.Change]) -> cod.Deck:
    """Apply changes to the deck, preserving printing pins on untouched cards.

    Handles multi-printing entries (same card name listed multiple times
    with different setShortName/uuid):
      - remove: drop every entry with the name
      - qty increase: bump the single entry if there's one; otherwise append
        a new bare entry with the delta so existing printings stay intact
      - qty decrease: reduce from the END (last-added printings first),
        dropping entries that hit zero
    """
    new_zones: list[cod.Zone] = list(deck.zones)

    by_zone: dict[str, list[diff.Change]] = {}
    for c in changes:
        by_zone.setdefault(c.zone, []).append(c)

    for zone_name, zone_changes in by_zone.items():
        zone = _get_or_create_zone(new_zones, zone_name)
        next_cards = _apply_zone(list(zone.cards), zone_changes)
        new_zone = zone.with_cards(tuple(next_cards))
        idx = next(i for i, z in enumerate(new_zones) if z.name == zone_name)
        new_zones[idx] = new_zone

    return deck.with_zones(tuple(new_zones))


def _apply_zone(cards: list[cod.Card], zone_changes: list[diff.Change]) -> list[cod.Card]:
    removes = {c.name for c in zone_changes if c.kind == "remove"}
    qty_updates = {c.name: c.remote_qty for c in zone_changes if c.kind == "qty"}
    adds = [c for c in zone_changes if c.kind == "add"]

    indices_by_name: dict[str, list[int]] = {}
    for i, card in enumerate(cards):
        indices_by_name.setdefault(card.name, []).append(i)

    drop: set[int] = set()
    new_qty: dict[int, int] = {}
    extra_appends: list[cod.Card] = []

    for name in removes:
        drop.update(indices_by_name.get(name, []))

    for name, target in qty_updates.items():
        indices = indices_by_name.get(name, [])
        current_total = sum(cards[i].quantity for i in indices)
        if target == current_total:
            continue
        if target > current_total:
            delta = target - current_total
            if len(indices) == 1:
                new_qty[indices[0]] = cards[indices[0]].quantity + delta
            else:
                extra_appends.append(cod.Card(name=name, quantity=delta))
        else:
            shortfall = current_total - target
            for i in reversed(indices):
                if shortfall <= 0:
                    break
                cur = cards[i].quantity
                if cur <= shortfall:
                    drop.add(i)
                    shortfall -= cur
                else:
                    new_qty[i] = cur - shortfall
                    shortfall = 0

    next_cards: list[cod.Card] = []
    for i, card in enumerate(cards):
        if i in drop:
            continue
        if i in new_qty:
            next_cards.append(card.with_quantity(new_qty[i]))
        else:
            next_cards.append(card)

    for c in adds:
        next_cards.append(cod.Card(name=c.name, quantity=c.remote_qty))
    next_cards.extend(extra_appends)

    return next_cards


def _get_or_create_zone(zones: list[cod.Zone], name: str) -> cod.Zone:
    for z in zones:
        if z.name == name:
            return z
    new = cod.Zone(name=name)
    zones.append(new)
    return new


if __name__ == "__main__":
    sys.exit(main())
