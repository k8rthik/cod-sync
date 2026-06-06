"""Tests for `cod-sync import`."""
from __future__ import annotations

import os

import pytest

from cod_sync import cli, cod, sourcetag


URL = "https://www.moxfield.com/decks/abc123"


@pytest.fixture(autouse=True)
def _silence_input(monkeypatch):
    """Default input() to "y" — individual tests can override."""
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")


def test_refuses_existing_file(tmp_path, capsys, monkeypatch):
    cod_path = tmp_path / "already-here.cod"
    cod_path.write_text("<not a real deck/>", encoding="utf-8")
    before = cod_path.read_text(encoding="utf-8")

    def boom(*_a, **_k):
        raise AssertionError("sources.fetch must not be called when the file exists")

    monkeypatch.setattr("cod_sync.cli.sources.fetch", boom)

    rc = cli.run_import(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 2
    assert "already exists" in capsys.readouterr().err
    assert cod_path.read_text(encoding="utf-8") == before


def test_creates_deck_from_mocked_source(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: {
            "main": {"Sol Ring": 1, "Arcane Signet": 1},
            "side": {},
        },
    )

    cod_path = tmp_path / "fresh.cod"
    rc = cli.run_import(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    assert cod_path.exists()

    deck = cod.load(str(cod_path))
    assert deck.deckname == "fresh"
    main_zone = deck.zone("main")
    assert main_zone is not None
    names = {c.name: c.quantity for c in main_zone.cards}
    assert names == {"Sol Ring": 1, "Arcane Signet": 1}
    assert deck.zone("side") is None


def test_creates_side_zone_when_remote_has_sideboard(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: {
            "main": {"Lightning Bolt": 4},
            "side": {"Pyroblast": 2},
        },
    )

    cod_path = tmp_path / "burn.cod"
    rc = cli.run_import(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    deck = cod.load(str(cod_path))
    side = deck.zone("side")
    assert side is not None
    assert {c.name: c.quantity for c in side.cards} == {"Pyroblast": 2}


def test_stores_source_url_in_comments(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: {"main": {"Sol Ring": 1}, "side": {}},
    )

    cod_path = tmp_path / "url-deck.cod"
    cli.run_import(str(cod_path), URL, yes=True, dry_run=False)

    deck = cod.load(str(cod_path))
    assert sourcetag.get_source_url(deck.comments) == URL


def test_does_not_store_url_for_file_source(tmp_path, monkeypatch):
    text_path = tmp_path / "decklist.txt"
    text_path.write_text("4 Lightning Bolt\n", encoding="utf-8")
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: {"main": {"Lightning Bolt": 4}, "side": {}},
    )

    cod_path = tmp_path / "from-file.cod"
    cli.run_import(str(cod_path), str(text_path), yes=True, dry_run=False)

    deck = cod.load(str(cod_path))
    assert sourcetag.get_source_url(deck.comments) is None


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: {"main": {"Sol Ring": 1}, "side": {}},
    )

    cod_path = tmp_path / "dry.cod"
    rc = cli.run_import(str(cod_path), URL, yes=True, dry_run=True)

    assert rc == 0
    assert not cod_path.exists()


def test_empty_remote_does_not_write(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: {"main": {}, "side": {}},
    )

    cod_path = tmp_path / "empty.cod"
    rc = cli.run_import(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    assert not cod_path.exists()
    assert "empty" in capsys.readouterr().out.lower()


def test_prompt_no_aborts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: {"main": {"Sol Ring": 1}, "side": {}},
    )
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")

    cod_path = tmp_path / "declined.cod"
    rc = cli.run_import(str(cod_path), URL, yes=False, dry_run=False)

    assert rc == 0
    assert not cod_path.exists()


def test_fetch_failure_returns_error(tmp_path, monkeypatch, capsys):
    def boom(_src):
        raise ValueError("nope")

    monkeypatch.setattr("cod_sync.cli.sources.fetch", boom)

    cod_path = tmp_path / "broken.cod"
    rc = cli.run_import(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 2
    assert not cod_path.exists()
    assert "failed to fetch" in capsys.readouterr().err
