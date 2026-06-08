from cod_sync import cod, diff


def _deck(main: dict[str, int], side: dict[str, int] | None = None) -> cod.Deck:
    zones = [cod.Zone(name="main", cards=tuple(cod.Card(n, q) for n, q in main.items()))]
    if side:
        zones.append(cod.Zone(name="side", cards=tuple(cod.Card(n, q) for n, q in side.items())))
    return cod.Deck(zones=tuple(zones))


def test_no_changes():
    deck = _deck({"Sol Ring": 1, "Forest": 10})
    remote = {"main": {"Sol Ring": 1, "Forest": 10}, "side": {}}
    assert diff.compute(deck, remote) == []


def test_add_remove_and_qty():
    deck = _deck({"Sol Ring": 1, "Forest": 10, "Gamble": 1})
    remote = {"main": {"Sol Ring": 1, "Forest": 11, "Black Lotus": 1}, "side": {}}
    changes = diff.compute(deck, remote)
    kinds = [(c.kind, c.name) for c in changes]
    assert ("add", "Black Lotus") in kinds
    assert ("remove", "Gamble") in kinds
    assert ("qty", "Forest") in kinds
    assert ("add" if False else "qty", "Sol Ring") not in kinds


def test_side_zone_changes_tracked_separately():
    deck = _deck({"Sol Ring": 1}, side={"Pithing Needle": 1})
    remote = {"main": {"Sol Ring": 1}, "side": {}}
    changes = diff.compute(deck, remote)
    assert len(changes) == 1
    assert changes[0].zone == "side"
    assert changes[0].kind == "remove"
    assert changes[0].name == "Pithing Needle"


def test_changes_sorted_case_insensitive():
    deck = _deck({})
    remote = {"main": {"banana": 1, "Apple": 1, "cherry": 1}, "side": {}}
    names = [c.name for c in diff.compute(deck, remote)]
    assert names == ["Apple", "banana", "cherry"]


def test_dfc_matches_front_only_local_name():
    """Remote returns 'Front // Back'; local has just 'Front'. No diff."""
    deck = _deck({"Bala Ged Recovery": 1})
    remote = {"main": {"Bala Ged Recovery // Bala Ged Sanctuary": 1}, "side": {}}
    assert diff.compute(deck, remote) == []


def test_dfc_full_form_match_when_local_has_full_form():
    """Both sides use the full form: still no diff."""
    deck = _deck({"Dusk // Dawn": 1})
    remote = {"main": {"Dusk // Dawn": 1}, "side": {}}
    assert diff.compute(deck, remote) == []


def test_dfc_quantity_change_works_with_short_local_name():
    deck = _deck({"Bala Ged Recovery": 1})
    remote = {"main": {"Bala Ged Recovery // Bala Ged Sanctuary": 2}, "side": {}}
    changes = diff.compute(deck, remote)
    assert len(changes) == 1
    assert changes[0].kind == "qty"
    assert changes[0].name == "Bala Ged Recovery"
    assert changes[0].remote_qty == 2


def test_dfc_new_card_uses_front_face_only():
    """A brand-new DFC is added under the front face name so Cockatrice's card
    database can find it. The "// Back" portion is stripped on add."""
    deck = _deck({})
    remote = {"main": {"Fable of the Mirror-Breaker // Reflection of Kiki-Jiki": 1}, "side": {}}
    changes = diff.compute(deck, remote)
    assert len(changes) == 1
    assert changes[0].kind == "add"
    assert changes[0].name == "Fable of the Mirror-Breaker"


def test_dfc_local_full_form_is_healed_to_remote_front_face():
    """Local stores a stale "Front // Back" entry (written before the v0.8.0
    alt_name fix); remote sends the front face only. Cockatrice cannot read
    the full form, so the diff must surface the stale entry as a remove and
    the correct entry as an add, letting the user heal the file on next sync.
    """
    deck = _deck({"Bala Ged Recovery // Bala Ged Sanctuary": 1})
    remote = {"main": {"Bala Ged Recovery": 1}, "side": {}}
    changes = diff.compute(deck, remote)
    assert len(changes) == 2
    by_kind = {(c.kind, c.name): c for c in changes}
    remove = by_kind[("remove", "Bala Ged Recovery // Bala Ged Sanctuary")]
    add = by_kind[("add", "Bala Ged Recovery")]
    assert remove.local_qty == 1
    assert add.remote_qty == 1


def test_dfc_local_full_form_with_qty_change_is_healed():
    """Heal also resets quantity. Local has 1 under the stale full key,
    remote wants 3 under the front face — emit a remove of the full form
    at qty 1 and an add of the front face at qty 3.
    """
    deck = _deck({"Bala Ged Recovery // Bala Ged Sanctuary": 1})
    remote = {"main": {"Bala Ged Recovery": 3}, "side": {}}
    changes = diff.compute(deck, remote)
    assert len(changes) == 2
    by_kind = {(c.kind, c.name): c for c in changes}
    remove = by_kind[("remove", "Bala Ged Recovery // Bala Ged Sanctuary")]
    add = by_kind[("add", "Bala Ged Recovery")]
    assert remove.local_qty == 1
    assert add.remote_qty == 3
