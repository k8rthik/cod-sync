"""Source fetchers: convert a URL or local text file to a normalized decklist.

Normalized form: RemoteDeck(name, zones).
- name is the deck's title at the source ("" when unknown, e.g. text files)
- zones is {"main": {card_name: qty, ...}, "side": {card_name: qty, ...}}
Zone names match Cockatrice's ("main", "side").

After the source-specific fetch, every card name is run through
`alt_name.canonicalize_batch` so flavor-name reskins (Secret Lair etc.) are
mapped to their Cockatrice-recognized canonical names in one batch lookup.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from .. import alt_name
from ..errors import InvalidSourceError
from . import archidekt, moxfield, text
from .types import RemoteDeck, Zones

__all__ = ["RemoteDeck", "Zones", "fetch"]


def fetch(source: str) -> RemoteDeck:
    """Dispatch based on URL host or file extension, then canonicalize names."""
    raw = _fetch_raw(source)
    return _canonicalize(raw)


def _fetch_raw(source: str) -> RemoteDeck:
    if _looks_like_url(source):
        host = (urlparse(source).hostname or "").lower()
        if "moxfield.com" in host:
            return moxfield.fetch(source)
        if "archidekt.com" in host:
            return archidekt.fetch(source)
        raise InvalidSourceError(source, reason=f"unsupported deck site: {host or '(no host)'}")

    if os.path.isfile(source):
        with open(source, encoding="utf-8") as f:
            return RemoteDeck(name="", zones=text.parse(f.read()))

    raise InvalidSourceError(source, reason="not a known URL or readable file")


def _canonicalize(deck: RemoteDeck) -> RemoteDeck:
    """Rewrite zone names through the alt-name map. Merges colliding entries."""
    all_names = {name for cards in deck.zones.values() for name in cards}
    if not all_names:
        return deck
    mapping = alt_name.canonicalize_batch(all_names)
    if all(mapping.get(n, n) == n for n in all_names):
        return deck
    new_zones: Zones = {}
    for zone, cards in deck.zones.items():
        merged: dict[str, int] = {}
        for original, qty in cards.items():
            canonical = mapping.get(original, original)
            merged[canonical] = merged.get(canonical, 0) + qty
        new_zones[zone] = merged
    return RemoteDeck(name=deck.name, zones=new_zones, tags=deck.tags)


def _looks_like_url(s: str) -> bool:
    return bool(re.match(r"^https?://", s, re.IGNORECASE))
