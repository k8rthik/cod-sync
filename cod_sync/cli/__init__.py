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

from cod_sync import __version__
from cod_sync import sources as sources  # noqa: F401 — tests patch cod_sync.cli.sources.fetch

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
    _format_source_error,
    _print_summary,
    _sanitize_filename,
    _show_info,
)

# Re-exports — interactive prompts live in cli.prompts. _confirm and
# _review are called from _sync_deck (still in this module); tests
# patch `cod_sync.cli._confirm`, so the bare name must resolve here.
from .prompts import _ask_walk_stored as _ask_walk_stored  # noqa: F401
from .prompts import _confirm as _confirm  # noqa: F401
from .prompts import _names_differ as _names_differ  # noqa: F401
from .prompts import _review as _review  # noqa: F401

# Re-exports — path/url helpers live in cli.routing. _route uses the
# bare names; nothing else patches these but symmetry keeps the
# pattern consistent.
from .routing import (  # noqa: F401
    _ensure_cod_suffix,
    _is_url,
    _resolve_deck_path,
)

# Re-exports — per-deck sync core lives in cli.sync. _route reads
# _sync_file and _create_from_bare_url through __init__.py's namespace
# so dispatch-test monkeypatches reach them. The sync module imports
# `cod_sync.cli` back to resolve _confirm at call time, which is why
# this import comes AFTER the .prompts re-export above (so _confirm is
# already bound on the partially-loaded cli module when sync.py runs).
from .sync import (  # noqa: F401
    SyncOutcome,
    SyncStatus,
    _create_from_bare_url,
    _sync_deck,
    _sync_file,
)

# Re-exports — directory walk lives in cli.walk. _route reads
# _walk_directory through __init__.py's namespace so dispatch-test
# monkeypatches reach it.
from .walk import _find_cod_files as _find_cod_files  # noqa: F401
from .walk import _walk_directory as _walk_directory  # noqa: F401


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cod-sync",
        description=(
            "Sync Cockatrice .cod decklists against Moxfield/Archidekt URLs or text "
            "files. Pass a directory to walk it, a deck file to sync it, or a URL "
            "to create a new deck from."
        ),
    )
    parser.add_argument(
        "target", nargs="?", default=None, help="A directory, a deck file, or a URL"
    )
    parser.add_argument(
        "url", nargs="?", default=None, help="Remote URL or path to a plain-text decklist"
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Recurse into subdirectories (directory targets only)",
    )
    parser.add_argument(
        "--yes", "-y", action="store_true", help="Apply all changes without prompting"
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Print changes and do not modify any file"
    )
    parser.add_argument(
        "--info",
        "-i",
        action="store_true",
        help="Print the deck's contents and metrics instead of syncing",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress informational output; implies --yes"
    )
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
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


def _route(
    target: str | None, url: str | None, *, recursive: bool, yes: bool, dry_run: bool, info: bool
) -> int:
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
        print("error: --info needs a deck file. Usage: cod-sync FILE --info", file=sys.stderr)
        return 2
    if url is not None:
        print("error: --info doesn't take a URL.", file=sys.stderr)
        return 2
    if _is_url(target):
        print("error: --info needs a local deck file, not a URL.", file=sys.stderr)
        return 2
    if os.path.isdir(target):
        print(f"error: --info needs a deck file, not a directory ({target}).", file=sys.stderr)
        return 2

    resolved = _resolve_deck_path(target)
    if resolved is None:
        print(f"error: deck file not found: {target}", file=sys.stderr)
        return 2
    return _show_info(resolved)


if __name__ == "__main__":
    sys.exit(main())
