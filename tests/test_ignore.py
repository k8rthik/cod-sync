"""Per-card ignore: the `i` review option and the cod-sync-ignore marker.

Answering `i` during change review marks the card as ignored: the change
is not applied, a `cod-sync-ignore: <name>` line is written into the
deck's <comments>, and future syncs stop proposing changes for that
name. Un-ignoring is deleting the line (visible in Cockatrice's
comments box).
"""

from __future__ import annotations

from cod_sync import cod, sourcetag
from cod_sync.cli.sync import _sync_file
from cod_sync.sources import RemoteDeck

URL = "https://www.moxfield.com/decks/abc123"


def _remote(zones, name=""):
    return RemoteDeck(name=name, zones=zones)


def _write_deck(path, comments="", main=None):
    zones = []
    if main:
        zones.append(
            cod.Zone(
                name="main", cards=tuple(cod.Card(name=n, quantity=q) for n, q in main.items())
            )
        )
    cod.save(cod.Deck(deckname="t", comments=comments, zones=tuple(zones)), str(path))


def _input_seq(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(it))


# ----- marker helpers --------------------------------------------------------


def test_ignore_marker_round_trip():
    comments = sourcetag.add_ignored_name("", "Sol Ring")
    assert sourcetag.get_ignored_names(comments) == frozenset({"Sol Ring"})


def test_ignore_marker_appends_without_duplicating():
    comments = sourcetag.add_ignored_name("", "Sol Ring")
    again = sourcetag.add_ignored_name(comments, "Sol Ring")
    assert again == comments


def test_ignore_marker_preserves_user_lines_and_source_marker():
    comments = "my notes\ncod-sync-source: " + URL
    out = sourcetag.add_ignored_name(comments, "Counterspell")
    assert "my notes" in out
    assert sourcetag.get_source_url(out) == URL
    assert sourcetag.get_ignored_names(out) == frozenset({"Counterspell"})


def test_ignored_names_empty_for_plain_comments():
    assert sourcetag.get_ignored_names("just some notes") == frozenset()


# ----- review `i` flow -------------------------------------------------------


def test_review_i_persists_ignore_and_skips_change(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src, **_kw: _remote({"main": {"Sol Ring": 1, "Counterspell": 4}, "side": {}}),
    )
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, main={"Sol Ring": 1})
    _input_seq(monkeypatch, ["i"])

    rc = _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert rc == 0
    deck = cod.load(str(cod_path))
    names = {c.name for z in deck.zones for c in z.cards}
    assert "Counterspell" not in names
    assert sourcetag.get_ignored_names(deck.comments) == frozenset({"Counterspell"})


def test_ignored_card_suppressed_on_next_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src, **_kw: _remote({"main": {"Sol Ring": 1, "Counterspell": 4}, "side": {}}),
    )
    comments = sourcetag.add_ignored_name(f"cod-sync-source: {URL}", "Counterspell")
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, comments=comments, main={"Sol Ring": 1})
    before = cod_path.read_text()

    def boom(*_a, **_k):
        raise AssertionError("no prompt expected: the only change is ignored")

    monkeypatch.setattr("builtins.input", boom)

    rc = _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert rc == 0
    assert cod_path.read_text() == before


def test_review_mixes_ignore_and_accept(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src, **_kw: _remote(
            {"main": {"Sol Ring": 1, "Counterspell": 4, "Negate": 2}, "side": {}}
        ),
    )
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, main={"Sol Ring": 1})
    # Changes are sorted by name: Counterspell first, then Negate.
    _input_seq(monkeypatch, ["i", "y"])

    rc = _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert rc == 0
    deck = cod.load(str(cod_path))
    names = {c.name: c.quantity for z in deck.zones for c in z.cards}
    assert names.get("Negate") == 2
    assert "Counterspell" not in names
    assert sourcetag.get_ignored_names(deck.comments) == frozenset({"Counterspell"})


def test_yes_mode_never_ignores(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src, **_kw: _remote({"main": {"Sol Ring": 1, "Counterspell": 4}, "side": {}}),
    )
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, main={"Sol Ring": 1})

    rc = _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    deck = cod.load(str(cod_path))
    names = {c.name: c.quantity for z in deck.zones for c in z.cards}
    assert names.get("Counterspell") == 4
    assert sourcetag.get_ignored_names(deck.comments) == frozenset()


def test_review_quit_discards_pending_ignores(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src, **_kw: _remote(
            {"main": {"Sol Ring": 1, "Counterspell": 4, "Negate": 2}, "side": {}}
        ),
    )
    cod_path = tmp_path / "deck.cod"
    _write_deck(cod_path, comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1})
    before = cod_path.read_text()
    _input_seq(monkeypatch, ["i", "q"])

    rc = _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert rc == 0
    assert cod_path.read_text() == before
