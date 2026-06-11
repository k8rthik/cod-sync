"""Multi-face card name shaping.

Cockatrice's card database keys true double-faced cards (transform,
modal_dfc, meld, flip, adventure) by the front face only — "Storm the
Vault // Vault of Catlacan" is stored as "Storm the Vault". But cards
whose two halves share a single face keep the full "A // B" name: split
cards ("Fire // Ice"), aftermath cards ("Dusk // Dawn"), and the
Duskmourn "Room" enchantments ("Bottomless Pool // Locker Room"), which
Scryfall also classifies as layout "split".

`cockatrice_name` shapes a name using the card's Scryfall-style layout
when the caller has one (Moxfield, Archidekt, and Scryfall responses all
carry it). `front_face` is the layout-blind fallback for callers with no
layout information; it treats " // " as a DFC marker, which is correct
for every layout except split/aftermath.
"""

from __future__ import annotations

# Scryfall layouts whose cards Cockatrice stores under the full "A // B"
# name. Everything else with a " // " separator is keyed by front face.
_FULL_NAME_LAYOUTS = frozenset({"split", "aftermath"})


def front_face(name: str) -> str:
    """Return only the front face of a "Front // Back" card name."""
    if " // " in name:
        return name.split(" // ", 1)[0]
    return name


def cockatrice_name(name: str, layout: str | None) -> str:
    """Shape a card name to the form Cockatrice's database uses.

    Keeps the full "A // B" name for split-style layouts (split cards,
    aftermath, Rooms); reduces every other layout — including an unknown
    or missing one — to the front face.
    """
    if layout and layout.lower() in _FULL_NAME_LAYOUTS:
        return name
    return front_face(name)
