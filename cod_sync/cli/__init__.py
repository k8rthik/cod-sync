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
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from cod_sync import __version__, alt_name, cod, diff, errors, sources, sourcetag

from . import _state

# Re-exports — the deck-mutation logic lives in cli.apply but tests and
# internal callers reach for these names through the `cli` namespace.
from .apply import (  # noqa: F401
    _apply,
    _apply_zone,
    _build_new_deck,
    _get_or_create_zone,
    _import_preview_changes,
)

# Re-exports — formatting and info live in cli.formatting; existing
# f-string call sites in this module reference the bare names, and
# tests patch `cod_sync.cli._show_info` / unit-test
# `cod_sync.cli._sanitize_filename`, so we bind them locally here.
from .formatting import (  # noqa: F401
    _BOLD,
    _CYAN,
    _DIM,
    _GREEN,
    _RED,
    _RESET,
    _YELLOW,
    _color,
    _print_summary,
    _sanitize_filename,
    _show_info,
)

# Re-exports — interactive prompts live in cli.prompts. _confirm and
# _review are called from _sync_deck (still in this module); tests
# patch `cod_sync.cli._confirm`, so the bare name must resolve here.
from .prompts import (  # noqa: F401
    _ask_walk_stored,
    _confirm,
    _names_differ,
    _review,
)

