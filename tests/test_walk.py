"""Tests for `_walk_directory` per-deck prompt UX.

The dispatcher tests in `test_dispatch.py` mock `_walk_directory` itself, so
this file exercises the actual prompt loop end-to-end with a fake `input`
queue and a stubbed `sources.fetch`.
"""
from __future__ import annotations

import pytest

from cod_sync import cli, cod, sourcetag
from cod_sync.sources import RemoteDeck


URL_STORED = "https://archidekt.com/decks/12345"
URL_TYPED = "https://www.moxfield.com/decks/typed"


def _write(path, *, deckname="", url=None, main=None):
    comments = f"cod-sync-source: {url}" if url else ""
    zones = []
    if main:
        zones.append(cod.Zone(name="main", cards=tuple(
            cod.Card(name=n, quantity=q) for n, q in main.items()
        )))
    deck = cod.Deck(deckname=deckname, comments=comments, zones=tuple(zones))
    cod.save(deck, str(path))


def _stub_fetch(monkeypatch):
    """Record fetch() calls; return a RemoteDeck that produces zero diff."""
    calls: list[str] = []

    def fake_fetch(src):
        calls.append(src)
        return RemoteDeck(name="", zones={"main": {"Sol Ring": 1}, "side": {}})

    monkeypatch.setattr("cod_sync.cli.sources.fetch", fake_fetch)
    return calls


def _queue_input(monkeypatch, answers):
    """Replace input() with a queue. Raises if exhausted."""
    queue = list(answers)

    def fake_input(_prompt=""):
        if not queue:
            raise AssertionError(f"input() called more times than expected; prompt={_prompt!r}")
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", fake_input)
    return queue


# ----- stored URL branch ----------------------------------------------------


def test_stored_url_enter_accepts(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", url=URL_STORED, main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, [""])

    rc = cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert rc == 0
    assert fetched == [URL_STORED]


def test_stored_url_y_accepts(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", url=URL_STORED, main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, ["y"])

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == [URL_STORED]


def test_stored_url_n_skips(tmp_path, monkeypatch, capsys):
    _write(tmp_path / "a.cod", deckname="A", url=URL_STORED, main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, ["n"])

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == []
    out = capsys.readouterr().out
    assert "skipped=1" in out


def test_stored_url_q_quits_before_remaining_files(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", url=URL_STORED, main={"Sol Ring": 1})
    _write(tmp_path / "b.cod", deckname="B", url=URL_STORED, main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, ["q"])

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == []


def test_stored_url_yes_flag_suppresses_prompt(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", url=URL_STORED, main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)

    # If input() is touched, this raises.
    def boom(_prompt=""):
        raise AssertionError("prompt should not be shown under --yes")

    monkeypatch.setattr("builtins.input", boom)

    cli._walk_directory(str(tmp_path), recursive=False, yes=True, dry_run=False)

    assert fetched == [URL_STORED]


def test_stored_url_garbage_then_accept(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", url=URL_STORED, main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, ["huh?", "wat", "y"])

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == [URL_STORED]


def test_stored_url_eof_quits(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", url=URL_STORED, main={"Sol Ring": 1})
    _write(tmp_path / "b.cod", deckname="B", url=URL_STORED, main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)

    def fake_input(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == []


# ----- no-stored-URL branch -------------------------------------------------


def test_no_stored_url_user_types_url(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, [URL_TYPED])

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == [URL_TYPED]
    # Marker should now be stashed.
    deck = cod.load(str(tmp_path / "a.cod"))
    assert sourcetag.get_source_url(deck.comments) == URL_TYPED


def test_no_stored_url_empty_skips(tmp_path, monkeypatch, capsys):
    _write(tmp_path / "a.cod", deckname="A", main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, [""])

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == []
    assert "skipped=1" in capsys.readouterr().out


def test_no_stored_url_q_quits(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="A", main={"Sol Ring": 1})
    _write(tmp_path / "b.cod", deckname="B", main={"Sol Ring": 1})
    fetched = _stub_fetch(monkeypatch)
    _queue_input(monkeypatch, ["q"])

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert fetched == []


# ----- per-deck parity with sync (deckname mismatch) -----------------------
#
# Walk used to suppress the deckname-mismatch prompt that single-file sync
# fires. After unifying `_sync_deck`'s per-deck logic, walk should hit the
# same `cli._confirm` path. URL-conflict parity isn't tested here because
# walk only ever syncs against the stored URL (or none-then-store), so
# `stored == url_to_remember` always holds and the conflict branch is
# structurally unreachable from this entrypoint.


def _stub_fetch_named(monkeypatch, remote_name):
    """Like _stub_fetch but the remote deck carries a real name."""
    def fake_fetch(_src):
        return RemoteDeck(
            name=remote_name, zones={"main": {"Sol Ring": 1}, "side": {}}
        )

    monkeypatch.setattr("cod_sync.cli.sources.fetch", fake_fetch)


def test_walk_prompts_deckname_mismatch_accept(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="Local", url=URL_STORED, main={"Sol Ring": 1})
    _stub_fetch_named(monkeypatch, "Remote")
    _queue_input(monkeypatch, [""])  # accept stored URL in the walk-level prompt

    confirm_calls: list = []

    def fake_confirm(prompt, *, default, auto_yes):
        confirm_calls.append(prompt)
        return True

    monkeypatch.setattr("cod_sync.cli._confirm", fake_confirm)

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert len(confirm_calls) == 1
    assert "Local" in confirm_calls[0]
    assert "Remote" in confirm_calls[0]
    assert cod.load(str(tmp_path / "a.cod")).deckname == "Remote"


def test_walk_prompts_deckname_mismatch_decline(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="Local", url=URL_STORED, main={"Sol Ring": 1})
    _stub_fetch_named(monkeypatch, "Remote")
    _queue_input(monkeypatch, [""])

    monkeypatch.setattr("cod_sync.cli._confirm", lambda *a, **kw: False)

    cli._walk_directory(str(tmp_path), recursive=False, yes=False, dry_run=False)

    assert cod.load(str(tmp_path / "a.cod")).deckname == "Local"


def test_walk_yes_flag_auto_updates_deckname(tmp_path, monkeypatch):
    _write(tmp_path / "a.cod", deckname="Local", url=URL_STORED, main={"Sol Ring": 1})
    _stub_fetch_named(monkeypatch, "Remote")

    # -y must bypass *both* the walk-level y/n/q prompt AND the deckname
    # `_confirm`. Any input() call is a regression.
    def boom(_prompt=""):
        raise AssertionError("prompt should not be shown under --yes")

    monkeypatch.setattr("builtins.input", boom)

    cli._walk_directory(str(tmp_path), recursive=False, yes=True, dry_run=False)

    assert cod.load(str(tmp_path / "a.cod")).deckname == "Remote"
