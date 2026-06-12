"""Diff a local Cockatrice deck against a normalized remote decklist.

Card names are compared verbatim: the source fetchers and the alt_name
layer deliver remote names already in Cockatrice's database form, and
this layer never reshapes them. A stale name shape in the local file
surfaces as a remove + add pair, which heals the file on the next sync.
See ARCHITECTURE.md ("Card name shaping").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cod_sync.cod import Deck

ChangeKind = Literal["add", "remove", "qty"]


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    zone: str  # "main" | "side"
    name: str
    local_qty: int  # current quantity in the .cod (0 if absent)
    remote_qty: int  # quantity in the remote source (0 if absent)

    def describe(self) -> str:
        if self.kind == "add":
            return f"+ {self.remote_qty}x {self.name}"
        if self.kind == "remove":
            return f"- {self.local_qty}x {self.name}"
        return f"~ {self.local_qty} → {self.remote_qty}x {self.name}"


def total_card_delta(changes: list[Change]) -> int:
    """Total number of cards touched — a `+ 4x Forest` line counts as 4.

    User-facing counts (the summary header, the "Wrote N change(s)" line)
    promise cards, not unique-name lines; quantity bumps count the delta.
    """
    return sum(abs(c.remote_qty - c.local_qty) for c in changes)


def compute(deck: Deck, remote: dict[str, dict[str, int]]) -> list[Change]:
    """Return the ordered list of changes needed to make `deck` match `remote`."""
    changes: list[Change] = []
    for zone_name in ("main", "side"):
        local = _zone_to_dict(deck, zone_name)
        remote_zone = remote.get(zone_name, {})
        all_names = sorted(set(local) | set(remote_zone), key=str.lower)
        for name in all_names:
            lq = local.get(name, 0)
            rq = remote_zone.get(name, 0)
            if lq == rq:
                continue
            if lq == 0:
                changes.append(Change("add", zone_name, name, 0, rq))
            elif rq == 0:
                changes.append(Change("remove", zone_name, name, lq, 0))
            else:
                changes.append(Change("qty", zone_name, name, lq, rq))
    return changes


def _zone_to_dict(deck: Deck, zone_name: str) -> dict[str, int]:
    """Sum quantities by card name — a deck can list a card under several
    printings (multiple <card .../> lines with the same name but different
    setShortName/uuid). Treat them as a single logical card for diff."""
    zone = deck.zone(zone_name)
    if zone is None:
        return {}
    totals: dict[str, int] = {}
    for c in zone.cards:
        totals[c.name] = totals.get(c.name, 0) + c.quantity
    return totals
