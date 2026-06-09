"""URL detection and deck-path resolution helpers.

Pure helpers with no I/O beyond ``os.path.exists`` checks. The actual
``_route`` / ``_route_info`` dispatchers live in ``cli/__init__.py``
where they can see the re-exported flow functions (so monkeypatches on
``cod_sync.cli._walk_directory`` etc. reach them at call time).
"""

from __future__ import annotations

import os
import re

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
