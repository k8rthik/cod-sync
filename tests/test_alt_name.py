"""Tests for the bundled-seed flavor-name canonicalization."""
from __future__ import annotations

from cod_sync import alt_name


def test_seed_entry_resolves():
    """A known reskin in the bundled seed maps to its canonical name."""
    out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Rhystic Study"}


def test_unknown_name_is_identity():
    out = alt_name.canonicalize_batch(["Counterspell"])
    assert out == {"Counterspell": "Counterspell"}


def test_batch_mixes_known_and_unknown():
    out = alt_name.canonicalize_batch(
        ["Unstable Harmonics", "Sol Ring", "Counterspell"]
    )
    assert out == {
        "Unstable Harmonics": "Rhystic Study",
        "Sol Ring": "Sol Ring",
        "Counterspell": "Counterspell",
    }


def test_empty_input_returns_empty():
    assert alt_name.canonicalize_batch([]) == {}
    assert alt_name.canonicalize_batch([""]) == {}
    assert alt_name.canonicalize_batch(["", "Sol Ring"]) == {"Sol Ring": "Sol Ring"}


def test_canonicalize_single():
    assert alt_name.canonicalize("Unstable Harmonics") == "Rhystic Study"
    assert alt_name.canonicalize("Sol Ring") == "Sol Ring"
    assert alt_name.canonicalize("") == ""


def test_seed_is_non_trivial():
    """Guardrail: the bundled seed should have at least a few entries.

    Catches an accidentally-blanked _seed_data.py before it ships.
    """
    assert len(alt_name._SEED) > 50
