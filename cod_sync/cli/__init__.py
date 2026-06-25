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
import sys

from cod_sync import __version__

from . import _state
from .routing import _route


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

    try:
        return _route(
            args.target,
            args.url,
            recursive=args.recursive,
            yes=args.yes or args.quiet,
            dry_run=args.dry_run,
            info=args.info,
        )
    except KeyboardInterrupt:
        # Ctrl-C at any interactive prompt (or mid-fetch) should exit
        # cleanly, not dump a traceback. Finish the partial prompt line,
        # then return the conventional 128 + SIGINT(2) status.
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
