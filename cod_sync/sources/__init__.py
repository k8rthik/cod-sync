"""Source fetchers: convert a URL or local text file to a normalized decklist.

Normalized form: {"main": {card_name: qty, ...}, "side": {card_name: qty, ...}}
Zone names match Cockatrice's ("main", "side").
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from . import archidekt, moxfield, text

Decklist = dict[str, dict[str, int]]


def fetch(source: str) -> Decklist:
    """Dispatch based on URL host or file extension."""
    if _looks_like_url(source):
        host = (urlparse(source).hostname or "").lower()
        if "moxfield.com" in host:
            return moxfield.fetch(source)
        if "archidekt.com" in host:
            return archidekt.fetch(source)
        raise ValueError(f"Unsupported deck site: {host}")

    if os.path.isfile(source):
        with open(source, encoding="utf-8") as f:
            return text.parse(f.read())

    raise ValueError(f"Source is neither a known URL nor a readable file: {source!r}")


def _looks_like_url(s: str) -> bool:
    return bool(re.match(r"^https?://", s, re.IGNORECASE))
