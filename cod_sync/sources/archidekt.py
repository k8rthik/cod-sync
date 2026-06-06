"""Archidekt deck fetcher.

URL forms:
  https://archidekt.com/decks/<id>
  https://archidekt.com/decks/<id>/<slug>

API: https://archidekt.com/api/decks/<id>/
"""
from __future__ import annotations

import re

import requests

from .. import dfc
from .types import RemoteDeck

_API_BASE = "https://archidekt.com/api/decks/"
_USER_AGENT = "cod-sync/0.1 (+local CLI for personal use)"
_DECK_ID_RE = re.compile(r"/decks/(\d+)")

# Archidekt categories that map to Cockatrice's `side` zone.
# Everything else (Commander included) goes to `main`.
_SIDE_CATEGORIES = {"sideboard"}


def fetch(url: str) -> RemoteDeck:
    deck_id = _extract_id(url)
    resp = requests.get(
        f"{_API_BASE}{deck_id}/",
        headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return RemoteDeck(name=_extract_name(data), zones=_parse(data))


def _extract_name(data: dict) -> str:
    raw = data.get("name") or ""
    return raw.strip()


def _extract_id(url: str) -> str:
    m = _DECK_ID_RE.search(url)
    if not m:
        raise ValueError(f"Could not extract Archidekt deck id from URL: {url}")
    return m.group(1)


def _parse(data: dict) -> dict[str, dict[str, int]]:
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
        name = dfc.front_face(name)
        zone = "side" if any(c in side_categories for c in categories) else "main"
        out[zone][name] = out[zone].get(name, 0) + qty
    return out


def _card_name(entry: dict) -> str | None:
    card = entry.get("card") or {}
    oracle = card.get("oracleCard") or {}
    return oracle.get("name") or card.get("displayName")
