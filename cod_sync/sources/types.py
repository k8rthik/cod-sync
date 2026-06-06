"""Shared types for the source fetchers."""
from __future__ import annotations

from dataclasses import dataclass

Zones = dict[str, dict[str, int]]


@dataclass(frozen=True)
class RemoteDeck:
    """A decklist fetched from a remote source.

    `name` is the deck's title at the source. Empty when unknown
    (e.g. plain-text decklists, which have no title).

    `zones` is the normalized form: {"main": {...}, "side": {...}}.
    """
    name: str
    zones: Zones
