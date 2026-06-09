"""Integration: `sources.fetch` post-processes through `alt_name.canonicalize_batch`.

The source modules return whatever Moxfield / Archidekt give us. The
shared `_canonicalize` step in `sources/__init__.py` rewrites flavor
names to canonical names so the resulting deck matches Cockatrice's
card database.
"""

from __future__ import annotations

from cod_sync import sources
from cod_sync.sources import RemoteDeck


def test_fetch_canonicalizes_seed_reskin(monkeypatch):
    """A reskin in seed gets rewritten without touching the network."""
    raw = RemoteDeck(
        name="Reskin Test",
        zones={"main": {"Unstable Harmonics": 1, "Sol Ring": 1}, "side": {}},
    )
    monkeypatch.setattr("cod_sync.sources._fetch_raw", lambda _s: raw)

    deck = sources.fetch("https://www.moxfield.com/decks/x")

    assert deck.name == "Reskin Test"
    assert deck.zones["main"] == {"Rhystic Study": 1, "Sol Ring": 1}


def test_fetch_merges_quantities_when_flavor_and_canonical_collide(monkeypatch):
    """If the source returns both flavor and canonical, merge into one entry."""
    raw = RemoteDeck(
        name="",
        zones={"main": {"Unstable Harmonics": 1, "Rhystic Study": 2}, "side": {}},
    )
    monkeypatch.setattr("cod_sync.sources._fetch_raw", lambda _s: raw)

    deck = sources.fetch("https://www.moxfield.com/decks/x")

    assert deck.zones["main"] == {"Rhystic Study": 3}


def test_fetch_passes_through_normal_cards_unchanged(monkeypatch):
    raw = RemoteDeck(
        name="Normal Deck",
        zones={"main": {"Sol Ring": 1, "Counterspell": 4}, "side": {"Negate": 2}},
    )
    monkeypatch.setattr("cod_sync.sources._fetch_raw", lambda _s: raw)

    deck = sources.fetch("https://www.moxfield.com/decks/x")

    assert deck.zones == {
        "main": {"Sol Ring": 1, "Counterspell": 4},
        "side": {"Negate": 2},
    }


def test_fetch_empty_zones_short_circuits(monkeypatch):
    """No card names → no canonicalize call, return deck as-is."""
    raw = RemoteDeck(name="Empty", zones={"main": {}, "side": {}})
    monkeypatch.setattr("cod_sync.sources._fetch_raw", lambda _s: raw)

    deck = sources.fetch("https://www.moxfield.com/decks/x")

    assert deck.zones == {"main": {}, "side": {}}
