"""Interactive CLI.

Usage:

  cod-sync                              walk the current directory
  cod-sync DIR [-r]                     walk a directory (optionally recursive)
  cod-sync FILE URL                     sync FILE against URL (creates FILE if absent)
  cod-sync FILE                         sync FILE against the URL stored in its comments
  cod-sync URL                          sync the default-named .cod in cwd against URL,
                                          creating it if absent (name comes from the remote)
  cod-sync FILE --info                  print deck contents and structural metrics

Flags:
  -y / --yes        accept all prompts non-interactively
  -n / --dry-run    show changes but write nothing
  -r / --recursive  recurse into subdirectories (only valid with a directory target)
  -i / --info       show the deck's contents and metrics instead of syncing
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

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
    parser.add_argument("--info", "-i", action="store_true",
                        help="Print the deck's contents and metrics instead of syncing")
    args = parser.parse_args(argv)

    return _route(
        args.target,
        args.url,
        recursive=args.recursive,
        yes=args.yes,
        dry_run=args.dry_run,
        info=args.info,
    )


# ----- routing --------------------------------------------------------------


def _route(target: str | None, url: str | None, *,
           recursive: bool, yes: bool, dry_run: bool, info: bool) -> int:
    """Classify TARGET and dispatch."""
    if info:
        return _route_info(target, url)

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

    assert target is not None  # narrowed by the four returning branches above

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


def _route_info(target: str | None, url: str | None) -> int:
    """Dispatch for --info. Requires a file target, refuses URL/dir."""
    if target is None:
        print("error: --info needs a deck file. Usage: cod-sync FILE --info",
              file=sys.stderr)
        return 2
    if url is not None:
        print("error: --info doesn't take a URL.", file=sys.stderr)
        return 2
    if _is_url(target):
        print("error: --info needs a local deck file, not a URL.", file=sys.stderr)
        return 2
    if os.path.isdir(target):
        print(f"error: --info needs a deck file, not a directory ({target}).",
              file=sys.stderr)
        return 2

    resolved = _resolve_deck_path(target)
    if resolved is None:
        print(f"error: deck file not found: {target}", file=sys.stderr)
        return 2
    return _show_info(resolved)


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


# ----- per-deck sync core ---------------------------------------------------


SyncStatus = Literal["no_change", "updated", "created", "skipped", "dry_run"]


@dataclass(frozen=True)
class SyncOutcome:
    status: SyncStatus
    approved_count: int
    marker_changed: bool
    deckname_changed: bool


def _sync_deck(
    deck: cod.Deck,
    cod_path: str,
    remote_zones: dict[str, dict[str, int]],
    remote_name: str | None,
    *,
    is_new_file: bool,
    url_to_remember: str | None,
    prompt_deckname_on_mismatch: bool,
    prompt_on_url_conflict: bool,
    yes: bool,
    dry_run: bool,
    indent: str = "",
) -> SyncOutcome:
    """Run diff → approve → apply → save for one deck.

    The single-file and walk callers differ only in (1) which prompts fire
    when local and remote disagree, (2) whether the file is being created
    fresh, and (3) output indentation. Everything else is shared.
    """
    if is_new_file:
        changes = _import_preview_changes(remote_zones)
    else:
        changes = diff.compute(deck, remote_zones)

    if changes:
        _print_summary(changes, indent=indent)

    if dry_run:
        if not changes:
            print(f"{indent}{_DIM}No differences.{_RESET}")
        return SyncOutcome("dry_run", 0, False, False)

    if is_new_file:
        if not changes:
            print(f"{indent}{_DIM}Remote source is empty. Nothing to create.{_RESET}")
            return SyncOutcome("no_change", 0, False, False)
        if not yes:
            try:
                ans = input(
                    f"{indent}Create {cod_path} with {len(changes)} card(s)? [Y/n] "
                ).strip().lower()
            except EOFError:
                ans = "n"
            if ans not in ("", "y", "yes"):
                print(f"{indent}{_DIM}Aborted.{_RESET}")
                return SyncOutcome("skipped", 0, False, False)
        approved = changes
    else:
        approved = (changes if yes else _review(changes, indent=indent)) if changes else []

    final_deck = _apply(deck, approved) if approved else deck

    deckname_changed = False
    if is_new_file:
        new_deckname = remote_name or Path(cod_path).stem
        if new_deckname != final_deck.deckname:
            final_deck = replace(final_deck, deckname=new_deckname)
            deckname_changed = True
    elif (
        prompt_deckname_on_mismatch
        and remote_name
        and _names_differ(remote_name, final_deck.deckname)
    ):
        if _confirm(
            f"Local name:  {final_deck.deckname or '(none)'}\n"
            f"Remote name: {remote_name}\n"
            f"Update deckname?",
            default=False, auto_yes=yes,
        ):
            final_deck = replace(final_deck, deckname=remote_name)
            deckname_changed = True

    marker_changed = False
    if url_to_remember is not None:
        stored = sourcetag.get_source_url(final_deck.comments)
        if stored is None or stored == url_to_remember:
            update = True
        elif prompt_on_url_conflict:
            update = _confirm(
                f"Stored URL: {stored}\n"
                f"New URL:    {url_to_remember}\n"
                f"Update stored URL?",
                default=False, auto_yes=yes,
            )
        else:
            update = True
        if update:
            new_comments = sourcetag.set_source_url(final_deck.comments, url_to_remember)
            if new_comments != final_deck.comments:
                final_deck = replace(final_deck, comments=new_comments)
                marker_changed = True

    if not is_new_file and not approved and not marker_changed and not deckname_changed:
        if not changes:
            print(f"{indent}{_DIM}No differences.{_RESET}")
            return SyncOutcome("no_change", 0, False, False)
        print(f"{indent}{_DIM}No changes applied.{_RESET}")
        return SyncOutcome("skipped", 0, False, False)

    cod.save(final_deck, cod_path)

    if is_new_file:
        print(f"{indent}{_BOLD}Wrote new deck to {cod_path}{_RESET}")
        return SyncOutcome("created", len(approved), marker_changed, deckname_changed)

    parts: list[str] = []
    if approved:
        parts.append(f"{len(approved)} change(s)")
    if marker_changed:
        parts.append("source URL")
    if deckname_changed:
        parts.append("deckname")
    print(f"{indent}{_BOLD}Wrote {' + '.join(parts)} to {cod_path}{_RESET}")
    return SyncOutcome("updated", len(approved), marker_changed, deckname_changed)


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

    _sync_deck(
        deck, cod_path, remote.zones, remote.name,
        is_new_file=not exists,
        url_to_remember=url if _is_url(url) else None,
        prompt_deckname_on_mismatch=True,
        prompt_on_url_conflict=True,
        yes=yes, dry_run=dry_run,
    )
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
        print(f"{_DIM}syncing existing {target}{_RESET}")

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


# ----- info -----------------------------------------------------------------


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
        max_qty_width = len(str(max(totals.values())))
        for name in sorted(totals, key=str.lower):
            print(f"    {totals[name]:>{max_qty_width}} {name}")
        print()

    if grand_total == 0:
        print(f"  {_DIM}(empty deck){_RESET}")
        print()
    print(f"  {_BOLD}total:{_RESET} {grand_total} cards")
    return 0


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
        source: str | None
        if stored:
            print(f"  {_DIM}stored: {stored}{_RESET}")
            decision = _ask_walk_stored(auto_yes=yes)
            if decision == "quit":
                print(f"  {_DIM}quitting walk{_RESET}\n")
                break
            if decision == "skip":
                print(f"  {_DIM}skipped{_RESET}\n")
                stats["skipped"] += 1
                continue
            source = stored
        else:
            try:
                entered = input("  source URL/path (empty=skip, q=quit): ").strip()
            except EOFError:
                entered = "q"
            if entered.lower() == "q":
                print(f"  {_DIM}quitting walk{_RESET}\n")
                break
            if not entered or entered.lower() == "s":
                print(f"  {_DIM}skipped{_RESET}\n")
                stats["skipped"] += 1
                continue
            source = entered

        try:
            remote = sources.fetch(source)
        except Exception as e:
            print(f"  {_RED}fetch failed: {e}{_RESET}\n")
            stats["errors"] += 1
            continue

        outcome = _sync_deck(
            deck, str(path), remote.zones, remote.name,
            is_new_file=False,
            url_to_remember=source if _is_url(source) else None,
            prompt_deckname_on_mismatch=False,
            prompt_on_url_conflict=False,
            yes=yes, dry_run=dry_run, indent="  ",
        )
        print()
        stat_key = "no_change" if outcome.status == "dry_run" else outcome.status
        stats[stat_key] = stats.get(stat_key, 0) + 1

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


# ----- UI helpers -----------------------------------------------------------


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
