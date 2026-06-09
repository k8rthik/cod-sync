"""Pure deck-mutation logic.

No I/O, no prompts, no module-level state. Given a deck and a list of
diff changes, return the new deck. Tested directly by
``tests/test_multi_printing.py``.
"""
from __future__ import annotations

from cod_sync import cod, diff


def _build_new_deck(deckname: str, remote: dict[str, dict[str, int]]) -> cod.Deck:
    zones: list[cod.Zone] = []
    for zone_name in ("main", "side"):
        entries = remote.get(zone_name, {})
        if not entries:
            continue
        cards = tuple(
            cod.Card(name=name, quantity=qty)
            for name, qty in sorted(entries.items(), key=lambda kv: kv[0].lower())
        )
        zones.append(cod.Zone(name=zone_name, cards=cards))
    return cod.Deck(deckname=deckname, zones=tuple(zones))


def _import_preview_changes(remote: dict[str, dict[str, int]]) -> list[diff.Change]:
    changes: list[diff.Change] = []
    for zone_name in ("main", "side"):
        entries = remote.get(zone_name, {})
        for name in sorted(entries, key=str.lower):
            changes.append(diff.Change("add", zone_name, name, 0, entries[name]))
    return changes


def _apply(deck: cod.Deck, changes: list[diff.Change]) -> cod.Deck:
    """Apply changes to the deck, preserving printing pins on untouched cards.

    Handles multi-printing entries (same card name listed multiple times
    with different setShortName/uuid):
      - remove: drop every entry with the name
      - qty increase: bump the single entry if there's one; otherwise append
        a new bare entry with the delta so existing printings stay intact
      - qty decrease: reduce from the END (last-added printings first),
        dropping entries that hit zero
    """
    new_zones: list[cod.Zone] = list(deck.zones)

    by_zone: dict[str, list[diff.Change]] = {}
    for c in changes:
        by_zone.setdefault(c.zone, []).append(c)

    for zone_name, zone_changes in by_zone.items():
        zone = _get_or_create_zone(new_zones, zone_name)
        next_cards = _apply_zone(list(zone.cards), zone_changes)
        new_zone = zone.with_cards(tuple(next_cards))
        idx = next(i for i, z in enumerate(new_zones) if z.name == zone_name)
        new_zones[idx] = new_zone

    return deck.with_zones(tuple(new_zones))


def _apply_zone(cards: list[cod.Card], zone_changes: list[diff.Change]) -> list[cod.Card]:
    removes = {c.name for c in zone_changes if c.kind == "remove"}
    qty_updates = {c.name: c.remote_qty for c in zone_changes if c.kind == "qty"}
    adds = [c for c in zone_changes if c.kind == "add"]

    indices_by_name: dict[str, list[int]] = {}
    for i, card in enumerate(cards):
        indices_by_name.setdefault(card.name, []).append(i)

    drop: set[int] = set()
    new_qty: dict[int, int] = {}
    extra_appends: list[cod.Card] = []

    for name in removes:
        drop.update(indices_by_name.get(name, []))

    for name, target in qty_updates.items():
        indices = indices_by_name.get(name, [])
        current_total = sum(cards[i].quantity for i in indices)
        if target == current_total:
            continue
        if target > current_total:
            delta = target - current_total
            if len(indices) == 1:
                new_qty[indices[0]] = cards[indices[0]].quantity + delta
            else:
                extra_appends.append(cod.Card(name=name, quantity=delta))
        else:
            shortfall = current_total - target
            for i in reversed(indices):
                if shortfall <= 0:
                    break
                cur = cards[i].quantity
                if cur <= shortfall:
                    drop.add(i)
                    shortfall -= cur
                else:
                    new_qty[i] = cur - shortfall
                    shortfall = 0

    next_cards: list[cod.Card] = []
    for i, card in enumerate(cards):
        if i in drop:
            continue
        if i in new_qty:
            next_cards.append(card.with_quantity(new_qty[i]))
        else:
            next_cards.append(card)

    for c in adds:
        next_cards.append(cod.Card(name=c.name, quantity=c.remote_qty))
    next_cards.extend(extra_appends)

    return next_cards


def _get_or_create_zone(zones: list[cod.Zone], name: str) -> cod.Zone:
    for z in zones:
        if z.name == name:
            return z
    new = cod.Zone(name=name)
    zones.append(new)
    return new
