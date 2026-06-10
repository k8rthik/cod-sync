"""Tests for the unified `_sync_file` flow.

`_sync_file` handles both creating a new deck (file missing) and updating an
existing one. The two paths share fetch → diff → apply but diverge on the
prompt UX and on whether deckname / URL marker prompts run.
"""

from __future__ import annotations

import pytest

from cod_sync import cod, sourcetag
from cod_sync.cli.sync import _sync_file
from cod_sync.sources import RemoteDeck

URL = "https://www.moxfield.com/decks/abc123"
URL_OTHER = "https://archidekt.com/decks/999"


def _remote(zones, name="", tags=()):
    return RemoteDeck(name=name, zones=zones, tags=tuple(tags))


def _write_deck(path, deckname="", comments="", main=None, side=None, tags=()):
    zones = []
    if main:
        zones.append(
            cod.Zone(
                name="main", cards=tuple(cod.Card(name=n, quantity=q) for n, q in main.items())
            )
        )
    if side:
        zones.append(
            cod.Zone(
                name="side", cards=tuple(cod.Card(name=n, quantity=q) for n, q in side.items())
            )
        )
    deck = cod.Deck(
        deckname=deckname,
        comments=comments,
        zones=tuple(zones),
        tags_xml=cod.tags_list_to_xml(tuple(tags)),
    )
    cod.save(deck, str(path))


@pytest.fixture(autouse=True)
def _default_input(monkeypatch):
    """Default any input() to "y" — individual tests override as needed."""
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "y")


# ----- new file (formerly `import`) -----------------------------------------


def test_new_file_creates_with_remote_zones(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1, "Arcane Signet": 1}, "side": {}},
            name="Tester",
        ),
    )
    cod_path = tmp_path / "fresh.cod"
    rc = _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    assert cod_path.exists()
    deck = cod.load(str(cod_path))
    names = {c.name: c.quantity for c in deck.zone("main").cards}
    assert names == {"Sol Ring": 1, "Arcane Signet": 1}


def test_new_file_uses_remote_name_as_deckname(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="Atraxa Superfriends",
        ),
    )
    cod_path = tmp_path / "atraxa.cod"
    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    deck = cod.load(str(cod_path))
    assert deck.deckname == "Atraxa Superfriends"


def test_new_file_falls_back_to_stem_when_remote_unnamed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name=""),
    )
    cod_path = tmp_path / "my-deck.cod"
    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "my-deck"


def test_new_file_stores_url_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="x"),
    )
    cod_path = tmp_path / "deck.cod"
    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL


def test_new_file_with_text_source_does_not_store_marker(tmp_path, monkeypatch):
    text_path = tmp_path / "list.txt"
    text_path.write_text("4 Lightning Bolt\n", encoding="utf-8")
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Lightning Bolt": 4}, "side": {}}),
    )
    cod_path = tmp_path / "fromtxt.cod"
    _sync_file(str(cod_path), str(text_path), yes=True, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) is None


def test_new_file_empty_remote_does_not_write(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {}, "side": {}}, name="empty"),
    )
    cod_path = tmp_path / "empty.cod"
    rc = _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 0
    assert not cod_path.exists()
    assert "empty" in capsys.readouterr().out.lower()


def test_new_file_declined_prompt_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}),
    )
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")

    cod_path = tmp_path / "declined.cod"
    rc = _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert rc == 0
    assert not cod_path.exists()


def test_new_file_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}),
    )
    cod_path = tmp_path / "dry.cod"
    rc = _sync_file(str(cod_path), URL, yes=True, dry_run=True)

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
        "cod_sync.sources.fetch",
        lambda _src: RemoteDeck(name="DFC deck", zones=moxfield._parse(payload)),
    )
    cod_path = tmp_path / "dfc.cod"
    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    deck = cod.load(str(cod_path))
    assert {c.name for c in deck.zone("main").cards} == {"Storm the Vault"}


def test_fetch_failure_returns_error_for_new_file(tmp_path, monkeypatch, capsys):
    from cod_sync import errors

    def boom(_src):
        raise errors.DeckNotFoundError(URL)

    monkeypatch.setattr("cod_sync.sources.fetch", boom)
    cod_path = tmp_path / "broken.cod"
    rc = _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert rc == 2
    assert not cod_path.exists()
    err = capsys.readouterr().err
    assert "deck not found" in err
    assert "404" in err


# ----- existing file (formerly `sync`) --------------------------------------


