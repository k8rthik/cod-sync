"""Shared types for the source fetchers."""

from __future__ import annotations

from dataclasses import dataclass

Zones = dict[str, dict[str, int]]


@dataclass(frozen=True)
class AppliedRename:
    """One alt-name mapping the canonicalize step applied to a deck.

    `quantity` is the original name's own quantity in `zone` — needed to
    un-merge precisely if the user overrides the mapping, because the
    canonical entry may also hold copies that were never renamed.
    `settled` is True when the mapping came from the user's disk cache
    (confirmed or previously learned), so the CLI won't re-prompt for it.
    """

    zone: str
    original: str
    canonical: str
    quantity: int
    settled: bool


@dataclass(frozen=True)
class RemoteDeck:
    """A decklist fetched from a remote source.

    `name` is the deck's title at the source. Empty when unknown
    (e.g. plain-text decklists, which have no title).

    `zones` is the normalized form: {"main": {...}, "side": {...}}.

    `tags` is the deck-level tag list (Archidekt `deckTags`, Moxfield `hubs`).
    Empty for sources that don't expose deck-wide tags (plain text).

    `renames` lists the alt-name mappings applied while building `zones`,
    so the CLI can surface and control them.
    """

    name: str
    zones: Zones
    tags: tuple[str, ...] = ()
    renames: tuple[AppliedRename, ...] = ()
