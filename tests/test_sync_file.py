"""Tests for the unified `_sync_file` flow.

`_sync_file` handles both creating a new deck (file missing) and updating an
existing one. The two paths share fetch → diff → apply but diverge on the
prompt UX and on whether deckname / URL marker prompts run.
"""
from __future__ import annotations

import pytest

from cod_sync import cli, cod, sourcetag
from cod_sync.sources import RemoteDeck


URL = "https://www.moxfield.com/decks/abc123"
URL_OTHER = "https://archidekt.com/decks/999"


def _remote(zones, name=""):
    return RemoteDeck(name=name, zones=zones)


def _write_deck(path, deckname="", comments="", main=None, side=None):
    zones = []
    if main:
        zones.append(cod.Zone(name="main", cards=tuple(
            cod.Card(name=n, quantity=q) for n, q in main.items()
        )))
    if side:
        zones.append(cod.Zone(name="side", cards=tuple(
            cod.Card(name=n, quantity=q) for n, q in side.items()
        )))
    deck = cod.Deck(deckname=deckname, comments=comments, zones=tuple(zones))
    cod.save(deck, str(path))


@pytest.fixture(autouse=True)
def _default_input(monkeypatch):
    """Default any input() to "y" — individual tests override as needed."""
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")


# ----- new file (formerly `import`) -----------------------------------------


def test_new_file_creates_with_remote_zones(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1, "Arcane Signet": 1}, "side": {}},
            name="Tester",
        ),
    )
    cod_path = tmp_path / "fresh.cod"
    rc = cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    assert cod_path.exists()
    deck = cod.load(str(cod_path))
    names = {c.name: c.quantity for c in deck.zone("main").cards}
    assert names == {"Sol Ring": 1, "Arcane Signet": 1}


def test_new_file_uses_remote_name_as_deckname(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="Atraxa Superfriends",
        ),
    )
    cod_path = tmp_path / "atraxa.cod"
    cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    deck = cod.load(str(cod_path))
    assert deck.deckname == "Atraxa Superfriends"


def test_new_file_falls_back_to_stem_when_remote_unnamed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name=""),
    )
    cod_path = tmp_path / "my-deck.cod"
    cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "my-deck"


def test_new_file_stores_url_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )
    cod_path = tmp_path / "deck.cod"
    cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL


def test_new_file_with_text_source_does_not_store_marker(tmp_path, monkeypatch):
    text_path = tmp_path / "list.txt"
    text_path.write_text("4 Lightning Bolt\n", encoding="utf-8")
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Lightning Bolt": 4}, "side": {}}),
    )
    cod_path = tmp_path / "fromtxt.cod"
    cli._sync_file(str(cod_path), str(text_path), yes=True, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) is None


def test_new_file_empty_remote_does_not_write(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {}, "side": {}}, name="empty"),
    )
    cod_path = tmp_path / "empty.cod"
    rc = cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    assert not cod_path.exists()
    assert "empty" in capsys.readouterr().out.lower()


def test_new_file_declined_prompt_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}),
    )
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")

    cod_path = tmp_path / "declined.cod"
    rc = cli._sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert rc == 0
    assert not cod_path.exists()


def test_new_file_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}),
    )
    cod_path = tmp_path / "dry.cod"
    rc = cli._sync_file(str(cod_path), URL, yes=True, dry_run=True)

    assert rc == 0
    assert not cod_path.exists()


def test_dfc_imported_as_front_face_only(tmp_path, monkeypatch):
    """End-to-end: a Moxfield-shape DFC entry lands as just the front face."""
    from cod_sync.sources import moxfield
    payload = {
        "name": "DFC deck",
        "boards": {
            "mainboard": {
                "cards": {
                    "id1": {
                        "quantity": 1,
                        "card": {"name": "Storm the Vault // Vault of Catlacan"},
                    }
                }
            }
        },
    }
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: RemoteDeck(name="DFC deck", zones=moxfield._parse(payload)),
    )
    cod_path = tmp_path / "dfc.cod"
    cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    deck = cod.load(str(cod_path))
    assert {c.name for c in deck.zone("main").cards} == {"Storm the Vault"}


def test_fetch_failure_returns_error_for_new_file(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: (_ for _ in ()).throw(ValueError("nope")),
    )
    cod_path = tmp_path / "broken.cod"
    rc = cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 2
    assert not cod_path.exists()
    assert "failed to fetch" in capsys.readouterr().err


