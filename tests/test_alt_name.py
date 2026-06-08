"""Tests for the reskin / flavor-name canonicalization layer."""
from __future__ import annotations

import json

import pytest

from cod_sync import alt_name


# ----- seed + cache --------------------------------------------------------


def test_seed_resolves_without_network():
    """Bundled seed entries resolve even with COD_SYNC_NO_NETWORK=1."""
    out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Rhystic Study"}


def test_unknown_name_identity_when_network_disabled():
    out = alt_name.canonicalize_batch(["Counterspell"])
    assert out == {"Counterspell": "Counterspell"}


def test_empty_input_returns_empty():
    assert alt_name.canonicalize_batch([]) == {}
    assert alt_name.canonicalize_batch([""]) == {}


def test_single_canonicalize_wrapper():
    assert alt_name.canonicalize("Unstable Harmonics") == "Rhystic Study"
    assert alt_name.canonicalize("Counterspell") == "Counterspell"
    assert alt_name.canonicalize("") == ""


def test_disk_cache_entries_override_unknown(monkeypatch, tmp_path):
    """A cached mapping resolves without seed or network."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"Some Reskin": "Real Card"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["Some Reskin"])
    assert out == {"Some Reskin": "Real Card"}


def test_corrupt_cache_is_tolerated(monkeypatch, tmp_path):
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("{not valid json")
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    # Should still resolve seed entries; unknowns become identity.
    out = alt_name.canonicalize_batch(["Unstable Harmonics", "Sol Ring"])
    assert out == {"Unstable Harmonics": "Rhystic Study", "Sol Ring": "Sol Ring"}


# ----- Scryfall path -------------------------------------------------------


def _allow_network(monkeypatch):
    monkeypatch.delenv("COD_SYNC_NO_NETWORK", raising=False)


def test_scryfall_resolves_flavor_name(monkeypatch, tmp_path):
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    def fake_lookup(names):
        assert names == ["Some Newer Reskin"]
        return {"Some Newer Reskin": "Original Card"}

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(["Some Newer Reskin"])
    assert out == {"Some Newer Reskin": "Original Card"}

    # Cached on disk so the next call doesn't re-query.
    cache_data = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cache_data["Some Newer Reskin"] == "Original Card"


def test_scryfall_404_caches_identity(monkeypatch, tmp_path):
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", lambda _n: {})

    out = alt_name.canonicalize_batch(["Madeup Card"])
    assert out == {"Madeup Card": "Madeup Card"}

    cache_data = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cache_data["Madeup Card"] == "Madeup Card"


def test_seed_short_circuits_scryfall(monkeypatch, tmp_path):
    """Seed cards never touch the network even when it's available."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    called = []
    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda names: called.append(names) or {},
    )

    out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Rhystic Study"}
    assert called == []


def test_scryfall_mixed_known_and_unknown(monkeypatch, tmp_path):
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    def fake_lookup(names):
        # Only "Mystery" passes through (Unstable Harmonics is in seed).
        assert set(names) == {"Mystery", "Counterspell"}
        return {"Mystery": "Real Mystery"}

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(["Unstable Harmonics", "Mystery", "Counterspell"])
    assert out == {
        "Unstable Harmonics": "Rhystic Study",
        "Mystery": "Real Mystery",
        "Counterspell": "Counterspell",  # not_found in Scryfall response → identity
    }


# ----- response matching ---------------------------------------------------


def test_absorb_response_matches_in_order():
    resolved: dict[str, str] = {}
    chunk = ["A flavor", "B normal", "C bogus", "D normal"]
    data = {
        "data": [
            {"name": "A canonical"},
            {"name": "B normal"},
            {"name": "D normal"},
        ],
        "not_found": [{"name": "C bogus"}],
    }
    alt_name._absorb_response(chunk, data, resolved)
    assert resolved == {
        "A flavor": "A canonical",
        "B normal": "B normal",
        "D normal": "D normal",
    }


def test_absorb_response_handles_empty_response():
    resolved: dict[str, str] = {}
    alt_name._absorb_response(["A"], {}, resolved)
    assert resolved == {}


# ----- direct Scryfall HTTP layer (mocked) ---------------------------------


def test_scryfall_lookup_swallows_network_error(monkeypatch):
    """Network failures resolve to identity, no exception."""
    import requests

    def boom(*_a, **_k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("cod_sync.alt_name.requests.post", boom)

    assert alt_name._scryfall_batch_lookup(["X"]) == {}


def test_scryfall_lookup_handles_bad_json(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not json")

    monkeypatch.setattr("cod_sync.alt_name.requests.post", lambda *_a, **_k: FakeResp())
    assert alt_name._scryfall_batch_lookup(["X"]) == {}
