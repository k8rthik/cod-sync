"""Directory-walk orchestration.

For each ``.cod`` file in a directory tree, prompts whether to sync
against its stored source URL (or asks for a fresh one), then delegates
the per-deck work to ``_sync_deck``. Per-deck behavior is identical to
single-file sync — including deckname-mismatch and URL-conflict
prompts, which can fire mid-loop. Pass ``-y`` to accept-all.
"""

from __future__ import annotations

import sys
from pathlib import Path

from cod_sync import cod, errors, sources, sourcetag

from . import _state, routing
from .formatting import _BOLD, _CYAN, _DIM, _RESET, _format_source_error
from .prompts import _ask_walk_stored
from .sync import _apply_mapping_control, _sync_deck


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
        _state.say(
            f"{_CYAN}{_BOLD}{header} {rel}{_RESET}  {_DIM}— {deck.deckname or '(no name)'}{_RESET}"
        )

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
            if not entered:
                _state.say(f"  {_DIM}skipped{_RESET}\n")
                stats["skipped"] += 1
                continue
            source = entered

        _state.say(f"  {_DIM}fetching {source} ...{_RESET}")
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

        remote = _apply_mapping_control(remote, yes=yes, dry_run=dry_run, indent="  ")

        outcome = _sync_deck(
            deck,
            str(path),
            remote.zones,
            remote.name,
            remote.tags,
            is_new_file=False,
            url_to_remember=source if routing._is_url(source) else None,
            yes=yes,
            dry_run=dry_run,
            indent="  ",
        )
        _state.say()
        # Walk forces is_new_file=False, so _sync_deck never returns "created";
        # the footer below only renders these four buckets. Fail loudly rather
        # than silently swallow a status a future refactor might introduce.
        stat_key = "no_change" if outcome.status == "dry_run" else outcome.status
        if stat_key not in stats:
            raise RuntimeError(
                f"walk produced unaccounted sync status {outcome.status!r} for {path}; "
                "the summary footer cannot report it"
            )
        stats[stat_key] += 1

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
