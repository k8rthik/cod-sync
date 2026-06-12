"""Plain-text decklist parser (MTGA / MTGO export formats).

Accepts "1 Card", "1x Card", and "1 Card (SET) 123" lines, the MTGO
"SB:" prefix, and section headers like Deck / Mainboard / Sideboard /
Commander. Lines starting with // or # are comments.

Plain text carries no layout information, so every "A // B" name is
reduced to its front face here; the alt_name layer restores full names
for split-family cards when the network is available (see
ARCHITECTURE.md, "Card name shaping").
"""

from __future__ import annotations

import re

from .. import dfc

# Matches:  "1 Card Name", "1x Card Name", "1 Card Name (SET) 123", "SB: 1 Card"
# Collector number is only consumed when it follows a (SET) tag — otherwise a
# trailing word is part of the card name (e.g. "Agatha's Soul Cauldron").
_LINE_RE = re.compile(
    r"""^\s*
        (?:SB:\s*)?
        (?P<qty>\d+)\s*[xX]?\s+
        (?P<name>.+?)
        (?:\s+\((?P<set>[^)]+)\)(?:\s+\S+)?)?
        \s*$
    """,
    re.VERBOSE,
)

# Cockatrice has no commander/companion zone; both render with the
# commander pin only from the sideboard, so commander/companion headers
# route there too.
_SIDE_HEADERS = {"sideboard", "side", "sb", "commander", "commanders", "companion"}
_MAIN_HEADERS = {"deck", "mainboard", "main"}

_SB_PREFIX_RE = re.compile(r"^\s*SB:")


def parse(text: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {"main": {}, "side": {}}
    current = "main"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        header = line.rstrip(":").lower()
        if header in _SIDE_HEADERS:
            current = "side"
            continue
        if header in _MAIN_HEADERS:
            current = "main"
            continue

        # MTGO-style explicit sideboard prefix overrides current zone.
        zone = "side" if _SB_PREFIX_RE.match(raw) else current

        m = _LINE_RE.match(raw)
        if not m:
            continue
        name = m.group("name").strip()
        qty = int(m.group("qty"))
        if not name or qty <= 0:
            continue
        name = dfc.front_face(name)
        out[zone][name] = out[zone].get(name, 0) + qty
    return out
