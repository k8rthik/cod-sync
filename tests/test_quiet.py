"""--quiet / -q suppresses informational stdout, preserves stderr,
and silently implies --yes."""
from __future__ import annotations

import pytest

from cod_sync import cli, cod, sourcetag
from cod_sync.sources import RemoteDeck


URL = "https://www.moxfield.com/decks/abc123"


def _remote(zones, name=""):
    return RemoteDeck(name=name, zones=zones)


def _write_deck(path, *, deckname="", comments="", main=None, side=None):
    zones = []
    if main:
        zones.append(cod.Zone(name="main", cards=tuple(
            cod.Card(name=n, quantity=q) for n, q in main.items()
        )))
    if side:
        zones.append(cod.Zone(name="side", cards=tuple(
            cod.Card(name=n, quantity=q) for n, q in side.items()
        )))
    cod.save(cod.Deck(deckname=deckname, comments=comments, zones=tuple(zones)), str(path))


@pytest.fixture(autouse=True)
def _reset_quiet():
    """Module-level _QUIET leaks across tests if a test mutates it directly.
    main() resets it on every invocation, but defensively clear here too."""
    cli._QUIET = False
    yield
    cli._QUIET = False


@pytest.fixture(autouse=True)
def _default_input(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")


# ----- stdout is suppressed -------------------------------------------------


def test_quiet_suppresses_noop_diff_message(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, deckname="x",
                comments=sourcetag.set_source_url("", URL),
                main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--quiet"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out == ""


def test_quiet_suppresses_write_summary(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, deckname="x",
                comments=sourcetag.set_source_url("", URL),
                main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1, "Counterspell": 4}, "side": {}}, name="x"),
    )

    rc = cli.main([str(cod_path), "--quiet"])
    captured = capsys.readouterr()

    assert rc == 0
    # File was actually updated — autoaccepted via implied --yes.
    deck = cod.load(str(cod_path))
    main_zone = deck.zone("main")
    assert main_zone is not None
    names = {c.name for c in main_zone.cards}
    assert "Counterspell" in names
    # But no informational output landed on stdout.
    assert captured.out == ""


def test_quiet_suppresses_walk_banner_and_stats(tmp_path, monkeypatch, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, deckname="x",
                comments=sourcetag.set_source_url("", URL),
                main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )

    rc = cli.main([str(tmp_path), "--quiet"])
    captured = capsys.readouterr()

    assert rc == 0
    assert captured.out == ""


# ----- stderr is preserved --------------------------------------------------


def test_quiet_preserves_fetch_error_on_stderr(tmp_path, monkeypatch, capsys):
    from cod_sync import errors

    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, deckname="x",
                comments=sourcetag.set_source_url("", URL),
                main={"Sol Ring": 1})

    def boom(_src):
        raise errors.NetworkError(URL, cause="network unreachable")

    monkeypatch.setattr("cod_sync.cli.sources.fetch", boom)

    rc = cli.main([str(cod_path), "--quiet"])
    captured = capsys.readouterr()

    assert rc == 2
    assert "network unreachable" in captured.err
    assert captured.out == ""


def test_quiet_preserves_walk_fetch_error_on_stderr(tmp_path, monkeypatch, capsys):
    from cod_sync import errors

    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, deckname="x",
                comments=sourcetag.set_source_url("", URL),
                main={"Sol Ring": 1})

    def boom(_src):
        raise errors.RateLimitedError(URL)

    monkeypatch.setattr("cod_sync.cli.sources.fetch", boom)

    rc = cli.main([str(tmp_path), "--quiet"])
    captured = capsys.readouterr()

    assert rc == 1  # walk exits 1 when any file had an error
    assert "rate limited" in captured.err
    assert captured.out == ""


# ----- --info is not gated by --quiet ---------------------------------------


def test_quiet_does_not_gate_info(tmp_path, capsys):
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, deckname="My Deck", main={"Sol Ring": 1})

    rc = cli.main([str(cod_path), "--info", "--quiet"])
    captured = capsys.readouterr()

    assert rc == 0
    assert "My Deck" in captured.out
    assert "Sol Ring" in captured.out


# ----- --quiet implies --yes ------------------------------------------------


def test_quiet_auto_accepts_changes_without_prompt(tmp_path, monkeypatch, capsys):
    """No input() should be consumed — confirms --quiet implies --yes."""
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, deckname="x",
                comments=sourcetag.set_source_url("", URL),
                main={"Sol Ring": 1})
    monkeypatch.setattr(
        "cod_sync.cli.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1, "Counterspell": 4}, "side": {}}, name="x"),
    )

    def boom(*_a, **_k):
        raise AssertionError("input() should not be called under --quiet")

    monkeypatch.setattr("builtins.input", boom)

    rc = cli.main([str(cod_path), "--quiet"])
    assert rc == 0
    deck = cod.load(str(cod_path))
    main_zone = deck.zone("main")
    assert main_zone is not None
    assert {c.name for c in main_zone.cards} == {"Sol Ring", "Counterspell"}
