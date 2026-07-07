"""Moxfield deck fetcher.

URL forms:
  https://www.moxfield.com/decks/<publicId>
  https://moxfield.com/decks/<publicId>

API: https://api2.moxfield.com/v3/decks/all/<publicId>
"""

from __future__ import annotations

import re
from typing import Any

from .. import dfc, errors
from . import _http
from .types import RemoteDeck

_API_BASE = "https://api2.moxfield.com/v3/decks/all/"
_DECK_ID_RE = re.compile(r"/decks/([A-Za-z0-9_-]+)")

# Moxfield board names → Cockatrice zone names.
# Cockatrice has no commander/companion zone; the convention is to place
# both in the sideboard so they render with the commander pin. Maybeboard
# is excluded by default and folded into the sideboard only when the caller
# passes include_maybeboard (see _parse).
_BOARD_TO_ZONE = {
    "mainboard": "main",
    "commanders": "side",
    "companions": "side",
    "sideboard": "side",
}
_MAYBEBOARD = "maybeboard"


def fetch(url: str, *, include_maybeboard: bool = False) -> RemoteDeck:
    import requests  # deferred: only network paths pay the import

    public_id = _extract_id(url)
    try:
        resp = _http.get_session().get(_API_BASE + public_id, timeout=20)
    except (requests.ConnectionError, requests.Timeout) as e:
        raise errors.NetworkError(url, cause=type(e).__name__) from e
    except requests.RequestException as e:
        raise errors.NetworkError(url, cause=str(e) or type(e).__name__) from e
    if not resp.ok:
        raise errors.from_http_response(url, resp)
    try:
        data = resp.json()
    except ValueError as e:
        raise errors.MalformedResponseError(url, reason="invalid JSON") from e
    return RemoteDeck(
        name=_extract_name(data),
        zones=_parse(data, include_maybeboard=include_maybeboard),
        tags=_extract_tags(data),
    )


def _extract_name(data: dict[str, Any]) -> str:
    raw = data.get("name") or ""
    return raw.strip()


def _extract_tags(data: dict[str, Any]) -> tuple[str, ...]:
    """Moxfield's deck-level tags live in `hubs` — themes/format labels at
    the deck level, distinct from per-card `tags`. Each hub is a `{name, slug}`
    object; we keep the human-readable `name`."""
    out: list[str] = []
    seen: set[str] = set()
    for entry in data.get("hubs") or []:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return tuple(out)


def _extract_id(url: str) -> str:
    m = _DECK_ID_RE.search(url)
    if not m:
        raise errors.InvalidSourceError(url, reason="could not extract Moxfield deck id")
    return m.group(1)


def _parse(data: dict[str, Any], *, include_maybeboard: bool = False) -> dict[str, dict[str, int]]:
    """Parse Moxfield v3 response. Falls back to v2 layout if needed.

    With ``include_maybeboard`` the maybeboard is folded into the sideboard;
    by default it is dropped entirely."""
    out: dict[str, dict[str, int]] = {"main": {}, "side": {}}

    board_to_zone = dict(_BOARD_TO_ZONE)
    if include_maybeboard:
        board_to_zone[_MAYBEBOARD] = "side"

    boards = data.get("boards")
    if isinstance(boards, dict):
        # v3 layout: {boards: {mainboard: {cards: {<id>: {quantity, card: {name}}}}}}
        for board_name, zone_name in board_to_zone.items():
            board = boards.get(board_name) or {}
            cards = board.get("cards") or {}
            for entry in cards.values():
                _add(out[zone_name], entry)
        return out

    # v2 fallback: boards live as top-level keys.
    for board_name, zone_name in board_to_zone.items():
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
    name = dfc.cockatrice_name(name, card.get("layout"))
    zone[name] = zone.get(name, 0) + qty
