"""Interactive CLI.

Two subcommands:

  cod-sync sync FILE SOURCE       diff one .cod against one URL/text file
  cod-sync dir  DIRECTORY         walk every .cod in a directory, prompting
                                  for a source per file
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from cod_sync import cod, diff, sources


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

    return _sync_one(deck, cod_path, remote, yes=yes, dry_run=dry_run)


def _sync_one(
    deck: cod.Deck,
    cod_path: str,
    remote: dict[str, dict[str, int]],
    *,
    yes: bool,
    dry_run: bool,
) -> int:
    """Diff → review → apply for a single deck. Returns 0 on success."""
    changes = diff.compute(deck, remote)
    if not changes:
        print(f"{_DIM}No differences.{_RESET}")
        return 0

    _print_summary(changes)

    if dry_run:
        return 0

    approved = changes if yes else _review(changes)
    if not approved:
        print(f"{_DIM}No changes applied.{_RESET}")
        return 0

    new_deck = _apply(deck, approved)
    cod.save(new_deck, cod_path)
    print(f"{_BOLD}Wrote {len(approved)} change(s) to {cod_path}{_RESET}")
    return 0


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

        try:
            source = input(f"  source URL/path (empty=skip, q=quit): ").strip()
        except EOFError:
            source = "q"

        if not source or source.lower() == "s":
            print(f"  {_DIM}skipped{_RESET}\n")
            stats["skipped"] += 1
            continue
        if source.lower() == "q":
            print(f"  {_DIM}quitting walk{_RESET}\n")
            break

        try:
            remote = sources.fetch(source)
        except Exception as e:
            print(f"  {_RED}fetch failed: {e}{_RESET}\n")
            stats["errors"] += 1
            continue

        changes = diff.compute(deck, remote)
        if not changes:
            print(f"  {_DIM}no differences{_RESET}\n")
            stats["no_change"] += 1
            continue

        _print_summary(changes, indent="  ")

        if dry_run:
            stats["no_change"] += 1  # diff shown but nothing written
            print()
            continue

        approved = changes if yes else _review(changes, indent="  ")
        if not approved:
            print(f"  {_DIM}no changes applied{_RESET}\n")
            stats["skipped"] += 1
            continue

        new_deck = _apply(deck, approved)
        cod.save(new_deck, str(path))
        print(f"  {_BOLD}wrote {len(approved)} change(s){_RESET}\n")
        stats["updated"] += 1

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

        next_cards: list[cod.Card] = []
        for card in cards:
            if card.name in removes:
                continue
            if card.name in qty_updates:
                next_cards.append(card.with_quantity(qty_updates[card.name]))
            else:
                next_cards.append(card)

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
