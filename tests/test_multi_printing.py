"""Coverage for the multi-printing bug: a card listed as several <card> lines
with different printing pins (e.g. 9 Nazgûl, each its own uuid) must be
treated as one logical card by both diff and apply."""
from cod_sync import cod, diff
from cod_sync.cli import _apply


def _deck_with_nazgul_printings(n: int) -> cod.Deck:
    cards = tuple(
        cod.Card(
            name="Nazgûl",
            quantity=1,
            set_short_name="LTR",
            collector_number=str(331 + i),
            uuid=f"uuid-{i}",
        )
        for i in range(n)
    )
    return cod.Deck(zones=(cod.Zone(name="main", cards=cards),))


def test_diff_sums_multi_printing_quantities():
    deck = _deck_with_nazgul_printings(9)
    remote = {"main": {"Nazgûl": 9}, "side": {}}
    assert diff.compute(deck, remote) == []


def test_diff_emits_qty_change_against_total():
    deck = _deck_with_nazgul_printings(9)
    remote = {"main": {"Nazgûl": 10}, "side": {}}
    changes = diff.compute(deck, remote)
    assert len(changes) == 1
    assert changes[0].kind == "qty"
    assert changes[0].local_qty == 9
    assert changes[0].remote_qty == 10


def test_apply_qty_increase_on_multi_printing_appends_bare_entry():
    deck = _deck_with_nazgul_printings(9)
    changes = [diff.Change("qty", "main", "Nazgûl", 9, 10)]
    new_deck = _apply(deck, changes)
    main = new_deck.zone("main")
    assert len(main.cards) == 10
    # First 9 untouched — printing pins preserved
    for original, current in zip(deck.zone("main").cards, main.cards[:9]):
        assert current == original
    # Tenth is the bare append
    extra = main.cards[9]
    assert extra.name == "Nazgûl"
    assert extra.quantity == 1
    assert extra.set_short_name is None
    assert extra.uuid is None


def test_apply_qty_decrease_drops_from_end():
    deck = _deck_with_nazgul_printings(9)
    changes = [diff.Change("qty", "main", "Nazgûl", 9, 5)]
    new_deck = _apply(deck, changes)
    main = new_deck.zone("main")
    assert len(main.cards) == 5
    # First 5 kept; last 4 (most recently added printings) dropped
    for original, current in zip(deck.zone("main").cards[:5], main.cards):
        assert current == original


def test_apply_qty_decrease_partial_on_last_entry():
    # 3 entries of qty 4 each = 12 total. Target 10 → drop nothing, reduce
    # last entry from 4 to 2.
    cards = tuple(
        cod.Card(name="Treasure Token", quantity=4, set_short_name="X", collector_number=str(i), uuid=f"u{i}")
        for i in range(3)
    )
    deck = cod.Deck(zones=(cod.Zone(name="main", cards=cards),))
    changes = [diff.Change("qty", "main", "Treasure Token", 12, 10)]
    new_deck = _apply(deck, changes)
    main = new_deck.zone("main")
    assert len(main.cards) == 3
    assert main.cards[0].quantity == 4
    assert main.cards[1].quantity == 4
    assert main.cards[2].quantity == 2
    assert main.cards[2].uuid == "u2"


def test_apply_remove_drops_all_printings():
    deck = _deck_with_nazgul_printings(9)
    changes = [diff.Change("remove", "main", "Nazgûl", 9, 0)]
    new_deck = _apply(deck, changes)
    assert new_deck.zone("main").cards == ()


def test_apply_qty_increase_on_single_entry_bumps_in_place():
    """Single-entry case still works: bump qty on the existing card, preserve pins."""
    card = cod.Card(name="Forest", quantity=10, set_short_name="LEA", collector_number="1", uuid="x")
    deck = cod.Deck(zones=(cod.Zone(name="main", cards=(card,)),))
    changes = [diff.Change("qty", "main", "Forest", 10, 11)]
    new_deck = _apply(deck, changes)
    main = new_deck.zone("main")
    assert len(main.cards) == 1
    assert main.cards[0].quantity == 11
    assert main.cards[0].set_short_name == "LEA"
    assert main.cards[0].uuid == "x"
