"""Target classification and dispatch.

``_route`` / ``_route_info`` classify the CLI target (directory, deck
file, or URL) and dispatch to the matching flow. Flow functions are
invoked through sibling module objects (``sync._sync_file``,
``walk._walk_directory``, ``formatting._show_info``) so monkeypatches
on the defining modules are seen at call time. ``sync`` and ``walk``
import this module back for ``_is_url``; the cycle is harmless because
every cross-module reference resolves at call time, never at import
time.
"""

from __future__ import annotations

import os
import re
import sys

from . import formatting, sync, walk

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


def _route(
    target: str | None,
    url: str | None,
    *,
    recursive: bool,
    yes: bool,
    dry_run: bool,
    info: bool,
    include_maybeboard: bool = False,
) -> int:
    """Classify TARGET and dispatch."""
    if info:
        return _route_info(target, url)

    if target is None and url is None:
        return walk._walk_directory(
            ".",
            recursive=recursive,
            yes=yes,
            dry_run=dry_run,
            include_maybeboard=include_maybeboard,
        )

    # Bare URL given as the only arg (argparse binds it to `target`).
    if target is not None and _is_url(target):
        if url is not None:
            print(
                "error: two URLs given. Pass a file path or directory as the first argument.",
                file=sys.stderr,
            )
            return 2
        return sync._create_from_bare_url(
            target, yes=yes, dry_run=dry_run, include_maybeboard=include_maybeboard
        )

    # Defensive: argparse won't actually produce (None, URL); cover it anyway.
    if target is None and url is not None:
        return sync._create_from_bare_url(
            url, yes=yes, dry_run=dry_run, include_maybeboard=include_maybeboard
        )

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
        return walk._walk_directory(
            target,
            recursive=recursive,
            yes=yes,
            dry_run=dry_run,
            include_maybeboard=include_maybeboard,
        )

    # Otherwise: file path. Resolve `foo` → `foo.cod` if present, else treat as new.
    resolved = _resolve_deck_path(target)
    cod_path = resolved if resolved is not None else _ensure_cod_suffix(target)

    if resolved is None and url is None:
        print(
            f"error: {cod_path} doesn't exist and no URL was provided.",
            file=sys.stderr,
        )
        return 2

    return sync._sync_file(
        cod_path, url, yes=yes, dry_run=dry_run, include_maybeboard=include_maybeboard
    )


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
    return formatting._show_info(resolved)
