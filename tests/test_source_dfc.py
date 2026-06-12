"""DFC normalization in the source fetchers.

Both Moxfield and Archidekt return "Front // Back" for double-faced cards.
We strip the back face before the name reaches the diff layer or the import
writer so it matches Cockatrice's card database, which keys DFCs by front
face only.
"""

from __future__ import annotations

import json

import cod_sync.sources as sources
from cod_sync.sources import archidekt, moxfield, text
from cod_sync.sources.types import RemoteDeck


def test_moxfield_strips_dfc_back_in_mainboard():
    payload = {
        "name": "DFC Deck",
        "boards": {
            "mainboard": {
                "cards": {
                    "id1": {
                        "quantity": 1,
                        "card": {"name": "Storm the Vault // Vault of Catlacan"},
                    },
                    "id2": {
                        "quantity": 2,
                        "card": {"name": "Sol Ring"},
                    },
                }
            }
        },
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Storm the Vault": 1, "Sol Ring": 2}


def test_moxfield_strips_dfc_in_sideboard_and_commanders():
    payload = {
        "boards": {
            "sideboard": {
                "cards": {
                    "id1": {
                        "quantity": 1,
                        "card": {"name": "Delver of Secrets // Insectile Aberration"},
                    }
                }
            },
            "commanders": {
                "cards": {
                    "id2": {
                        "quantity": 1,
                        "card": {"name": "Halana and Alena, Partners"},
                    }
                }
            },
        }
    }
    out = moxfield._parse(payload)
    # Commanders ride along in `side` with the literal sideboard so they
    # render with the commander pin in Cockatrice.
    assert out["side"] == {
        "Delver of Secrets": 1,
        "Halana and Alena, Partners": 1,
    }
    assert out["main"] == {}


def test_archidekt_strips_dfc_back():
    payload = {
        "categories": [],
        "cards": [
            {
                "quantity": 1,
                "categories": [],
                "card": {"oracleCard": {"name": "Storm the Vault // Vault of Catlacan"}},
            },
            {
                "quantity": 4,
                "categories": [],
                "card": {"oracleCard": {"name": "Lightning Bolt"}},
            },
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Storm the Vault": 1, "Lightning Bolt": 4}


def test_archidekt_strips_dfc_in_sideboard_category():
    payload = {
        "categories": [{"name": "Sideboard", "includedInDeck": True}],
        "cards": [
            {
                "quantity": 1,
                "categories": ["Sideboard"],
                "card": {"oracleCard": {"name": "Bala Ged Recovery // Bala Ged Sanctuary"}},
            }
        ],
    }
    out = archidekt._parse(payload)
    assert out["side"] == {"Bala Ged Recovery": 1}
    assert out["main"] == {}


def test_moxfield_keeps_room_card_full_name():
    """Rooms (Scryfall layout "split") are stored by Cockatrice under the
    full "A // B" name — the fetcher must not reduce them to the front half."""
    payload = {
        "boards": {
            "mainboard": {
                "cards": {
                    "id1": {
                        "quantity": 1,
                        "card": {
                            "name": "Bottomless Pool // Locker Room",
                            "layout": "split",
                        },
                    }
                }
            }
        },
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Bottomless Pool // Locker Room": 1}


def test_moxfield_keeps_adventure_full_name():
    """Adventures (and Tarkir omens, which share the layout) are stored by
    Cockatrice under the full "A // B" name, same as split-style cards."""
    payload = {
        "boards": {
            "mainboard": {
                "cards": {
                    "id1": {
                        "quantity": 1,
                        "card": {
                            "name": "Brazen Borrower // Petty Theft",
                            "layout": "adventure",
                        },
                    }
                }
            }
        },
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Brazen Borrower // Petty Theft": 1}


def test_archidekt_keeps_prepare_full_name():
    payload = {
        "categories": [],
        "cards": [
            {
                "quantity": 1,
                "categories": [],
                "card": {
                    "oracleCard": {
                        "name": "Studious First-Year // Rampant Growth",
                        "layout": "prepare",
                    }
                },
            }
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Studious First-Year // Rampant Growth": 1}


def test_moxfield_strips_transform_with_explicit_layout():
    payload = {
        "boards": {
            "mainboard": {
                "cards": {
                    "id1": {
                        "quantity": 1,
                        "card": {
                            "name": "Storm the Vault // Vault of Catlacan",
                            "layout": "transform",
                        },
                    }
                }
            }
        },
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Storm the Vault": 1}


def test_moxfield_keeps_aftermath_full_name():
    payload = {
        "boards": {
            "mainboard": {
                "cards": {
                    "id1": {
                        "quantity": 1,
                        "card": {"name": "Dusk // Dawn", "layout": "aftermath"},
                    }
                }
            }
        },
    }
    out = moxfield._parse(payload)
    assert out["main"] == {"Dusk // Dawn": 1}


def test_archidekt_keeps_room_card_full_name():
    payload = {
        "categories": [],
        "cards": [
            {
                "quantity": 1,
                "categories": [],
                "card": {
                    "oracleCard": {
                        "name": "Bottomless Pool // Locker Room",
                        "layout": "split",
                    }
                },
            }
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Bottomless Pool // Locker Room": 1}


def test_archidekt_strips_transform_with_explicit_layout():
    payload = {
        "categories": [],
        "cards": [
            {
                "quantity": 1,
                "categories": [],
                "card": {
                    "oracleCard": {
                        "name": "Storm the Vault // Vault of Catlacan",
                        "layout": "transform",
                    }
                },
            }
        ],
    }
    out = archidekt._parse(payload)
    assert out["main"] == {"Storm the Vault": 1}


def test_text_parser_strips_dfc_back():
    src = """
Deck
1 Storm the Vault // Vault of Catlacan
4 Lightning Bolt

Sideboard
2 Bala Ged Recovery // Bala Ged Sanctuary
"""
    out = text.parse(src)
    assert out["main"] == {"Storm the Vault": 1, "Lightning Bolt": 4}
    assert out["side"] == {"Bala Ged Recovery": 2}


def test_canonicalize_does_not_resurrect_dfc_back_face_from_legacy_cache(tmp_path, monkeypatch):
    """End-to-end regression for the user-reported failure: the Archidekt
    fetcher correctly reduces a modal_dfc to its front face ("Fell the
    Profane"), but a cache written before layout-aware shaping mapped that
    front face back to the raw Scryfall canonical ("Fell the Profane //
    Fell Mire"), and the canonicalize step wrote the full name into the
    .cod — a name Cockatrice cannot load. Legacy cache values must never
    re-expand an already-shaped name."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"Fell the Profane": "Fell the Profane // Fell Mire"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    deck = RemoteDeck(name="Deck", zones={"main": {"Fell the Profane": 1}, "side": {}})
    out = sources._canonicalize(deck)
    assert out.zones["main"] == {"Fell the Profane": 1}


def test_text_parser_merges_dfc_and_front_only_entries():
    """If a text file has both forms for the same card they sum together."""
    src = """
2 Storm the Vault
1 Storm the Vault // Vault of Catlacan
"""
    out = text.parse(src)
    assert out["main"] == {"Storm the Vault": 3}
