"""Tests for the DFC front-face normalization utility."""

from __future__ import annotations

from cod_sync import dfc


def test_strips_back_face_from_dfc_name():
    assert dfc.front_face("Storm the Vault // Vault of Catlacan") == "Storm the Vault"


def test_strips_back_face_from_mdfc():
    assert dfc.front_face("Bala Ged Recovery // Bala Ged Sanctuary") == "Bala Ged Recovery"


def test_passes_through_normal_card_name():
    assert dfc.front_face("Sol Ring") == "Sol Ring"


def test_passes_through_empty_string():
    assert dfc.front_face("") == ""


def test_only_splits_on_double_slash_separator():
    # A single slash isn't the DFC separator.
    assert dfc.front_face("Some/Card") == "Some/Card"


def test_only_takes_the_first_face():
    # Theoretical three-face card; we only keep what's before the first " // ".
    assert dfc.front_face("A // B // C") == "A"


# ----- layout-aware shaping (cockatrice_name) -------------------------------
#
# Cockatrice keys true double-faced cards (transform / modal_dfc) by the
# front face only, but keeps the full "A // B" name for cards whose halves
# share one face: split cards, the Duskmourn "Room" enchantments (Scryfall
# layout "split"), aftermath cards, adventures — including Tarkir omens,
# which Scryfall also classifies as layout "adventure" — and prepare cards.
# Verified against Cockatrice's own cards.xml: every adventure, aftermath,
# split, and prepare entry uses the full name; no other layout does.


def test_cockatrice_name_strips_transform():
    assert (
        dfc.cockatrice_name("Storm the Vault // Vault of Catlacan", "transform")
        == "Storm the Vault"
    )


def test_cockatrice_name_strips_modal_dfc():
    assert (
        dfc.cockatrice_name("Bala Ged Recovery // Bala Ged Sanctuary", "modal_dfc")
        == "Bala Ged Recovery"
    )


def test_cockatrice_name_keeps_split_full():
    assert dfc.cockatrice_name("Fire // Ice", "split") == "Fire // Ice"


def test_cockatrice_name_keeps_room_full():
    # Rooms are layout "split" on Scryfall; Cockatrice stores both halves.
    assert (
        dfc.cockatrice_name("Bottomless Pool // Locker Room", "split")
        == "Bottomless Pool // Locker Room"
    )


def test_cockatrice_name_keeps_aftermath_full():
    assert dfc.cockatrice_name("Dusk // Dawn", "aftermath") == "Dusk // Dawn"


def test_cockatrice_name_keeps_adventure_full():
    assert (
        dfc.cockatrice_name("Brazen Borrower // Petty Theft", "adventure")
        == "Brazen Borrower // Petty Theft"
    )


def test_cockatrice_name_keeps_omen_full():
    # Omens are layout "adventure" on Scryfall; Cockatrice stores the full name.
    assert (
        dfc.cockatrice_name("Marang River Regent // Coil and Catch", "adventure")
        == "Marang River Regent // Coil and Catch"
    )
    # Defensive alias in case a deck API ever reports the mechanic's own name.
    assert (
        dfc.cockatrice_name("Marang River Regent // Coil and Catch", "omen")
        == "Marang River Regent // Coil and Catch"
    )


def test_cockatrice_name_keeps_prepare_full():
    assert (
        dfc.cockatrice_name("Studious First-Year // Rampant Growth", "prepare")
        == "Studious First-Year // Rampant Growth"
    )


def test_cockatrice_name_keeps_room_alias_full():
    # Rooms are layout "split" on Scryfall; "room" is a defensive alias.
    assert (
        dfc.cockatrice_name("Bottomless Pool // Locker Room", "room")
        == "Bottomless Pool // Locker Room"
    )


def test_cockatrice_name_strips_flip():
    # Kamigawa flip cards carry "A // B" names on Scryfall but Cockatrice
    # keys them by the front face like true DFCs.
    assert (
        dfc.cockatrice_name("Bushi Tenderfoot // Kenzo the Hardhearted", "flip")
        == "Bushi Tenderfoot"
    )


def test_cockatrice_name_unknown_layout_strips():
    # Missing or unrecognized layout falls back to the historical behavior:
    # treat " // " as a DFC marker and keep the front face.
    assert dfc.cockatrice_name("Storm the Vault // Vault of Catlacan", None) == "Storm the Vault"
    assert dfc.cockatrice_name("Storm the Vault // Vault of Catlacan", "") == "Storm the Vault"
    assert dfc.cockatrice_name("A // B", "future_layout") == "A"


def test_cockatrice_name_layout_is_case_insensitive():
    assert dfc.cockatrice_name("Fire // Ice", "Split") == "Fire // Ice"


def test_cockatrice_name_plain_name_unchanged_for_any_layout():
    assert dfc.cockatrice_name("Sol Ring", None) == "Sol Ring"
    assert dfc.cockatrice_name("Sol Ring", "split") == "Sol Ring"