# ----- existing file (formerly `sync`) --------------------------------------


def test_existing_file_no_url_uses_stored(tmp_path, monkeypatch):
    cod_path = tmp_path / "stored.cod"
    _write_deck(cod_path, deckname="Stored", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    captured = {}

    def fake_fetch(src):
        captured["src"] = src
        return _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Stored")

    monkeypatch.setattr("cod_sync.cli.sources.fetch", fake_fetch)
    rc = cli._sync_file(str(cod_path), None, yes=True, dry_run=False)

    assert rc == 0
    assert captured["src"] == URL


def test_existing_file_no_url_and_no_stored_errors(tmp_path, capsys):
    cod_path = tmp_path / "lonely.cod"
    _write_deck(cod_path, deckname="Lonely", main={"Sol Ring": 1})

    rc = cli._sync_file(str(cod_path), None, yes=True, dry_run=False)

    assert rc == 2
    assert "no source URL" in capsys.readouterr().err


def test_existing_file_url_same_as_stored_keeps_marker(tmp_path, monkeypatch):
    cod_path = tmp_path / "match.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )

    # Track whether _confirm was called — it shouldn't be (no divergence).
    confirm_calls: list = []
    monkeypatch.setattr(
        "cod_sync.cli._confirm",
        lambda *a, **kw: confirm_calls.append((a, kw)) or False,
    )

    cli._sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert confirm_calls == []
    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL


def test_existing_file_url_differs_decline_keeps_old(tmp_path, monkeypatch):
    cod_path = tmp_path / "diff.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )
    # Decline every confirm prompt.
    monkeypatch.setattr("cod_sync.cli._confirm", lambda *a, **kw: False)

    cli._sync_file(str(cod_path), URL_OTHER, yes=False, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL


def test_existing_file_url_differs_accept_overwrites(tmp_path, monkeypatch):
    cod_path = tmp_path / "diff.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )
    monkeypatch.setattr("cod_sync.cli._confirm", lambda *a, **kw: True)

    cli._sync_file(str(cod_path), URL_OTHER, yes=False, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL_OTHER


def test_existing_file_yes_flag_auto_updates_url(tmp_path, monkeypatch):
    cod_path = tmp_path / "yesurl.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )
    # No _confirm override — the real _confirm should auto-yes under yes=True.
    cli._sync_file(str(cod_path), URL_OTHER, yes=True, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL_OTHER


def test_existing_file_remote_name_matches_no_prompt(tmp_path, monkeypatch):
    cod_path = tmp_path / "named.cod"
    _write_deck(cod_path, deckname="Same Name", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Same Name"),
    )
    confirm_calls: list = []
    monkeypatch.setattr(
        "cod_sync.cli._confirm",
        lambda *a, **kw: confirm_calls.append((a, kw)) or False,
    )

    cli._sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert confirm_calls == []
    assert cod.load(str(cod_path)).deckname == "Same Name"


def test_existing_file_remote_name_differs_decline_keeps_local(tmp_path, monkeypatch):
    cod_path = tmp_path / "rename.cod"
    _write_deck(cod_path, deckname="Local Name", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Remote Name"),
    )
    monkeypatch.setattr("cod_sync.cli._confirm", lambda *a, **kw: False)

    cli._sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "Local Name"


def test_existing_file_remote_name_differs_accept_renames(tmp_path, monkeypatch):
    cod_path = tmp_path / "rename.cod"
    _write_deck(cod_path, deckname="Local Name", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Remote Name"),
    )
    monkeypatch.setattr("cod_sync.cli._confirm", lambda *a, **kw: True)

    cli._sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "Remote Name"


def test_existing_file_yes_flag_auto_updates_deckname(tmp_path, monkeypatch):
    cod_path = tmp_path / "rename.cod"
    _write_deck(cod_path, deckname="Local Name", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Remote Name"),
    )

    cli._sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "Remote Name"


def test_existing_file_dry_run_writes_nothing(tmp_path, monkeypatch):
    cod_path = tmp_path / "dry-existing.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})
    before = cod_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 2}, "side": {}}, name="X"),
    )

    rc = cli._sync_file(str(cod_path), URL, yes=True, dry_run=True)

    assert rc == 0
    assert cod_path.read_text(encoding="utf-8") == before
