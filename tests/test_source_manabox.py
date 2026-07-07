"""ManaBox source fetcher: HTML extraction, Astro decoding, and zone routing.

ManaBox has no JSON API; the share page server-renders the deck into an
``<astro-island>`` props attribute. These tests cover the offline pieces:
the end-to-end HTML→zones path against a saved fixture, the `[type, value]`
Astro decoder, the board-category → zone routing, and the malformed-page
error paths. The live-page format is guarded separately by the
network-gated test in `tests/integration/`.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pytest

from cod_sync import errors, sources
from cod_sync.sources import manabox
from cod_sync.sources.types import RemoteDeck

_FIXTURE = Path(__file__).parent / "fixtures" / "manabox_deck.html"


# ----- end-to-end: rendered page -> zones -----------------------------------


def _fixture_deck() -> dict:
    page = _FIXTURE.read_text(encoding="utf-8")
    return manabox._extract_deck("https://manabox.app/decks/x", page)


def test_fixture_extracts_name_and_format():
    deck = _fixture_deck()
    assert deck["name"] == "Fixture Deck"
    assert deck["format"] == "Commander"


def test_fixture_full_path_zones():
    zones = manabox._parse(_fixture_deck())
    # mainboard normals, plus a modal_dfc reduced to its front face and a
    # split card that keeps its full "A // B" name.
    assert zones["main"] == {
        "Sol Ring": 1,
        "Llanowar Elves": 4,
        "Kazuul's Fury": 1,
        "Connive // Concoct": 1,
    }
    # commander (boardCategory 0) and sideboard (4) both land in `side`.
    assert zones["side"] == {
        "Atraxa, Praetors' Voice": 1,
        "Lurrus of the Dream-Den": 1,
    }
    # the maybeboard (boardCategory 5) card is excluded from both zones.
    assert "Some Maybeboard Card" not in zones["main"]
    assert "Some Maybeboard Card" not in zones["side"]


# ----- board-category routing -----------------------------------------------


def _deck(*cards: dict) -> dict:
    return {"name": "D", "cards": list(cards)}


def _card(name: str, qty: int, board: int, layout: int = 0) -> dict:
    return {"name": name, "quantity": qty, "boardCategory": board, "layout": layout}


@pytest.mark.parametrize(
    "board",
    [
        0,  # commander
        1,  # oathbreaker
        2,  # signatureSpell
        4,  # sideboard
    ],
)
def test_command_and_sideboard_categories_route_to_side(board):
    zones = manabox._parse(_deck(_card("Atraxa, Praetors' Voice", 1, board)))
    assert zones["side"] == {"Atraxa, Praetors' Voice": 1}
    assert zones["main"] == {}


def test_mainboard_routes_to_main():
    zones = manabox._parse(_deck(_card("Sol Ring", 1, 3)))
    assert zones["main"] == {"Sol Ring": 1}
    assert zones["side"] == {}


def test_maybeboard_is_excluded():
    zones = manabox._parse(_deck(_card("Sol Ring", 1, 3), _card("Brainstorm", 4, 5)))
    assert zones["main"] == {"Sol Ring": 1}
    assert zones["side"] == {}


def test_unknown_board_category_defaults_to_main():
    # A category ManaBox might add later shouldn't silently drop the card;
    # default it into the mainboard rather than lose it.
    zones = manabox._parse(_deck(_card("Sol Ring", 1, 99)))
    assert zones["main"] == {"Sol Ring": 1}


def test_non_positive_and_nameless_entries_are_skipped():
    zones = manabox._parse(
        _deck(
            _card("Zero Qty", 0, 3),
            _card("Negative", -2, 3),
            {"name": "", "quantity": 1, "boardCategory": 3, "layout": 0},
            {"quantity": 1, "boardCategory": 3, "layout": 0},  # no name key
        )
    )
    assert zones == {"main": {}, "side": {}}


def test_duplicate_names_in_a_zone_sum():
    zones = manabox._parse(_deck(_card("Sol Ring", 1, 3), _card("Sol Ring", 2, 3)))
    assert zones["main"] == {"Sol Ring": 3}


# ----- layout-aware name shaping --------------------------------------------


def test_modal_dfc_reduces_to_front_face():
    # layout 17 == modal_dfc → Cockatrice keys it by the front face only.
    zones = manabox._parse(_deck(_card("Kazuul's Fury // Kazuul's Cliffs", 1, 3, 17)))
    assert zones["main"] == {"Kazuul's Fury": 1}


def test_transform_reduces_to_front_face():
    zones = manabox._parse(_deck(_card("Hostile Hostel // Creeping Inn", 1, 3, 3)))
    assert zones["main"] == {"Hostile Hostel": 1}


def test_split_keeps_full_name():
    # layout 1 == split → Cockatrice stores the full "A // B" name.
    zones = manabox._parse(_deck(_card("Connive // Concoct", 1, 3, 1)))
    assert zones["main"] == {"Connive // Concoct": 1}


def test_adventure_keeps_full_name():
    zones = manabox._parse(_deck(_card("Brazen Borrower // Petty Theft", 1, 3, 16)))
    assert zones["main"] == {"Brazen Borrower // Petty Theft": 1}


def test_unknown_layout_falls_back_to_front_face():
    # An unrecognized numeric layout maps to None, and cockatrice_name then
    # reduces to the front face — the conservative default.
    zones = manabox._parse(_deck(_card("Some Card // Back Side", 1, 3, 999)))
    assert zones["main"] == {"Some Card": 1}


# ----- Astro `[type, value]` decoder ----------------------------------------


def test_astro_decode_unwraps_value_object_and_array():
    encoded = [
        0,
        {
            "name": [0, "Deck"],
            "n": [0, 7],
            "cards": [1, [[0, {"q": [0, 2]}], [0, {"q": [0, 3]}]]],
        },
    ]
    assert manabox._astro_decode(encoded) == {
        "name": "Deck",
        "n": 7,
        "cards": [{"q": 2}, {"q": 3}],
    }


def test_astro_decode_passes_through_unwrapped_nodes():
    assert manabox._astro_decode("plain") == "plain"
    assert manabox._astro_decode(42) == 42


# ----- malformed pages ------------------------------------------------------


def test_missing_island_raises_malformed():
    with pytest.raises(errors.MalformedResponseError, match="deck data not found"):
        manabox._extract_deck("u", "<html><body>no island here</body></html>")


def test_invalid_props_json_raises_malformed():
    page = '<astro-island component-export="Main" props="not json" ssr></astro-island>'
    with pytest.raises(errors.MalformedResponseError, match="could not parse"):
        manabox._extract_deck("u", page)


def test_unexpected_deck_shape_raises_malformed():
    # Valid JSON in the props, but the decoded deck has no card list.
    props = html.escape(json.dumps({"deck": [0, {"name": [0, "D"]}]}), quote=True)
    page = f'<astro-island component-export="Main" props="{props}" ssr></astro-island>'
    with pytest.raises(errors.MalformedResponseError, match="unexpected deck shape"):
        manabox._extract_deck("u", page)


# ----- dispatch -------------------------------------------------------------


def test_fetch_dispatches_manabox_host(monkeypatch):
    seen: list[str] = []

    def fake_fetch(url: str, **_kw: object) -> RemoteDeck:
        seen.append(url)
        return RemoteDeck(name="X", zones={"main": {}, "side": {}})

    monkeypatch.setattr("cod_sync.sources.manabox.fetch", fake_fetch)
    sources.fetch("https://manabox.app/decks/abc123")
    assert seen == ["https://manabox.app/decks/abc123"]


def test_fetch_dispatches_www_manabox_host(monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.manabox.fetch",
        lambda url, **_kw: RemoteDeck(name="X", zones={"main": {}, "side": {}}),
    )
    # Should not raise the unsupported-site error for the www. subdomain.
    assert sources.fetch("https://www.manabox.app/decks/abc123").name == "X"