# Re-exports — path/url helpers live in cli.routing. _route uses the
# bare names; nothing else patches these but symmetry keeps the
# pattern consistent.
from .routing import (  # noqa: F401
    _ensure_cod_suffix,
    _is_url,
    _resolve_deck_path,
)


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
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress informational output; implies --yes")
    parser.add_argument("--version", "-V", action="version",
                        version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    _state._QUIET = args.quiet

    return _route(
        args.target,
        args.url,
        recursive=args.recursive,
        yes=args.yes or args.quiet,
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


# ----- per-deck sync core ---------------------------------------------------


SyncStatus = Literal["no_change", "updated", "created", "skipped", "dry_run"]


@dataclass(frozen=True)
class SyncOutcome:
    status: SyncStatus
    approved_count: int
    marker_changed: bool
    deckname_changed: bool
    banner_changed: bool = False
    tags_changed: bool = False


def _sync_deck(
    deck: cod.Deck,
    cod_path: str,
    remote_zones: dict[str, dict[str, int]],
    remote_name: str | None,
    remote_tags: tuple[str, ...],
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
            _state.say(f"{indent}{_DIM}No differences.{_RESET}")
        return SyncOutcome("dry_run", 0, False, False)

    if is_new_file:
        if not changes:
            _state.say(f"{indent}{_DIM}Remote source is empty. Nothing to create.{_RESET}")
            return SyncOutcome("no_change", 0, False, False)
        if not yes:
            try:
                ans = input(
                    f"{indent}Create {cod_path} with {len(changes)} card(s)? [Y/n] "
                ).strip().lower()
            except EOFError:
                ans = "n"
            if ans not in ("", "y", "yes"):
                _state.say(f"{indent}{_DIM}Aborted.{_RESET}")
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

    # Banner lives on the local deck (user-set in Cockatrice). Only rewrite
    # it when it's genuinely orphaned — i.e. the canonical name is already
    # in the post-apply card list AND the original (reskin) name is NOT.
    # In that state the banner used to reference a card in the deck and
    # got stranded when the card list was canonicalized; restoring the
    # link preserves the user's intent. Any other state (reskin still in
    # the deck, custom override, unknown name) leaves the banner alone.
    banner_changed = False
    if final_deck.banner_card_name:
        original = final_deck.banner_card_name
        canonical = alt_name.canonicalize(original)
        if canonical != original:
            card_names = {c.name for z in final_deck.zones for c in z.cards}
            if canonical in card_names and original not in card_names:
                final_deck = replace(final_deck, banner_card_name=canonical)
                banner_changed = True

    # Union deck-level tags from the remote into the local set. Never destructive:
    # local-only tags survive, and dedupe is case-insensitive but preserves the
    # casing of whichever side introduced each tag.
    tags_changed = False
    if remote_tags:
        local_tags = cod.tags_xml_to_list(final_deck.tags_xml)
        seen = {t.casefold() for t in local_tags}
        merged: list[str] = list(local_tags)
        for t in remote_tags:
            key = t.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(t)
        if tuple(merged) != local_tags:
            final_deck = replace(final_deck, tags_xml=cod.tags_list_to_xml(tuple(merged)))
            tags_changed = True

    if (
        not is_new_file
        and not approved
        and not marker_changed
        and not deckname_changed
        and not banner_changed
        and not tags_changed
    ):
        if not changes:
            _state.say(f"{indent}{_DIM}No differences.{_RESET}")
            return SyncOutcome("no_change", 0, False, False)
        _state.say(f"{indent}{_DIM}No changes applied.{_RESET}")
        return SyncOutcome("skipped", 0, False, False)

    cod.save(final_deck, cod_path)

    if is_new_file:
        _state.say(f"{indent}{_BOLD}Wrote new deck to {cod_path}{_RESET}")
        return SyncOutcome(
            "created", len(approved), marker_changed, deckname_changed, banner_changed,
            tags_changed,
        )

    parts: list[str] = []
    if approved:
        parts.append(f"{len(approved)} change(s)")
    if marker_changed:
        parts.append("source URL")
    if deckname_changed:
        parts.append("deckname")
    if banner_changed:
        parts.append("banner")
    if tags_changed:
        parts.append("tags")
    _state.say(f"{indent}{_BOLD}Wrote {' + '.join(parts)} to {cod_path}{_RESET}")
    return SyncOutcome(
        "updated", len(approved), marker_changed, deckname_changed, banner_changed,
        tags_changed,
    )


# ----- source-error formatting ----------------------------------------------


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
        return (
            f"error: deck at {e.source} is private or requires login (HTTP 401/403)."
        )
    if isinstance(e, errors.RateLimitedError):
        hint = f" retry-after: {e.retry_after}s." if e.retry_after else ""
        return (
            f"error: rate limited by source at {e.source} (HTTP 429). "
            f"try again in a minute.{hint}"
        )
    if isinstance(e, errors.RemoteServerError):
        return (
            f"error: source server error at {e.source} (HTTP {e.status}). "
            f"the site may be having issues; try again later."
        )
    if isinstance(e, errors.NetworkError):
        return (
            f"error: network error reaching {e.source}: {e.cause}. "
            f"check your connection."
        )
    if isinstance(e, errors.MalformedResponseError):
        return (
            f"error: unexpected response from {e.source}: {e.reason}. "
            f"the source API may have changed; please file a bug."
        )
    if isinstance(e, errors.InvalidSourceError):
        return f"error: invalid source {e.source}: {e.reason}."
    return f"error: failed to fetch {e.source}: {e}"


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
        _state.say(f"{_DIM}using stored URL: {url}{_RESET}")

    try:
        remote = sources.fetch(url)
    except errors.SourceError as e:
        print(_format_source_error(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to fetch {url}: {e}", file=sys.stderr)
        return 2

    _sync_deck(
        deck, cod_path, remote.zones, remote.name, remote.tags,
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
    except errors.SourceError as e:
        print(_format_source_error(e), file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: failed to fetch {url}: {e}", file=sys.stderr)
        return 2

    name = _sanitize_filename(remote.name) or "imported_deck"
    target = Path.cwd() / f"{name}.cod"
    if target.exists():
        _state.say(f"{_DIM}syncing existing {target}{_RESET}")

    return _sync_file(str(target), url, yes=yes, dry_run=dry_run)


# ----- directory walk -------------------------------------------------------


def _walk_directory(directory: str, *, recursive: bool, yes: bool, dry_run: bool) -> int:
    root = Path(directory)
    if not root.is_dir():
        print(f"error: not a directory: {directory}", file=sys.stderr)
        return 2

    files = _find_cod_files(root, recursive=recursive)
    if not files:
        _state.say(f"{_DIM}No .cod files found in {directory}{_RESET}")
        return 0

    _state.say(f"{_BOLD}{len(files)} .cod file(s) in {directory}{_RESET}\n")

    stats = {"updated": 0, "no_change": 0, "skipped": 0, "errors": 0}

    for i, path in enumerate(files, start=1):
        header = f"[{i}/{len(files)}]"
        try:
            deck = cod.load(str(path))
        except (OSError, ValueError) as e:
            print(f"{header} {path.name}: failed to load ({e})", file=sys.stderr)
            stats["errors"] += 1
            continue

        rel = path.relative_to(root) if path.is_relative_to(root) else path
        _state.say(f"{_CYAN}{_BOLD}{header} {rel}{_RESET}  {_DIM}— {deck.deckname or '(no name)'}{_RESET}")

        stored = sourcetag.get_source_url(deck.comments)
        source: str | None
        if stored:
            _state.say(f"  {_DIM}stored: {stored}{_RESET}")
            decision = _ask_walk_stored(auto_yes=yes)
            if decision == "quit":
                _state.say(f"  {_DIM}quitting walk{_RESET}\n")
                break
            if decision == "skip":
                _state.say(f"  {_DIM}skipped{_RESET}\n")
                stats["skipped"] += 1
                continue
            source = stored
        else:
            try:
                entered = input("  source URL/path (empty=skip, q=quit): ").strip()
            except EOFError:
                entered = "q"
            if entered.lower() == "q":
                _state.say(f"  {_DIM}quitting walk{_RESET}\n")
                break
            if not entered or entered.lower() == "s":
                _state.say(f"  {_DIM}skipped{_RESET}\n")
                stats["skipped"] += 1
                continue
            source = entered

        try:
            remote = sources.fetch(source)
        except errors.SourceError as e:
            print(f"  {_format_source_error(e)}", file=sys.stderr)
            stats["errors"] += 1
            continue
        except Exception as e:
            print(f"  fetch failed: {e}", file=sys.stderr)
            stats["errors"] += 1
            continue

        outcome = _sync_deck(
            deck, str(path), remote.zones, remote.name, remote.tags,
            is_new_file=False,
            url_to_remember=source if _is_url(source) else None,
            prompt_deckname_on_mismatch=False,
            prompt_on_url_conflict=False,
            yes=yes, dry_run=dry_run, indent="  ",
        )
        _state.say()
        stat_key = "no_change" if outcome.status == "dry_run" else outcome.status
        stats[stat_key] = stats.get(stat_key, 0) + 1

    _state.say(
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


if __name__ == "__main__":
    sys.exit(main())