def test_existing_file_no_url_uses_stored(tmp_path, monkeypatch):
    cod_path = tmp_path / "stored.cod"
    _write_deck(
        cod_path, deckname="Stored", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    captured = {}

    def fake_fetch(src):
        captured["src"] = src
        return _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Stored")

    monkeypatch.setattr("cod_sync.sources.fetch", fake_fetch)
    rc = _sync_file(str(cod_path), None, yes=True, dry_run=False)

    assert rc == 0
    assert captured["src"] == URL


def test_existing_file_no_url_and_no_stored_errors(tmp_path, capsys):
    cod_path = tmp_path / "lonely.cod"
    _write_deck(cod_path, deckname="Lonely", main={"Sol Ring": 1})

    rc = _sync_file(str(cod_path), None, yes=True, dry_run=False)

    assert rc == 2
    assert "no source URL" in capsys.readouterr().err


def test_existing_file_url_same_as_stored_keeps_marker(tmp_path, monkeypatch):
    cod_path = tmp_path / "match.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )

    # Track whether _confirm was called — it shouldn't be (no divergence).
    confirm_calls: list = []
    monkeypatch.setattr(
        "cod_sync.cli.prompts._confirm",
        lambda *a, **kw: confirm_calls.append((a, kw)) or False,
    )

    _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert confirm_calls == []
    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL


def test_existing_file_url_differs_decline_keeps_old(tmp_path, monkeypatch):
    cod_path = tmp_path / "diff.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )
    # Decline every confirm prompt.
    monkeypatch.setattr("cod_sync.cli.prompts._confirm", lambda *a, **kw: False)

    _sync_file(str(cod_path), URL_OTHER, yes=False, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL


def test_existing_file_url_differs_accept_overwrites(tmp_path, monkeypatch):
    cod_path = tmp_path / "diff.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )
    monkeypatch.setattr("cod_sync.cli.prompts._confirm", lambda *a, **kw: True)

    _sync_file(str(cod_path), URL_OTHER, yes=False, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL_OTHER


def test_existing_file_yes_flag_auto_updates_url(tmp_path, monkeypatch):
    cod_path = tmp_path / "yesurl.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )
    # No _confirm override — the real _confirm should auto-yes under yes=True.
    _sync_file(str(cod_path), URL_OTHER, yes=True, dry_run=False)

    assert sourcetag.get_source_url(cod.load(str(cod_path)).comments) == URL_OTHER


def test_existing_file_remote_name_matches_no_prompt(tmp_path, monkeypatch):
    cod_path = tmp_path / "named.cod"
    _write_deck(
        cod_path, deckname="Same Name", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Same Name"),
    )
    confirm_calls: list = []
    monkeypatch.setattr(
        "cod_sync.cli.prompts._confirm",
        lambda *a, **kw: confirm_calls.append((a, kw)) or False,
    )

    _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert confirm_calls == []
    assert cod.load(str(cod_path)).deckname == "Same Name"


def test_existing_file_remote_name_differs_decline_keeps_local(tmp_path, monkeypatch):
    cod_path = tmp_path / "rename.cod"
    _write_deck(
        cod_path, deckname="Local Name", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Remote Name"),
    )
    monkeypatch.setattr("cod_sync.cli.prompts._confirm", lambda *a, **kw: False)

    _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "Local Name"


def test_existing_file_remote_name_differs_accept_renames(tmp_path, monkeypatch):
    cod_path = tmp_path / "rename.cod"
    _write_deck(
        cod_path, deckname="Local Name", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Remote Name"),
    )
    monkeypatch.setattr("cod_sync.cli.prompts._confirm", lambda *a, **kw: True)

    _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "Remote Name"


def test_existing_file_yes_flag_auto_updates_deckname(tmp_path, monkeypatch):
    cod_path = tmp_path / "rename.cod"
    _write_deck(
        cod_path, deckname="Local Name", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Remote Name"),
    )

    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "Remote Name"


def test_existing_file_remote_name_casing_only_diff_no_prompt(tmp_path, monkeypatch):
    cod_path = tmp_path / "casing.cod"
    _write_deck(
        cod_path, deckname="Flip The Bird", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Flip the Bird"),
    )
    confirm_calls: list = []
    monkeypatch.setattr(
        "cod_sync.cli.prompts._confirm",
        lambda *a, **kw: confirm_calls.append((a, kw)) or False,
    )

    _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert confirm_calls == []
    assert cod.load(str(cod_path)).deckname == "Flip The Bird"


def test_existing_file_remote_name_whitespace_only_diff_no_prompt(tmp_path, monkeypatch):
    cod_path = tmp_path / "ws.cod"
    _write_deck(
        cod_path, deckname="Flip the Bird", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="  Flip the Bird "),
    )
    confirm_calls: list = []
    monkeypatch.setattr(
        "cod_sync.cli.prompts._confirm",
        lambda *a, **kw: confirm_calls.append((a, kw)) or False,
    )

    _sync_file(str(cod_path), URL, yes=False, dry_run=False)

    assert confirm_calls == []
    assert cod.load(str(cod_path)).deckname == "Flip the Bird"


def test_existing_file_remote_name_casing_only_diff_under_yes_keeps_local(tmp_path, monkeypatch):
    cod_path = tmp_path / "casing-yes.cod"
    _write_deck(
        cod_path, deckname="Flip The Bird", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1}
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="Flip the Bird"),
    )

    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.load(str(cod_path)).deckname == "Flip The Bird"


