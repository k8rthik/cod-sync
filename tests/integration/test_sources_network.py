"""Real-network integration tests for the Moxfield and Archidekt sources.

These are the only tests in the repo that make live HTTP requests. They
are gated behind COD_SYNC_RUN_NETWORK_TESTS=1 (wired in tests/conftest.py)
so the default `pytest -q` stays offline and fast.

Why they exist
--------------
Every other source test in this repo uses a hand-crafted JSON payload.
If Moxfield or Archidekt change their response shape (rename a key,
restructure a board, start gating with an API key), every offline test
keeps passing while every user breaks. These tests catch that class of
regression by exercising the live API and comparing what came back
against properties of a known Wizards-published Commander precon.

Why this specific deck
----------------------
Quandrix Unlimited - Secrets of Strixhaven. Both URLs point to copies
of the same deck on each platform; that lets us assert not just that
each source parses something sensible, but that both sources produce
the *same* normalized deck. Per-source regressions (one source's DFC
handling drifts, one source's commander routing breaks) surface as a
diff between the two zone dicts — something two independent per-source
tests would silently agree on.

If either URL goes dead, the replacement must be another copy of the
*same* deck on that platform. The parity assertion depends on that.
The invariants below were verified against the Archidekt copy at the
time of writing; if the deck owner edits the list materially, update
the invariants block (not the assertion bodies).
"""

from __future__ import annotations

import pytest

from cod_sync import sources
from cod_sync.sources import RemoteDeck

_MOXFIELD_URL = "https://moxfield.com/decks/gGtJmNlez06i3p6Kved35g"
_ARCHIDEKT_URL = "https://archidekt.com/decks/21319716/quandrix_unlimited_secrets_of_strixhaven"

# Invariants of the deck both URLs point to. These were verified by
# fetching the Archidekt copy directly; the Moxfield copy is asserted
# to match via the parity test.
_EXPECTED_TOTAL_CARDS = 100
_EXPECTED_COMMANDER = "Zimone, Infinite Analyst"
_EXPECTED_COMMANDER_QTY = 1

# Mainboard anchors that should be present and stable. Sol Ring,
# Command Tower, and Arcane Signet are universal commander staples —
# their removal from a Commander precon would be itself notable. The
# anchor set is intentionally small so a future deck edit that swaps
# any one specific card doesn't take everything down with it.
_EXPECTED_MAIN_ANCHORS = frozenset({"Sol Ring", "Command Tower", "Arcane Signet"})


@pytest.fixture(scope="session")
def moxfield_deck() -> RemoteDeck:
    return sources.fetch(_MOXFIELD_URL)


@pytest.fixture(scope="session")
def archidekt_deck() -> RemoteDeck:
    return sources.fetch(_ARCHIDEKT_URL)


def _assert_basic_shape(deck) -> None:
    """Properties any well-formed RemoteDeck must satisfy."""
    assert isinstance(deck, RemoteDeck)
    assert isinstance(deck.name, str)
    assert "main" in deck.zones
    assert "side" in deck.zones
    assert deck.zones["main"], "mainboard should not be empty"
    for zone_name, cards in deck.zones.items():
        for card_name, qty in cards.items():
            assert isinstance(card_name, str) and card_name, f"empty card name in zone {zone_name}"
            assert isinstance(qty, int) and qty > 0, (
                f"non-positive qty for {card_name!r} in zone {zone_name}: {qty!r}"
            )


def _assert_precon_invariants(deck) -> None:
    """Properties specific to the Quandrix Unlimited deck."""
    main = deck.zones["main"]
    side = deck.zones["side"]

    total = sum(main.values()) + sum(side.values())
    assert total == _EXPECTED_TOTAL_CARDS, (
        f"expected {_EXPECTED_TOTAL_CARDS} total cards, got {total}"
    )

    assert sum(side.values()) == _EXPECTED_COMMANDER_QTY, (
        f"expected exactly {_EXPECTED_COMMANDER_QTY} card(s) in side (commander zone), "
        f"got {sum(side.values())}: {dict(side)!r}"
    )
    assert side.get(_EXPECTED_COMMANDER) == 1, (
        f"expected commander {_EXPECTED_COMMANDER!r} with qty 1 in side, got side={dict(side)!r}"
    )

    missing = _EXPECTED_MAIN_ANCHORS - main.keys()
    assert not missing, f"mainboard missing expected anchor cards: {missing}"

    # Layout-aware shaping: the Quandrix deck contains an adventure card
    # and two prepare cards, which Cockatrice stores under the full
    # "A // B" name (the front-face-only entries don't exist in its
    # database). A regression toward blanket front-face stripping would
    # surface as these keys going missing.
    full_name_cards = {
        "Elusive Otter // Grove's Bounty",  # adventure
        "Striding Shotcaller // Run the Play",  # prepare
        "Yavimaya Bloomsage // Channel",  # prepare
    }
    missing_full = full_name_cards - main.keys()
    assert not missing_full, (
        f"adventure/prepare cards should keep their full names, missing: {missing_full}"
    )

    # And the inverse: no name outside the known full-name set should
    # round-trip as "Front // Back" — a true DFC leaking its back face
    # would show up here.
    dfc_residue = [
        name
        for cards in deck.zones.values()
        for name in cards
        if " // " in name and name not in full_name_cards
    ]
    assert not dfc_residue, f"unexpected full-form names (DFC back-face leak?): {dfc_residue}"


@pytest.mark.network
def test_moxfield_quandrix_fetch(moxfield_deck) -> None:
    _assert_basic_shape(moxfield_deck)
    _assert_precon_invariants(moxfield_deck)


@pytest.mark.network
def test_archidekt_quandrix_fetch(archidekt_deck) -> None:
    _assert_basic_shape(archidekt_deck)
    _assert_precon_invariants(archidekt_deck)


@pytest.mark.network
def test_sources_agree_on_quandrix(moxfield_deck, archidekt_deck) -> None:
    """Cross-source parity check.

    Both URLs point to the same deck. After source-specific parsing,
    DFC normalization, zone routing, and alt-name canonicalization,
    the two RemoteDecks should have identical zone dicts. If they
    diverge, exactly one source has drifted — and the diff in the
    failure message names which cards moved or which zone they ended
    up in.

    Deck names are uploader-controlled and may legitimately differ
    between platforms; we don't compare them.
    """
    assert moxfield_deck.zones == archidekt_deck.zones, (
        "Moxfield and Archidekt parsed the same deck differently.\n"
        f"  only in Moxfield main: "
        f"{set(moxfield_deck.zones['main']) - set(archidekt_deck.zones['main'])}\n"
        f"  only in Archidekt main: "
        f"{set(archidekt_deck.zones['main']) - set(moxfield_deck.zones['main'])}\n"
        f"  only in Moxfield side: "
        f"{set(moxfield_deck.zones['side']) - set(archidekt_deck.zones['side'])}\n"
        f"  only in Archidekt side: "
        f"{set(archidekt_deck.zones['side']) - set(moxfield_deck.zones['side'])}\n"
    )
