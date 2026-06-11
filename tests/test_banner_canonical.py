"""Banner card name is canonicalized only when the local banner is
genuinely orphaned — that is, the canonical name is in the deck's card
list and the original (reskin) name is not. In any other state the
banner is left alone, so the user's local Cockatrice settings win."""

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
        zones = (
            cod.Zone(
                name="main", cards=tuple(cod.Card(name=n, quantity=q) for n, q in main.items())
            ),
        )
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


# ----- the orphan case: banner points at a card no longer in the deck -------


def test_orphaned_reskin_banner_is_repointed_to_canonical(tmp_path, monkeypatch, capsys):
    """Banner says "Unstable Harmonics", deck has "Rhystic Study". The
    banner used to refer to a real card; the card got canonicalized; the
    banner got stranded. Restoring the link is preserving intent, not
    overriding it."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1, CANONICAL: 1})
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1, CANONICAL: 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])
    captured = capsys.readouterr()

    assert rc == 0
    reloaded = cod.load(str(cod_path))
    assert reloaded.banner_card_name == CANONICAL
    assert "banner" in captured.out


def test_orphan_repoint_alone_triggers_save(tmp_path, monkeypatch, capsys):
    """No card-list diff, no URL change — banner repoint is the only
    thing happening. The deck still gets written."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1, CANONICAL: 1})
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1, CANONICAL: 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == CANONICAL


def test_orphan_repoint_fires_under_walk(tmp_path, monkeypatch, capsys):
    """The walk shares the _sync_deck core, so the orphan fix runs there
    too."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1, CANONICAL: 1})
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1, CANONICAL: 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(tmp_path), "--yes"])

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == CANONICAL


# ----- the safe cases: don't rewrite the banner -----------------------------


def test_reskin_banner_preserved_when_reskin_still_in_card_list(tmp_path, monkeypatch, capsys):
    """Banner says "Unstable Harmonics" AND the deck still has
    "Unstable Harmonics" (e.g. user declined a canonicalize sync, or is
    intentionally running the reskin name locally). Don't touch the
    banner — rewriting would orphan it from a card the deck still has."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1, RESKIN: 1})
    # Remote also has the reskin name (so no card-list diff and no
    # canonicalize pressure on the local deck).
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1, RESKIN: 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])
    captured = capsys.readouterr()

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == RESKIN
    assert "banner" not in captured.out


def test_canonical_banner_unchanged(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=CANONICAL, main={"Sol Ring": 1, CANONICAL: 1})
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1, CANONICAL: 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])
    captured = capsys.readouterr()

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == CANONICAL
    assert "banner" not in captured.out
    assert "No differences" in captured.out


def test_no_banner_is_noop(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner=None, main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name is None


def test_banner_in_card_list_makes_no_alt_name_lookup(tmp_path, monkeypatch):
    """When the banner already names a card in the deck (the common case),
    the sync must not call alt_name at all — a cold-cache unknown banner
    would otherwise pay a Scryfall round-trip per sync to learn nothing."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, banner="Sol Ring", main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )
    calls = [0]

    def counting_canonicalize(name):
        calls[0] += 1
        return name

    monkeypatch.setattr("cod_sync.alt_name.canonicalize", counting_canonicalize)

    rc = cli.main([str(cod_path), "--yes"])

    assert rc == 0
    assert calls[0] == 0


def test_banner_preserved_when_canonical_not_in_card_list(tmp_path, monkeypatch, capsys):
    """Banner has a reskin name but the canonical isn't in the deck
    either. Rewriting would create a fresh orphan. Leave the banner
    alone; the user's setting wins."""
    cod_path = tmp_path / "deck.cod"
    # Deck has neither the reskin nor the canonical. Banner is a reskin
    # the user pinned for some reason — maybe a card from another deck
    # they wanted as the avatar.
    _write_deck(cod_path, banner=RESKIN, main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--yes"])

    assert rc == 0
    assert cod.load(str(cod_path)).banner_card_name == RESKIN
