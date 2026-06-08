"""Zone routing rules across source fetchers.

Cockatrice has no commander/companion zone; the convention is that any
card meant to render with the commander pin lives in the sideboard. Each
source must respect this when mapping its own structure onto our
{main, side} model.
"""
from __future__ import annotations

from cod_sync.sources import archidekt, moxfield, text


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


# ----- Text -----------------------------------------------------------------


def test_text_commander_header_routes_to_side():
    result = text.parse(
        "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Sol Ring\n"
    )
    assert result == {
        "main": {"Sol Ring": 1},
        "side": {"Atraxa, Praetors' Voice": 1},
    }


def test_text_companion_header_routes_to_side():
    result = text.parse(
        "Companion\n1 Lurrus of the Dream-Den\nDeck\n4 Lightning Bolt\n"
    )
    assert result == {
        "main": {"Lightning Bolt": 4},
        "side": {"Lurrus of the Dream-Den": 1},
    }
