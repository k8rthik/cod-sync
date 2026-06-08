"""Banner card name is canonicalized through the same alt-name layer
as the card list. If the local banner is a reskin flavor name,
Cockatrice can't render it — sync should rewrite it to the canonical."""
from __future__ import annotations

import pytest

from cod_sync import cli, cod, sourcetag
from cod_sync.sources import RemoteDeck


URL = "https://www.moxfield.com/decks/abc123"

# A known seeded reskin → canonical mapping used by these tests.
RESKIN = "Unstable Harmonics"
CANONICAL = "Rhystic Study"


def _remote(zones, name=""):
    return RemoteDeck(name=name, zones=zones)


def _write_deck(path, *, banner=None, main=None):
    zones: tuple[cod.Zone, ...] = ()
    if main:
        zones = (cod.Zone(name="main", cards=tuple(
            cod.Card(name=n, quantity=q) for n, q in main.items()
        )),)
    deck = cod.Deck(
        deckname="x",
        comments=sourcetag.set_source_url("", URL),
        banner_card_name=banner,
        zones=zones,
    )
    cod.save(deck, str(path))


@pytest.fixture(autouse=True)
def _default_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")


def test_reskin_banner_is_rewritten_to_canonical(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])
    captured = capsys.readouterr()

    assert rc == 0
    reloaded = cod.load(str(cod_path))
    assert reloaded.banner_card_name == CANONICAL
    # The "Wrote" summary credits the banner.
    assert "banner" in captured.out


def test_banner_change_alone_triggers_save(tmp_path, monkeypatch, capsys):
    """No card-list diff, no URL change — banner rewrite is the only thing
    happening. The deck still gets written and the outcome is `updated`."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == CANONICAL


def test_canonical_banner_is_unchanged(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=CANONICAL, main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])
    captured = capsys.readouterr()

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == CANONICAL
    # No banner mention in the "Wrote" line because nothing changed.
    assert "banner" not in captured.out
    assert "No differences" in captured.out


def test_no_banner_is_noop(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=None, main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name is None


def test_banner_rewrite_works_in_walk(tmp_path, monkeypatch, capsys):
    """The walk shares the _sync_deck core, so banner canonicalization
    fires there too."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(tmp_path), "--yes"])

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == CANONICAL
