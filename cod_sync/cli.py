"""Interactive CLI.

Usage:

  cod-sync                              walk the current directory
  cod-sync DIR [-r]                     walk a directory (optionally recursive)
  cod-sync FILE URL                     sync FILE against URL (creates FILE if absent)
  cod-sync FILE                         sync FILE against the URL stored in its comments
  cod-sync URL                          create a new deck in cwd, named after the remote

Flags:
  -y / --yes        accept all prompts non-interactively
  -n / --dry-run    show changes but write nothing
  -r / --recursive  recurse into subdirectories (only valid with a directory target)
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
        description=(
            "Sync Cockatrice .cod decklists against Moxfield/Archidekt URLs or text "
            "files. Pass a directory to walk it, a deck file to sync it, or a URL "
            "to create a new deck from."
        ),
    )
    parser.add_argument("target", nargs="?", default=None,
                        help="A directory, a deck file, or a URL")
    parser.add_argument("url", nargs="?", default=None,
                        help="Remote URL or path to a plain-text decklist")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Recurse into subdirectories (directory targets only)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Apply all changes without prompting")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Print changes and do not modify any file")
    args = parser.parse_args(argv)

    return _route(
        args.target,
        args.url,
        recursive=args.recursive,
        yes=args.yes,
        dry_run=args.dry_run,
    )


# ----- routing --------------------------------------------------------------


def _route(target: str | None, url: str | None, *,
           recursive: bool, yes: bool, dry_run: bool) -> int:
    """Classify TARGET and dispatch."""
    if target is None and url is None:
        return _walk_directory(".", recursive=recursive, yes=yes, dry_run=dry_run)

    # Bare URL given as the only arg (argparse binds it to `target`).
    if target is not None and _is_url(target):
        if url is not None:
            print(
                "error: two URLs given. Pass a file path or directory as the first argument.",
                file=sys.stderr,
            )
            return 2
        return _create_from_bare_url(target, yes=yes, dry_run=dry_run)

    # Defensive: argparse won't actually produce (None, URL); cover it anyway.
    if target is None and url is not None:
        return _create_from_bare_url(url, yes=yes, dry_run=dry_run)

    # Directory target.
    if os.path.isdir(target):
        if url is not None:
            print(
                f"error: can't sync a directory against a single URL. "
                f"Pass a deck file, or omit the URL to walk {target!r} interactively.",
                file=sys.stderr,
            )
            return 2
        return _walk_directory(target, recursive=recursive, yes=yes, dry_run=dry_run)

    # Otherwise: file path. Resolve `foo` → `foo.cod` if present, else treat as new.
    resolved = _resolve_deck_path(target)
    cod_path = resolved if resolved is not None else _ensure_cod_suffix(target)

    if resolved is None and url is None:
        print(
            f"error: {cod_path} doesn't exist and no URL was provided.",
            file=sys.stderr,
        )
        return 2

    return _sync_file(cod_path, url, yes=yes, dry_run=dry_run)


_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _is_url(s: str) -> bool:
    return bool(_URL_RE.match(s))


def _resolve_deck_path(name: str) -> str | None:
    if os.path.exists(name):
        return name
    with_suffix = name if name.endswith(".cod") else name + ".cod"
    if with_suffix != name and os.path.exists(with_suffix):
        return with_suffix
    return None


def _ensure_cod_suffix(name: str) -> str:
    return name if name.endswith(".cod") else name + ".cod"


# ----- single-file sync (unified sync + import) -----------------------------


def _sync_file(cod_path: str, url: str | None, *, yes: bool, dry_run: bool) -> int:
    exists = os.path.exists(cod_path)

    if exists:
        try:
            deck = cod.load(cod_path)
        except (OSError, ValueError) as e:
            print(f"error: failed to load {cod_path}: {e}", file=sys.stderr)
            return 2
    else:
        deck = cod.Deck()

    if url is None:
        url = sourcetag.get_source_url(deck.comments)
        if url is None:
            print(
                f"error: no source URL passed and none stored in {cod_path}. "
                f"Provide one: `cod-sync {cod_path} <URL>`.",
                file=sys.stderr,
            )
            return 2
        print(f"{_DIM}using stored URL: {url}{_RESET}")

    try:
        remote = sources.fetch(url)
    except Exception as e:
        print(f"error: failed to fetch {url}: {e}", file=sys.stderr)
        return 2

    if exists:
        changes = diff.compute(deck, remote.zones)
    else:
        changes = _import_preview_changes(remote.zones)

    if changes:
        _print_summary(changes)

    if dry_run:
        if not changes:
            print(f"{_DIM}No differences.{_RESET}")
        return 0

    if not exists:
        if not changes:
            print(f"{_DIM}Remote source is empty. Nothing to create.{_RESET}")
            return 0
        if not yes:
            try:
                ans = input(f"Create {cod_path} with {len(changes)} card(s)? [Y/n] ").strip().lower()
            except EOFError:
                ans = "n"
            if ans not in ("", "y", "yes"):
                print(f"{_DIM}Aborted.{_RESET}")
                return 0
        approved = changes
    else:
        approved = (changes if yes else _review(changes)) if changes else []

    final_deck = _apply(deck, approved) if approved else deck

    deckname_changed = False
    if not exists:
        new_deckname = remote.name or Path(cod_path).stem
        if new_deckname != final_deck.deckname:
            final_deck = replace(final_deck, deckname=new_deckname)
            deckname_changed = True
    elif remote.name and remote.name != final_deck.deckname:
        if _confirm(
            f"Local name:  {final_deck.deckname or '(none)'}\n"
            f"Remote name: {remote.name}\n"
            f"Update deckname?",
            default=False, auto_yes=yes,
        ):
            final_deck = replace(final_deck, deckname=remote.name)
            deckname_changed = True

    marker_changed = False
    if _is_url(url):
        stored = sourcetag.get_source_url(final_deck.comments)
        if stored is None or stored == url:
            update = True
        else:
            update = _confirm(
                f"Stored URL: {stored}\n"
                f"New URL:    {url}\n"
                f"Update stored URL?",
                default=False, auto_yes=yes,
            )
        if update:
            new_comments = sourcetag.set_source_url(final_deck.comments, url)
            if new_comments != final_deck.comments:
                final_deck = replace(final_deck, comments=new_comments)
                marker_changed = True

    if exists and not approved and not marker_changed and not deckname_changed:
        if not changes:
            print(f"{_DIM}No differences.{_RESET}")
        else:
            print(f"{_DIM}No changes applied.{_RESET}")
        return 0

    cod.save(final_deck, cod_path)

    if not exists:
        print(f"{_BOLD}Wrote new deck to {cod_path}{_RESET}")
    else:
        parts: list[str] = []
        if approved:
            parts.append(f"{len(approved)} change(s)")
        if marker_changed:
            parts.append("source URL")
        if deckname_changed:
            parts.append("deckname")
        print(f"{_BOLD}Wrote {' + '.join(parts)} to {cod_path}{_RESET}")
    return 0


# ----- bare URL → new deck in cwd -------------------------------------------


def _create_from_bare_url(url: str, *, yes: bool, dry_run: bool) -> int:
    try:
        remote = sources.fetch(url)
    except Exception as e:
        print(f"error: failed to fetch {url}: {e}", file=sys.stderr)
        return 2

    name = _sanitize_filename(remote.name) or "imported_deck"
    target = Path.cwd() / f"{name}.cod"
    if target.exists():
        print(
            f"error: target {target} already exists. "
            f"Move it or pass an explicit filename: `cod-sync <path> {url}`.",
            file=sys.stderr,
        )
        return 2

    return _sync_file(str(target), url, yes=yes, dry_run=dry_run)


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


# ----- directory walk -------------------------------------------------------


def _walk_directory(directory: str, *, recursive: bool, yes: bool, dry_run: bool) -> int:
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
            deck, str(path), remote.zones,
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


# ----- per-file flow used inside the walk -----------------------------------


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
    """Diff → review → apply for a single deck inside the walk.

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


# ----- UI helpers -----------------------------------------------------------


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


# ----- deck construction and change application ----------------------------


def _build_new_deck(deckname: str, remote: dict[str, dict[str, int]]) -> cod.Deck:
    zones: list[cod.Zone] = []
    for zone_name in ("main", "side"):
        entries = remote.get(zone_name, {})
        if not entries:
            continue
        cards = tuple(
            cod.Card(name=name, quantity=qty)
            for name, qty in sorted(entries.items(), key=lambda kv: kv[0].lower())
        )
        zones.append(cod.Zone(name=zone_name, cards=cards))
    return cod.Deck(deckname=deckname, zones=tuple(zones))


def _import_preview_changes(remote: dict[str, dict[str, int]]) -> list[diff.Change]:
    changes: list[diff.Change] = []
    for zone_name in ("main", "side"):
        entries = remote.get(zone_name, {})
        for name in sorted(entries, key=str.lower):
            changes.append(diff.Change("add", zone_name, name, 0, entries[name]))
    return changes


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
