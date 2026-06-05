"""Diff a local Cockatrice deck against a normalized remote decklist."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cod_sync.cod import Deck

ChangeKind = Literal["add", "remove", "qty"]


@dataclass(frozen=True)
class Change:
    kind: ChangeKind
    zone: str           # "main" | "side"
    name: str
    local_qty: int      # current quantity in the .cod (0 if absent)
    remote_qty: int     # quantity in the remote source (0 if absent)

    def describe(self) -> str:
        if self.kind == "add":
            return f"+ {self.remote_qty}x {self.name}"
        if self.kind == "remove":
            return f"- {self.local_qty}x {self.name}"
        return f"~ {self.local_qty} → {self.remote_qty}x {self.name}"


def compute(deck: Deck, remote: dict[str, dict[str, int]]) -> list[Change]:
    """Return the ordered list of changes needed to make `deck` match `remote`."""
    changes: list[Change] = []
    for zone_name in ("main", "side"):
        local = _zone_to_dict(deck, zone_name)
        remote_zone = _reconcile_dfc_names(local, remote.get(zone_name, {}))
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
    zone = deck.zone(zone_name)
    if zone is None:
        return {}
    return {c.name: c.quantity for c in zone.cards}


def _reconcile_dfc_names(local: dict[str, int], remote: dict[str, int]) -> dict[str, int]:
    """Match remote DFC names against local card names that may use either the
    full "Front // Back" form or just "Front". Cockatrice card databases vary
    on which form they store, and the user's collection mixes both. We keep
    the source faithful — only the *matching key* is rewritten when needed."""
    result: dict[str, int] = {}
    for remote_name, qty in remote.items():
        matched = remote_name
        if remote_name not in local and " // " in remote_name:
            front = remote_name.split(" // ", 1)[0]
            if front in local:
                matched = front
        result[matched] = result.get(matched, 0) + qty
    return result
