"""Archidekt deck fetcher.

URL forms:
  https://archidekt.com/decks/<id>
  https://archidekt.com/decks/<id>/<slug>

API: https://archidekt.com/api/decks/<id>/
"""

from __future__ import annotations

import re
from typing import Any

from .. import dfc, errors
from . import _http
from .types import RemoteDeck

_API_BASE = "https://archidekt.com/api/decks/"
_DECK_ID_RE = re.compile(r"/decks/(\d+)")

# Archidekt categories that map to Cockatrice's `side` zone. Cockatrice
# has no commander/companion zone; both render with the commander pin
# only from the sideboard.
_SIDE_CATEGORIES = {"sideboard", "commander", "companion"}


def fetch(url: str) -> RemoteDeck:
    import requests  # deferred: only network paths pay the import

    deck_id = _extract_id(url)
    try:
        resp = _http.get_session().get(f"{_API_BASE}{deck_id}/", timeout=20)
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
    return RemoteDeck(name=_extract_name(data), zones=_parse(data), tags=_extract_tags(data))


def _extract_name(data: dict[str, Any]) -> str:
    raw = data.get("name") or ""
    return raw.strip()


def _extract_tags(data: dict[str, Any]) -> tuple[str, ...]:
    """Archidekt's deck-level tags live in `deckTags`, separate from per-card
    `categories`. Shape varies — entries may be `{name: str, ...}` dicts or
    bare strings depending on the API generation. Accept both, drop blanks."""
    out: list[str] = []
    seen: set[str] = set()
    for entry in data.get("deckTags") or []:
        if isinstance(entry, dict):
            name = (entry.get("name") or "").strip()
        elif isinstance(entry, str):
            name = entry.strip()
        else:
            continue
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
        raise errors.InvalidSourceError(url, reason="could not extract Archidekt deck id")
    return m.group(1)


def _parse(data: dict[str, Any]) -> dict[str, dict[str, int]]:
    # Categories list tells us which buckets are part of the deck at all,
    # and which (if any) should be treated as sideboard. Maybeboard is
    # represented by `includedInDeck: false` and must be ignored.
    excluded: set[str] = set()
    side_categories = set(_SIDE_CATEGORIES)
    for cat in data.get("categories") or []:
        name = (cat.get("name") or "").strip()
        if not name:
            continue
        if not cat.get("includedInDeck", True):
            excluded.add(name.lower())

    out: dict[str, dict[str, int]] = {"main": {}, "side": {}}
    for entry in data.get("cards") or []:
        qty = int(entry.get("quantity", 0))
        if qty <= 0:
            continue
        categories = [c.lower() for c in (entry.get("categories") or [])]
        if any(c in excluded for c in categories):
            continue
        name = _card_name(entry)
        if not name:
            continue
        name = dfc.cockatrice_name(name, _card_layout(entry))
        zone = "side" if any(c in side_categories for c in categories) else "main"
        out[zone][name] = out[zone].get(name, 0) + qty
    return out


def _card_name(entry: dict[str, Any]) -> str | None:
    card = entry.get("card") or {}
    oracle = card.get("oracleCard") or {}
    return oracle.get("name") or card.get("displayName")


def _card_layout(entry: dict[str, Any]) -> str | None:
    card = entry.get("card") or {}
    oracle = card.get("oracleCard") or {}
    layout = oracle.get("layout")
    return layout if isinstance(layout, str) else None
