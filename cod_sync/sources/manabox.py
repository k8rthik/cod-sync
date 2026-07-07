"""ManaBox deck fetcher.

URL forms:
  https://manabox.app/decks/<shareId>
  https://www.manabox.app/decks/<shareId>

Unlike Moxfield and Archidekt, ManaBox exposes no public JSON API for
shared decks. The share page is server-rendered by Astro with the entire
deck serialized into an ``<astro-island>`` element's ``props`` attribute:
HTML-entity-encoded JSON in Astro's ``[type, value]`` tuple form. We fetch
the page, pull out that island's props, and decode it.

That couples this fetcher to ManaBox's page shape *and* Astro's
serialization format — more fragile than a documented API. Two things
keep it honest: a structural surprise (island missing, props not JSON,
deck shape unexpected) raises ``MalformedResponseError`` rather than a
traceback, and the network-gated integration test exercises the live page
so format drift surfaces as a test failure rather than a silent user
breakage. See ARCHITECTURE.md ("Card name shaping") for the layout rules
this fetcher feeds into.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from .. import dfc, errors
from . import _http
from .types import RemoteDeck

# The deck is serialized into the props of the Astro island whose
# component exports `Main`. props values are HTML-entity-encoded, so no
# literal `"` appears inside until the attribute's own closing quote.
_ISLAND_RE = re.compile(
    r'<astro-island\b[^>]*\bcomponent-export="Main"[^>]*?\bprops="(?P<props>.*?)"\s',
    re.DOTALL,
)

# ManaBox board categories (a numeric enum) → Cockatrice zones. Cockatrice
# has a single `side` zone and no dedicated command zone, so commanders,
# oathbreakers, and signature spells all render with the commander pin from
# the sideboard — the same convention the Moxfield/Archidekt fetchers use.
# Maybeboard (5) is intentionally absent: it is excluded by default, matching
# Moxfield's maybeboard and Archidekt's `includedInDeck: false`, and folded
# into the sideboard only when the caller passes include_maybeboard (see _parse).
_MAYBEBOARD = 5
_BOARD_TO_ZONE = {
    0: "side",  # commander
    1: "side",  # oathbreaker
    2: "side",  # signatureSpell
    3: "main",  # mainboard
    4: "side",  # sideboard
}

# ManaBox layout enum (numeric) → Scryfall layout string, so the shared
# `dfc.cockatrice_name` can shape multi-face names. ManaBox already reports
# multi-face cards in "Front // Back" form, which is what cockatrice_name
# expects. Any layout ManaBox doesn't enumerate maps to None, and
# cockatrice_name then reduces to the front face — the safe default.
_LAYOUT = {
    0: "normal",
    1: "split",
    2: "flip",
    3: "transform",
    4: "meld",
    5: "leveler",
    6: "saga",
    7: "planar",
    8: "scheme",
    9: "vanguard",
    10: "token",
    11: "double_faced_token",
    12: "emblem",
    13: "augment",
    14: "host",
    15: "art_series",
    16: "adventure",
    17: "modal_dfc",
    18: "class_layout",
}


def fetch(url: str, *, include_maybeboard: bool = False) -> RemoteDeck:
    import requests  # deferred: only network paths pay the import

    try:
        # Override the session's `Accept: application/json` default: the
        # share page is HTML, not an API response.
        resp = _http.get_session().get(url, timeout=20, headers={"Accept": "text/html"})
    except (requests.ConnectionError, requests.Timeout) as e:
        raise errors.NetworkError(url, cause=type(e).__name__) from e
    except requests.RequestException as e:
        raise errors.NetworkError(url, cause=str(e) or type(e).__name__) from e
    if not resp.ok:
        raise errors.from_http_response(url, resp)
    deck = _extract_deck(url, resp.text)
    return RemoteDeck(
        name=(deck.get("name") or "").strip(),
        zones=_parse(deck, include_maybeboard=include_maybeboard),
    )


def _extract_deck(url: str, page: str) -> dict[str, Any]:
    """Pull the decoded deck object out of the rendered share page."""
    m = _ISLAND_RE.search(page)
    if not m:
        raise errors.MalformedResponseError(url, reason="deck data not found on page")
    try:
        props = json.loads(html.unescape(m.group("props")))
    except ValueError as e:
        raise errors.MalformedResponseError(url, reason="could not parse embedded deck JSON") from e
    deck = _astro_decode(props.get("deck") if isinstance(props, dict) else None)
    if not isinstance(deck, dict) or not isinstance(deck.get("cards"), list):
        raise errors.MalformedResponseError(url, reason="unexpected deck shape")
    return deck


def _astro_decode(node: Any) -> Any:
    """Decode Astro's ``[type, value]`` island serialization.

    Type 0 (Value) wraps a primitive as-is, or a plain object whose values
    are themselves encoded tuples; type 1 (Array) wraps a list of encoded
    items. Other Astro prop types (Date, Map, Set, …) don't appear in deck
    data; their payload is returned untouched so an unexpected one degrades
    rather than crashes.
    """
    if isinstance(node, list) and len(node) == 2 and isinstance(node[0], int):
        kind, payload = node
        if kind == 0:
            if isinstance(payload, dict):
                return {key: _astro_decode(value) for key, value in payload.items()}
            return payload
        if kind == 1 and isinstance(payload, list):
            return [_astro_decode(item) for item in payload]
        return payload
    return node


def _parse(deck: dict[str, Any], *, include_maybeboard: bool = False) -> dict[str, dict[str, int]]:
    """Map a decoded ManaBox deck onto the {main, side} zone model.

    With ``include_maybeboard`` the maybeboard is folded into the sideboard;
    by default it is dropped entirely."""
    out: dict[str, dict[str, int]] = {"main": {}, "side": {}}
    board_to_zone = dict(_BOARD_TO_ZONE)
    if include_maybeboard:
        board_to_zone[_MAYBEBOARD] = "side"
    for entry in deck.get("cards") or []:
        if not isinstance(entry, dict):
            continue
        board = entry.get("boardCategory")
        if board == _MAYBEBOARD and not include_maybeboard:
            continue
        qty = int(entry.get("quantity") or 0)
        if qty <= 0:
            continue
        raw_name = entry.get("name")
        if not raw_name:
            continue
        layout = entry.get("layout")
        name = dfc.cockatrice_name(
            raw_name, _LAYOUT.get(layout) if isinstance(layout, int) else None
        )
        zone = board_to_zone.get(board, "main") if isinstance(board, int) else "main"
        out[zone][name] = out[zone].get(name, 0) + qty
    return out
