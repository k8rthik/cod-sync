"""Deck-level tag extraction across source fetchers.

Archidekt exposes deck-wide tags via `deckTags` (distinct from per-card
`categories`); Moxfield exposes them via `hubs` (distinct from per-card
`tags`). Per-card site labels are intentionally not extracted — they have
no Cockatrice equivalent and would conflate semantic levels.
"""

from __future__ import annotations

from cod_sync.sources import archidekt, moxfield

# ----- Archidekt ------------------------------------------------------------


def test_archidekt_deck_tags_dict_form():
    payload = {"deckTags": [{"id": 1, "name": "Budget"}, {"name": "Combo"}]}
    assert archidekt._extract_tags(payload) == ("Budget", "Combo")


def test_archidekt_deck_tags_string_form():
    payload = {"deckTags": ["Budget", "Combo"]}
    assert archidekt._extract_tags(payload) == ("Budget", "Combo")


def test_archidekt_deck_tags_skips_blanks_and_dedupes():
    payload = {
        "deckTags": [
            {"name": "Budget"},
            {"name": "  "},
            {"name": "budget"},
            "",
            None,
            42,
            "Combo",
        ]
    }
    assert archidekt._extract_tags(payload) == ("Budget", "Combo")


def test_archidekt_deck_tags_absent_returns_empty():
    assert archidekt._extract_tags({}) == ()


def test_archidekt_deck_tags_explicit_empty_returns_empty():
    assert archidekt._extract_tags({"deckTags": []}) == ()


def test_archidekt_deck_tags_independent_of_per_card_categories():
    """`categories` (per-card roles) must not leak into `deckTags`."""
    payload = {
        "deckTags": [],
        "categories": [{"name": "Maybeboard", "includedInDeck": False}],
        "cards": [],
    }
    assert archidekt._extract_tags(payload) == ()


# ----- Moxfield -------------------------------------------------------------


def test_moxfield_hubs_extracted():
    payload = {"hubs": [{"name": "Aggro", "slug": "aggro"}, {"name": "Combo"}]}
    assert moxfield._extract_tags(payload) == ("Aggro", "Combo")


def test_moxfield_hubs_skips_blanks_and_dedupes():
    payload = {
        "hubs": [
            {"name": "Aggro", "slug": "aggro"},
            {"name": "  "},
            {"name": "aggro"},
            "loose-string-ignored",
            {"name": "Combo"},
        ]
    }
    assert moxfield._extract_tags(payload) == ("Aggro", "Combo")


def test_moxfield_hubs_absent_returns_empty():
    assert moxfield._extract_tags({}) == ()


def test_moxfield_hubs_explicit_empty_returns_empty():
    assert moxfield._extract_tags({"hubs": []}) == ()
