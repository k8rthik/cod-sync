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
