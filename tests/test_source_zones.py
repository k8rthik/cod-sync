"""Zone routing rules across source fetchers.

Cockatrice has no commander/companion zone; the convention is that any
card meant to render with the commander pin lives in the sideboard. Each
source must respect this when mapping its own structure onto our
{main, side} model.
"""

from __future__ import annotations

from cod_sync.sources import archidekt, manabox, moxfield, text

# ----- Moxfield -------------------------------------------------------------


def test_moxfield_commanders_route_to_side():
    payload = {
        "boards": {
            "mainboard": {
                "cards": {"a": {"quantity": 1, "card": {"name": "Sol Ring"}}},
            },
            "commanders": {
                "cards": {"b": {"quantity": 1, "card": {"name": "Atraxa, Praetors' Voice"}}},
            },
        }
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Sol Ring": 1}
    assert out["side"] == {"Atraxa, Praetors' Voice": 1}


def test_moxfield_companions_route_to_side():
    payload = {
        "boards": {
            "mainboard": {
                "cards": {"a": {"quantity": 1, "card": {"name": "Lightning Bolt"}}},
            },
            "companions": {
                "cards": {"b": {"quantity": 1, "card": {"name": "Lurrus of the Dream-Den"}}},
            },
        }
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Lightning Bolt": 1}
    assert out["side"] == {"Lurrus of the Dream-Den": 1}


# ----- Archidekt ------------------------------------------------------------


def test_archidekt_commander_category_routes_to_side():
    payload = {
        "categories": [{"name": "Commander", "includedInDeck": True}],
        "cards": [
            {
                "quantity": 1,
                "categories": ["Commander"],
                "card": {"oracleCard": {"name": "Atraxa, Praetors' Voice"}},
            },
            {
                "quantity": 1,
                "categories": [],
                "card": {"oracleCard": {"name": "Sol Ring"}},
            },
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Sol Ring": 1}
    assert out["side"] == {"Atraxa, Praetors' Voice": 1}


def test_archidekt_companion_category_routes_to_side():
    payload = {
        "categories": [{"name": "Companion", "includedInDeck": True}],
        "cards": [
            {
                "quantity": 1,
                "categories": ["Companion"],
                "card": {"oracleCard": {"name": "Lurrus of the Dream-Den"}},
            },
            {
                "quantity": 4,
                "categories": [],
                "card": {"oracleCard": {"name": "Lightning Bolt"}},
            },
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Lightning Bolt": 4}
    assert out["side"] == {"Lurrus of the Dream-Den": 1}


def test_archidekt_secondary_category_does_not_re_zone():
    """A card's first category is its primary — the one that determines
    placement on Archidekt. Later entries are just labels: a card filed
    under "Finisher" with a secondary sideboard-named tag is in the
    mainboard on Archidekt and must stay in main here."""
    payload = {
        "categories": [
            {"name": "Finisher", "includedInDeck": True},
            {"name": "SIdeboard", "includedInDeck": True},
        ],
        "cards": [
            {
                "quantity": 1,
                "categories": ["Finisher", "SIdeboard"],
                "card": {"oracleCard": {"name": "Akroma's Memorial"}},
            },
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Akroma's Memorial": 1}
    assert out["side"] == {}


def test_archidekt_exclusion_follows_primary_category_only():
    """Maybeboard exclusion is also primary-only: a card whose primary
    category is Maybeboard is out of the deck, but a card merely tagged
    with Maybeboard as a secondary label is still in the deck."""
    payload = {
        "categories": [
            {"name": "Maybeboard", "includedInDeck": False},
            {"name": "Creature", "includedInDeck": True},
        ],
        "cards": [
            {
                "quantity": 1,
                "categories": ["Maybeboard", "Creature"],
                "card": {"oracleCard": {"name": "Gandalf the White"}},
            },
            {
                "quantity": 1,
                "categories": ["Creature", "Maybeboard"],
                "card": {"oracleCard": {"name": "Llanowar Elves"}},
            },
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Llanowar Elves": 1}
    assert out["side"] == {}


# ----- Maybeboard: dropped by default, folded into side when requested ------


def test_moxfield_maybeboard_dropped_by_default():
    payload = {
        "boards": {
            "mainboard": {"cards": {"a": {"quantity": 1, "card": {"name": "Sol Ring"}}}},
            "maybeboard": {"cards": {"b": {"quantity": 1, "card": {"name": "Mana Crypt"}}}},
        }
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Sol Ring": 1}
    assert out["side"] == {}


def test_moxfield_maybeboard_folds_into_side_when_included():
    payload = {
        "boards": {
            "mainboard": {"cards": {"a": {"quantity": 1, "card": {"name": "Sol Ring"}}}},
            "maybeboard": {"cards": {"b": {"quantity": 1, "card": {"name": "Mana Crypt"}}}},
        }
    }
    out = moxfield._parse(payload, include_maybeboard=True)
    assert out["main"] == {"Sol Ring": 1}
    assert out["side"] == {"Mana Crypt": 1}


def test_archidekt_maybeboard_folds_into_side_when_included():
    payload = {
        "categories": [
            {"name": "Maybeboard", "includedInDeck": False},
            {"name": "Creature", "includedInDeck": True},
        ],
        "cards": [
            {
                "quantity": 1,
                "categories": ["Creature"],
                "card": {"oracleCard": {"name": "Llanowar Elves"}},
            },
            {
                "quantity": 1,
                "categories": ["Maybeboard"],
                "card": {"oracleCard": {"name": "Gandalf the White"}},
            },
        ],
    }
    out = archidekt._parse(payload, include_maybeboard=True)
    assert out["main"] == {"Llanowar Elves": 1}
    assert out["side"] == {"Gandalf the White": 1}


def test_manabox_maybeboard_dropped_by_default():
    deck = {
        "cards": [
            {"boardCategory": 3, "quantity": 1, "name": "Sol Ring"},
            {"boardCategory": 5, "quantity": 1, "name": "Mana Crypt"},
        ]
    }
    out = manabox._parse(deck)
    assert out["main"] == {"Sol Ring": 1}
    assert out["side"] == {}


def test_manabox_maybeboard_folds_into_side_when_included():
    deck = {
        "cards": [
            {"boardCategory": 3, "quantity": 1, "name": "Sol Ring"},
            {"boardCategory": 5, "quantity": 1, "name": "Mana Crypt"},
        ]
    }
    out = manabox._parse(deck, include_maybeboard=True)
    assert out["main"] == {"Sol Ring": 1}
    assert out["side"] == {"Mana Crypt": 1}


# ----- Text -----------------------------------------------------------------


def test_text_commander_header_routes_to_side():
    result = text.parse("Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Sol Ring\n")
    assert result == {
        "main": {"Sol Ring": 1},
        "side": {"Atraxa, Praetors' Voice": 1},
    }


def test_text_companion_header_routes_to_side():
    result = text.parse("Companion\n1 Lurrus of the Dream-Den\nDeck\n4 Lightning Bolt\n")
    assert result == {
        "main": {"Lightning Bolt": 4},
        "side": {"Lurrus of the Dream-Den": 1},
    }
