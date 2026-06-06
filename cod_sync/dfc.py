"""DFC name normalization.

Cockatrice's card database stores double-faced cards (and similar split-face
layouts) under the front face only. For example, "Storm the Vault // Vault of
Catlacan" is stored as "Storm the Vault". Both Moxfield and Archidekt return
the full "Front // Back" form, so we reduce remote names to the front face
before the .cod ever sees them.

This is a heuristic — split cards like "Fire // Ice" also use the " // "
separator and Cockatrice keeps the full name for those. In practice the
collections this tool is built for don't run split cards and treating the
" // " separator as a DFC marker works reliably. If a real split card breaks,
this is the function to make layout-aware.
"""
from __future__ import annotations


def front_face(name: str) -> str:
    """Return only the front face of a "Front // Back" card name."""
    if " // " in name:
        return name.split(" // ", 1)[0]
    return name
