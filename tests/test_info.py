"""Tests for `cod-sync FILE --info`."""
from __future__ import annotations

import re

import pytest

from cod_sync import cli, cod


URL = "https://www.moxfield.com/decks/abc123"
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def _write_deck(
    path,
    deckname="Test Deck",
    format_="commander",
    comments="",
    main=None,
    side=None,
    banner_card_name=None,
    pinned_set=None,
):
    """Build and save a minimal Deck for testing. `pinned_set` flags some
    cards with a setShortName so we can verify pin-count reporting."""
    def _mk_cards(entries):
        cards = []
        for name, qty in entries.items():
            cards.append(cod.Card(
                name=name,
                quantity=qty,
                set_short_name=pinned_set if pinned_set else None,
            ))
        return tuple(cards)

    zones = []
    if main:
        zones.append(cod.Zone(name="main", cards=_mk_cards(main)))
    if side:
        zones.append(cod.Zone(name="side", cards=_mk_cards(side)))
    deck = cod.Deck(
        deckname=deckname,
        format=format_,
        comments=comments,
        zones=tuple(zones),
        banner_card_name=banner_card_name,
    )
    cod.save(deck, str(path))


def test_info_shows_deckname_and_format(tmp_path, capsys):
    cod_path = tmp_path / "named.cod"
    _write_deck(cod_path, deckname="My EDH Pile", format_="commander",
                main={"Sol Ring": 1})

    rc = cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert rc == 0
    assert "My EDH Pile" in out
    assert "format: commander" in out


def test_info_shows_unnamed_deck_marker(tmp_path, capsys):
    cod_path = tmp_path / "blank.cod"
    _write_deck(cod_path, deckname="", main={"Sol Ring": 1})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert "(unnamed deck)" in out


def test_info_shows_stored_source_url(tmp_path, capsys):
    cod_path = tmp_path / "withurl.cod"
    _write_deck(cod_path, comments=f"cod-sync-source: {URL}",
                main={"Sol Ring": 1})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert f"source: {URL}" in out


def test_info_shows_no_stored_url_marker(tmp_path, capsys):
    cod_path = tmp_path / "nourl.cod"
    _write_deck(cod_path, main={"Sol Ring": 1})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert "(none stored)" in out


def test_info_shows_banner_when_set(tmp_path, capsys):
    cod_path = tmp_path / "withbanner.cod"
    _write_deck(cod_path, banner_card_name="Atraxa, Praetors' Voice",
                main={"Sol Ring": 1})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert "banner: Atraxa, Praetors' Voice" in out


def test_info_omits_banner_when_absent(tmp_path, capsys):
    cod_path = tmp_path / "nobanner.cod"
    _write_deck(cod_path, banner_card_name=None, main={"Sol Ring": 1})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert "banner:" not in out


def test_info_zone_counts(tmp_path, capsys):
    cod_path = tmp_path / "counts.cod"
    _write_deck(cod_path, main={"Sol Ring": 1, "Forest": 10, "Lightning Bolt": 4})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    # Main: 15 cards (1 + 10 + 4), 3 unique
    assert "[main] 15 cards · 3 unique" in out


def test_info_lists_cards_alphabetically(tmp_path, capsys):
    cod_path = tmp_path / "alpha.cod"
    _write_deck(cod_path, main={"Sol Ring": 1, "Arcane Signet": 1, "Forest": 10})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    # Locate the listing in the output and verify the order.
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    cards_in_order = [l for l in lines if l.endswith("Forest") or l.endswith("Sol Ring") or l.endswith("Arcane Signet")]
    assert cards_in_order == ["1 Arcane Signet", "10 Forest", "1 Sol Ring"]


def test_info_shows_total_across_zones(tmp_path, capsys):
    cod_path = tmp_path / "totals.cod"
    _write_deck(cod_path, main={"Sol Ring": 1, "Forest": 10},
                side={"Pyroblast": 2})

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert "[main] 11 cards" in out
    assert "[side] 2 cards" in out
    assert "total: 13 cards" in out


def test_info_handles_empty_deck(tmp_path, capsys):
    cod_path = tmp_path / "empty.cod"
    _write_deck(cod_path)

    rc = cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    assert rc == 0
    assert "(empty deck)" in out
    assert "total: 0 cards" in out


def test_info_pin_count_reflects_set_short_name(tmp_path, capsys):
    cod_path = tmp_path / "pinned.cod"
    _write_deck(cod_path, main={"Sol Ring": 1, "Forest": 5}, pinned_set="LCI")

    cli._show_info(str(cod_path))
    out = _plain(capsys.readouterr().out)

    # 6 cards total, all pinned
    assert "[main] 6 cards · 2 unique · 6 pinned" in out


def test_info_rolls_up_multi_printing_entries(tmp_path):
    """A deck with multiple <card name="Nazgul"> entries (different printings)
    rolls up to one line per name with the summed quantity."""
    cards = (
        cod.Card(name="Nazgûl", quantity=1, set_short_name="LTR"),
        cod.Card(name="Nazgûl", quantity=1, set_short_name="ME4"),
        cod.Card(name="Nazgûl", quantity=2, set_short_name="LTC"),
    )
    deck = cod.Deck(deckname="Nazgul Tribal", zones=(cod.Zone(name="main", cards=cards),))
    path = tmp_path / "naz.cod"
    cod.save(deck, str(path))

    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli._show_info(str(path))
    out = _plain(buf.getvalue())

    assert "4 Nazgûl" in out
    assert "[main] 4 cards · 1 unique · 4 pinned" in out


# ----- routing checks --------------------------------------------------------


def test_main_dispatches_info_to_show_info(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_deck(tmp_path / "x.cod", main={"Sol Ring": 1})

    called: list = []
    monkeypatch.setattr("cod_sync.cli._show_info",
                        lambda p: called.append(p) or 0)

    rc = cli.main(["x.cod", "--info"])

    assert rc == 0
    assert called == ["x.cod"]


def test_info_short_flag_dispatches_too(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_deck(tmp_path / "x.cod", main={"Sol Ring": 1})

    called: list = []
    monkeypatch.setattr("cod_sync.cli._show_info",
                        lambda p: called.append(p) or 0)

    cli.main(["x.cod", "-i"])

    assert called == ["x.cod"]


def test_info_resolves_cod_suffix(tmp_path, monkeypatch):
    """Bare 'x' should resolve to 'x.cod' before dispatch."""
    monkeypatch.chdir(tmp_path)
    _write_deck(tmp_path / "x.cod", main={"Sol Ring": 1})

    called: list = []
    monkeypatch.setattr("cod_sync.cli._show_info",
                        lambda p: called.append(p) or 0)

    cli.main(["x", "-i"])

    assert called == ["x.cod"]


def test_info_without_target_errors(capsys):
    rc = cli.main(["--info"])
    assert rc == 2
    assert "needs a deck file" in capsys.readouterr().err


def test_info_with_url_target_errors(capsys):
    rc = cli.main([URL, "--info"])
    assert rc == 2
    assert "not a URL" in capsys.readouterr().err


def test_info_with_directory_errors(tmp_path, capsys):
    rc = cli.main([str(tmp_path), "--info"])
    assert rc == 2
    assert "not a directory" in capsys.readouterr().err


def test_info_with_url_arg_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _write_deck(tmp_path / "x.cod", main={"Sol Ring": 1})

    rc = cli.main(["x.cod", URL, "--info"])
    assert rc == 2
    assert "doesn't take a URL" in capsys.readouterr().err


def test_info_missing_file_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["nope.cod", "--info"])
    assert rc == 2
    assert "not found" in capsys.readouterr().err
