"""Moxfield deck fetcher.

URL forms:
  https://www.moxfield.com/decks/<publicId>
  https://moxfield.com/decks/<publicId>

API: https://api2.moxfield.com/v3/decks/all/<publicId>
"""
from __future__ import annotations

import re
from typing import Any

import requests

from .. import dfc
from .types import RemoteDeck

_API_BASE = "https://api2.moxfield.com/v3/decks/all/"
_USER_AGENT = "cod-sync/0.1 (+local CLI for personal use)"
_DECK_ID_RE = re.compile(r"/decks/([A-Za-z0-9_-]+)")

# Moxfield board names → Cockatrice zone names.
# Main deck, commanders, companions all live in `main` for Cockatrice.
# Sideboard goes to `side`. Maybeboard is intentionally ignored.
_BOARD_TO_ZONE = {
    "mainboard": "main",
    "commanders": "main",
    "companions": "main",
    "sideboard": "side",
}


def fetch(url: str) -> RemoteDeck:
    public_id = _extract_id(url)
    resp = requests.get(
        _API_BASE + public_id,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return RemoteDeck(name=_extract_name(data), zones=_parse(data))


def _extract_name(data: dict[str, Any]) -> str:
    raw = data.get("name") or ""
    return raw.strip()


def _extract_id(url: str) -> str:
    m = _DECK_ID_RE.search(url)
    if not m:
        raise ValueError(f"Could not extract Moxfield deck id from URL: {url}")
    return m.group(1)


def _parse(data: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Parse Moxfield v3 response. Falls back to v2 layout if needed."""
    out: dict[str, dict[str, int]] = {"main": {}, "side": {}}

    boards = data.get("boards")
    if isinstance(boards, dict):
        # v3 layout: {boards: {mainboard: {cards: {<id>: {quantity, card: {name}}}}}}
        for board_name, zone_name in _BOARD_TO_ZONE.items():
            board = boards.get(board_name) or {}
            cards = board.get("cards") or {}
            for entry in cards.values():
                _add(out[zone_name], entry)
        return out

    # v2 fallback: boards live as top-level keys.
    for board_name, zone_name in _BOARD_TO_ZONE.items():
        cards = data.get(board_name) or {}
        if isinstance(cards, dict):
            for entry in cards.values():
                _add(out[zone_name], entry)
    return out


def _add(zone: dict[str, int], entry: dict[str, Any]) -> None:
    qty = int(entry.get("quantity", 0))
    if qty <= 0:
        return
    card = entry.get("card") or {}
    name = card.get("name")
    if not name:
        return
    name = dfc.front_face(name)
    zone[name] = zone.get(name, 0) + qty
