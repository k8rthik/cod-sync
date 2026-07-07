#!/usr/bin/env python3
"""Regenerate ``man/cod-sync.1`` from the CLI's argparse parser.

The man page is a generated artifact — the argparse parser in
``cod_sync.cli`` is the single source of truth for flags, help text, and
usage. Never hand-edit ``man/cod-sync.1``; change the parser and re-run
this script. ``tests/test_manpage.py`` fails if the committed file drifts
from what this generator produces, so a forgotten regen is caught in CI.

Usage:
    python scripts/gen_manpage.py

Requires the ``argparse-manpage`` dev dependency (``pip install -e '.[dev]'``).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT = _ROOT / "man" / "cod-sync.1"

# argparse-manpage stamps today's date into the .TH header, which would make
# every regeneration produce a spurious diff. Blank the date field so the
# committed file only changes when the flags or help text actually change.
# The version is deliberately omitted from the man page (it's a moving target;
# `cod-sync --version` reports it) so a bump never forces a regen.
_TH_DATE_RE = re.compile(r'(^\.TH\s+\S+\s+"[^"]*")\s+"[^"]*"', re.MULTILINE)


def render() -> str:
    """Return the roff man page as argparse-manpage would emit it, with the
    volatile .TH date blanked out."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from argparse_manpage.cli import main; main()",
            "--module",
            "cod_sync.cli",
            "--function",
            "_build_parser",
            "--prog",
            "cod-sync",
            "--project-name",
            "cod-sync",
            "--description",
            "Sync a Cockatrice .cod decklist against Moxfield/Archidekt/ManaBox/text",
            "--author",
            "cod-sync contributors",
            "--url",
            "https://github.com/keerthik/cod-sync",
            "--manual-title",
            "cod-sync manual",
        ],
        capture_output=True,
        text=True,
        check=True,
        cwd=_ROOT,
    )
    return _TH_DATE_RE.sub(r'\1 ""', result.stdout)


def main() -> int:
    _OUTPUT.parent.mkdir(exist_ok=True)
    _OUTPUT.write_text(render(), encoding="utf-8")
    print(f"wrote {_OUTPUT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
