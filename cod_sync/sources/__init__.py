"""Source fetchers: convert a URL or local text file to a normalized decklist.

Normalized form: RemoteDeck(name, zones, tags).
- name is the deck's title at the source ("" when unknown, e.g. text files)
- zones is {"main": {card_name: qty, ...}, "side": {card_name: qty, ...}},
  matching Cockatrice's zone names
- tags is the deck-level tag list, when the source exposes one

Card names leave this package in Cockatrice's database form: each
fetcher shapes multi-face names with the card's layout (`dfc`), and
`fetch` then maps reskin flavor names to canonical names in one batch
(`alt_name.canonicalize_batch`). See ARCHITECTURE.md ("Card name
shaping").
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from .. import alt_name
from ..errors import InvalidSourceError
from . import archidekt, manabox, moxfield, text
from .types import AppliedRename, RemoteDeck, Zones

__all__ = ["AppliedRename", "RemoteDeck", "Zones", "fetch"]


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
        if "manabox.app" in host:
            return manabox.fetch(source)
        raise InvalidSourceError(source, reason=f"unsupported deck site: {host or '(no host)'}")

    if os.path.isfile(source):
        with open(source, encoding="utf-8") as f:
            return RemoteDeck(name="", zones=text.parse(f.read()))

    raise InvalidSourceError(source, reason="not a known URL or readable file")


def _canonicalize(deck: RemoteDeck) -> RemoteDeck:
    """Rewrite zone names through the alt-name map. Merges colliding entries.

    Applied (non-identity) mappings are recorded on `renames` so the CLI
    can log them and prompt for unsettled ones. Single pass over the
    zones: the rewritten copy is built while checking for changes, and
    the original deck is returned untouched when every name mapped to
    itself (the common case)."""
    all_names = {name for cards in deck.zones.values() for name in cards}
    if not all_names:
        return deck
    resolutions = alt_name.canonicalize_batch_detailed(all_names)
    new_zones: Zones = {}
    renames: list[AppliedRename] = []
    for zone, cards in deck.zones.items():
        merged: dict[str, int] = {}
        for original, qty in cards.items():
            res = resolutions.get(original)
            canonical = res.canonical if res is not None else original
            if canonical != original and res is not None:
                renames.append(AppliedRename(zone, original, canonical, qty, res.settled))
            merged[canonical] = merged.get(canonical, 0) + qty
        new_zones[zone] = merged
    if not renames:
        return deck
    return RemoteDeck(name=deck.name, zones=new_zones, tags=deck.tags, renames=tuple(renames))


def _looks_like_url(s: str) -> bool:
    return bool(re.match(r"^https?://", s, re.IGNORECASE))
