"""Diff a local Cockatrice deck against a normalized remote decklist."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cod_sync import dfc
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


def _reconcile_dfc_names(local: dict[str, int], remote: dict[str, int]) -> dict[str, int]:
    """Pick the right card-name key for each remote entry.

    The source fetchers already strip "Front // Back" down to "Front" before
    the diff runs, but this layer stays defensive so direct callers can pass
    raw remote dicts in either form. Three cases:

      1. Remote name matches local exactly — use as-is.
      2. Remote has "Front // Back" — reduce to "Front" so it matches a
         front-only local key (and so new-add cards land under the
         Cockatrice-compatible front-face name).
      3. No match available — leave the remote name untouched.

    A local "Front // Back" entry with no matching remote key is intentionally
    surfaced as a remove + add pair: Cockatrice can't read the full form, so
    those entries are stale artifacts from before the alt_name DFC fix and
    need to heal to the front face on the next sync.
    """
    result: dict[str, int] = {}
    for remote_name, qty in remote.items():
        if remote_name in local:
            matched = remote_name
        elif " // " in remote_name:
            matched = dfc.front_face(remote_name)
        else:
            matched = remote_name
        result[matched] = result.get(matched, 0) + qty
    return result
