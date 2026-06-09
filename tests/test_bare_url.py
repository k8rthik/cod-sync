"""Tests for `cod-sync <URL>` (no file path).

Picks a filename from the remote's title, writes it in cwd, then defers to
`_sync_file` for the actual deck construction.
"""
from __future__ import annotations

import pytest

from cod_sync import cli, cod
from cod_sync.sources import RemoteDeck


URL = "https://www.moxfield.com/decks/abc123"


@pytest.fixture(autouse=True)
def _default_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")


def _remote(zones, name=""):
    return RemoteDeck(name=name, zones=zones)


def test_writes_sanitized_title_in_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="Atraxa Superfriends!",
        ),
    )

    rc = cli._create_from_bare_url(URL, yes=True, dry_run=False)

    assert rc == 0
    expected = tmp_path / "atraxa_superfriends.cod"
    assert expected.exists()
    assert cod.load(str(expected)).deckname == "Atraxa Superfriends!"


def test_lowercases_and_drops_punctuation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}},
                             name="Storm/the/Vault: A Deck!"),
    )

    cli._create_from_bare_url(URL, yes=True, dry_run=False)

    assert (tmp_path / "stormthevault_a_deck.cod").exists()


def test_falls_back_to_imported_deck_when_title_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name=""),
    )

    cli._create_from_bare_url(URL, yes=True, dry_run=False)

    assert (tmp_path / "imported_deck.cod").exists()


def test_falls_back_when_title_is_all_punctuation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}},
                             name="!!!???"),
    )

    cli._create_from_bare_url(URL, yes=True, dry_run=False)

    assert (tmp_path / "imported_deck.cod").exists()


def test_syncs_existing_target_against_url(tmp_path, monkeypatch, capsys):
    """When the default-named .cod already exists, sync it against the URL
    instead of refusing — that's what the user wants from `cod-sync <URL>`
    when they've already imported the deck once."""
    monkeypatch.chdir(tmp_path)
    existing = cod.Deck(deckname="Atraxa", zones=(
        cod.Zone(name="main", cards=(cod.Card(name="Sol Ring", quantity=1),)),
    ))
    cod.save(existing, str(tmp_path / "atraxa.cod"))

    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1, "Counterspell": 4}, "side": {}},
            name="Atraxa",
        ),
    )

    rc = cli._create_from_bare_url(URL, yes=True, dry_run=False)

    assert rc == 0
    # The existing file is updated with the new card from the URL.
    deck = cod.load(str(tmp_path / "atraxa.cod"))
    main_zone = deck.zone("main")
    assert main_zone is not None
    names = {c.name for c in main_zone.cards}
    assert names == {"Sol Ring", "Counterspell"}
    err = capsys.readouterr().err
    assert "already exists" not in err


def test_fetch_failure_returns_error(tmp_path, monkeypatch, capsys):
    from cod_sync import errors

    monkeypatch.chdir(tmp_path)

    def boom(_src):
        raise errors.DeckPrivateError(URL)

    monkeypatch.setattr("cod_sync.cli.sources.fetch", boom)

    rc = cli._create_from_bare_url(URL, yes=True, dry_run=False)

    assert rc == 2
    assert "private" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_sanitize_filename_unit():
    assert cli._sanitize_filename("Atraxa Superfriends") == "atraxa_superfriends"
    assert cli._sanitize_filename("  spaces  ") == "spaces"
    assert cli._sanitize_filename("multi   spaces") == "multi_spaces"
    assert cli._sanitize_filename("__leading_trailing__") == "leading_trailing"
    assert cli._sanitize_filename("") == ""
    assert cli._sanitize_filename("!!!") == ""
    assert cli._sanitize_filename("abc123-def") == "abc123-def"
