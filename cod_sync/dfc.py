"""Multi-face card name shaping.

Cockatrice's card database keys physically double-faced cards (transform,
modal_dfc, meld) and Kamigawa flip cards by the front face only — "Storm
the Vault // Vault of Catlacan" is stored as "Storm the Vault". But cards
whose two halves share a single face keep the full "A // B" name: split
cards ("Fire // Ice"), the Duskmourn "Room" enchantments (Scryfall layout
"split"), aftermath cards ("Dusk // Dawn"), adventures ("Brazen
Borrower // Petty Theft") — including Tarkir omens, which Scryfall also
classifies as layout "adventure" — and prepare cards ("Studious
First-Year // Rampant Growth"). The split between the two groups was
verified against Cockatrice's own cards.xml: every adventure, aftermath,
split, and prepare entry uses the full name; no other layout does.

`cockatrice_name` shapes a name using the card's Scryfall-style layout
when the caller has one (Moxfield, Archidekt, and Scryfall responses all
carry it). `front_face` is the layout-blind fallback for callers with no
layout information; it treats " // " as a DFC marker, which is correct
for every layout outside the full-name group.
"""

from __future__ import annotations

# Scryfall layouts whose cards Cockatrice stores under the full "A // B"
# name. Everything else with a " // " separator is keyed by front face.
# "room" and "omen" are defensive aliases: Scryfall currently files Rooms
# under "split" and omens under "adventure", but the mechanics have their
# own names and a deck API could plausibly start reporting them as such.
_FULL_NAME_LAYOUTS = frozenset({"split", "aftermath", "adventure", "prepare", "room", "omen"})


def front_face(name: str) -> str:
    """Return only the front face of a "Front // Back" card name."""
    if " // " in name:
        return name.split(" // ", 1)[0]
    return name


def cockatrice_name(name: str, layout: str | None) -> str:
    """Shape a card name to the form Cockatrice's database uses.

    Keeps the full "A // B" name for single-face multi-part layouts
    (split, Rooms, aftermath, adventures/omens, prepare); reduces every
    other layout — including an unknown or missing one — to the front
    face.
    """
    if layout and layout.lower() in _FULL_NAME_LAYOUTS:
        return name
    return front_face(name)
