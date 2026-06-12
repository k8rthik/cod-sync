"""In-flow alt-name mapping visibility and control.

`sources.fetch` reports applied (non-identity) mappings on
`RemoteDeck.renames`; `cli.sync._apply_mapping_control` logs every
mapping and prompts once for each unsettled one — accept, keep the
original printed name, or type a replacement — persisting the answer
to the disk cache so the same name never prompts again.
"""

from __future__ import annotations

from cod_sync import alt_name, sources
from cod_sync.cli.sync import _apply_mapping_control
from cod_sync.sources import RemoteDeck
from cod_sync.sources.types import AppliedRename

FLAVOR = "Unstable Harmonics"
CANONICAL = "Rhystic Study"


def _reskin_remote(qty=1, extra_canonical=0):
    main = {CANONICAL: qty + extra_canonical}
    return RemoteDeck(
        name="d",
        zones={"main": main, "side": {}},
        renames=(AppliedRename("main", FLAVOR, CANONICAL, qty, settled=False),),
    )


def _input_seq(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(it))


def _boom_input(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("input() must not be called")

    monkeypatch.setattr("builtins.input", boom)


# ----- renames are reported by the fetch pipeline ----------------------------


def test_fetch_reports_applied_renames(monkeypatch):
    raw = RemoteDeck(name="d", zones={"main": {FLAVOR: 2, "Sol Ring": 1}, "side": {}})
    monkeypatch.setattr("cod_sync.sources._fetch_raw", lambda _s: raw)

    deck = sources.fetch("https://www.moxfield.com/decks/x")

    assert deck.zones["main"] == {CANONICAL: 2, "Sol Ring": 1}
    assert deck.renames == (AppliedRename("main", FLAVOR, CANONICAL, 2, settled=False),)


def test_fetch_reports_no_renames_for_identity(monkeypatch):
    raw = RemoteDeck(name="d", zones={"main": {"Sol Ring": 1}, "side": {}})
    monkeypatch.setattr("cod_sync.sources._fetch_raw", lambda _s: raw)

    deck = sources.fetch("https://www.moxfield.com/decks/x")

    assert deck.renames == ()


# ----- interactive control ----------------------------------------------------


def test_accept_keeps_canonical_and_settles(monkeypatch, capsys):
    _input_seq(monkeypatch, ["y"])

    out = _apply_mapping_control(_reskin_remote(), yes=False, dry_run=False)

    assert out.zones["main"] == {CANONICAL: 1}
    assert alt_name.canonicalize_batch_detailed([FLAVOR])[FLAVOR].settled is True
    assert FLAVOR in capsys.readouterr().out


def test_keep_original_remaps_zone_and_caches_identity(monkeypatch):
    _input_seq(monkeypatch, ["n"])

    out = _apply_mapping_control(_reskin_remote(), yes=False, dry_run=False)

    assert out.zones["main"] == {FLAVOR: 1}
    assert alt_name.canonicalize(FLAVOR) == FLAVOR


def test_edit_remaps_zone_to_typed_name(monkeypatch):
    _input_seq(monkeypatch, ["e", "My Custom Name"])

    out = _apply_mapping_control(_reskin_remote(), yes=False, dry_run=False)

    assert out.zones["main"] == {"My Custom Name": 1}
    assert alt_name.canonicalize(FLAVOR) == "My Custom Name"


def test_keep_original_unmerges_only_the_renamed_quantity(monkeypatch):
    """A deck holding both the reskin and the literal canonical only moves
    the reskin's quantity back when the mapping is declined."""
    _input_seq(monkeypatch, ["n"])

    out = _apply_mapping_control(_reskin_remote(qty=1, extra_canonical=2), yes=False, dry_run=False)

    assert out.zones["main"] == {CANONICAL: 2, FLAVOR: 1}


def test_yes_mode_settles_without_prompting(monkeypatch):
    _boom_input(monkeypatch)

    out = _apply_mapping_control(_reskin_remote(), yes=True, dry_run=False)

    assert out.zones["main"] == {CANONICAL: 1}
    assert alt_name.canonicalize_batch_detailed([FLAVOR])[FLAVOR].settled is True


def test_settled_mapping_logs_without_prompting(monkeypatch, capsys):
    alt_name.set_override(FLAVOR, CANONICAL)
    _boom_input(monkeypatch)
    remote = RemoteDeck(
        name="d",
        zones={"main": {CANONICAL: 1}, "side": {}},
        renames=(AppliedRename("main", FLAVOR, CANONICAL, 1, settled=True),),
    )

    out = _apply_mapping_control(remote, yes=False, dry_run=False)

    assert out.zones["main"] == {CANONICAL: 1}
    assert FLAVOR in capsys.readouterr().out


def test_dry_run_logs_but_never_prompts_or_writes(monkeypatch, capsys):
    _boom_input(monkeypatch)

    out = _apply_mapping_control(_reskin_remote(), yes=False, dry_run=True)

    assert out.zones["main"] == {CANONICAL: 1}
    assert alt_name.canonicalize_batch_detailed([FLAVOR])[FLAVOR].settled is False
    assert FLAVOR in capsys.readouterr().out


def test_no_renames_is_a_no_op(monkeypatch):
    _boom_input(monkeypatch)
    remote = RemoteDeck(name="d", zones={"main": {"Sol Ring": 1}, "side": {}})

    assert _apply_mapping_control(remote, yes=False, dry_run=False) is remote