def test_existing_file_dry_run_writes_nothing(tmp_path, monkeypatch):
    cod_path = tmp_path / "dry-existing.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1})
    before = cod_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 2}, "side": {}}, name="X"),
    )

    rc = _sync_file(str(cod_path), URL, yes=True, dry_run=True)

    assert rc == 0
    assert cod_path.read_text(encoding="utf-8") == before


# ----- deck-level tag sync --------------------------------------------------


def test_existing_file_unions_remote_tags_into_local(tmp_path, monkeypatch):
    cod_path = tmp_path / "tags-union.cod"
    _write_deck(
        cod_path,
        deckname="X",
        comments=f"cod-sync-source: {URL}",
        main={"Sol Ring": 1},
        tags=("Budget", "Combo"),
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="X",
            tags=("Combo", "EDH"),
        ),
    )

    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.tags_xml_to_list(cod.load(str(cod_path)).tags_xml) == ("Budget", "Combo", "EDH")


def test_existing_file_tag_union_dedupes_case_insensitively(tmp_path, monkeypatch):
    cod_path = tmp_path / "tags-case.cod"
    _write_deck(
        cod_path,
        deckname="X",
        comments=f"cod-sync-source: {URL}",
        main={"Sol Ring": 1},
        tags=("Budget",),
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="X",
            tags=("budget", "Combo"),
        ),
    )

    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    # Local casing wins for the overlapping tag; new remote tag is appended.
    assert cod.tags_xml_to_list(cod.load(str(cod_path)).tags_xml) == ("Budget", "Combo")


def test_existing_file_tag_subset_does_not_rewrite(tmp_path, monkeypatch):
    cod_path = tmp_path / "tags-noop.cod"
    _write_deck(
        cod_path,
        deckname="X",
        comments=f"cod-sync-source: {URL}",
        main={"Sol Ring": 1},
        tags=("Budget", "Combo"),
    )
    before = cod_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="X",
            tags=("Combo",),
        ),
    )

    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod_path.read_text(encoding="utf-8") == before


def test_existing_file_no_remote_tags_leaves_local_untouched(tmp_path, monkeypatch):
    cod_path = tmp_path / "tags-localonly.cod"
    _write_deck(
        cod_path,
        deckname="X",
        comments=f"cod-sync-source: {URL}",
        main={"Sol Ring": 1},
        tags=("Budget",),
    )

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote({"main": {"Sol Ring": 1}, "side": {}}, name="X"),
    )

    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.tags_xml_to_list(cod.load(str(cod_path)).tags_xml) == ("Budget",)


def test_existing_file_remote_tags_only_still_triggers_write(tmp_path, monkeypatch):
    """Local card list matches remote, but remote brings new tags. The file
    must be rewritten because the diff in tag set is itself a change."""
    cod_path = tmp_path / "tags-only.cod"
    _write_deck(cod_path, deckname="X", comments=f"cod-sync-source: {URL}", main={"Sol Ring": 1})

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="X",
            tags=("Budget",),
        ),
    )

    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.tags_xml_to_list(cod.load(str(cod_path)).tags_xml) == ("Budget",)


def test_new_file_uses_remote_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="Imported",
            tags=("EDH", "Budget"),
        ),
    )
    cod_path = tmp_path / "fresh-tags.cod"
    _sync_file(str(cod_path), URL, yes=True, dry_run=False)

    assert cod.tags_xml_to_list(cod.load(str(cod_path)).tags_xml) == ("EDH", "Budget")


def test_existing_file_dry_run_does_not_apply_tag_union(tmp_path, monkeypatch):
    cod_path = tmp_path / "tags-dry.cod"
    _write_deck(
        cod_path,
        deckname="X",
        comments=f"cod-sync-source: {URL}",
        main={"Sol Ring": 1},
        tags=("Budget",),
    )
    before = cod_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        "cod_sync.sources.fetch",
        lambda _src: _remote(
            {"main": {"Sol Ring": 1}, "side": {}},
            name="X",
            tags=("Combo",),
        ),
    )

    rc = _sync_file(str(cod_path), URL, yes=True, dry_run=True)

    assert rc == 0
    assert cod_path.read_text(encoding="utf-8") == before
