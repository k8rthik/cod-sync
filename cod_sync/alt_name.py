"""Reskin / flavor name normalization.

Some MTG cards have alternate flavor names — Secret Lair reskins like
"Unstable Harmonics" (printed name) / "Rhystic Study" (canonical name) —
where Moxfield and Archidekt return the flavor name, but Cockatrice only
recognizes the canonical name. This module maps the flavor names back so
Cockatrice's importer will accept the card.

Resolution order:
  1. Bundled seed dict (`_SEED`) — common reskins resolve with no network.
  2. Disk cache (`~/.cache/cod-sync/alt_names.json`) — populated as Scryfall
     resolves new names.
  3. Scryfall `/cards/collection` batch endpoint — up to 75 cards per POST.

Anything that fails to resolve (404, network error, bad payload) maps to
itself and that identity result is cached so we don't re-query on every
sync. Set the env var `COD_SYNC_NO_NETWORK=1` to skip Scryfall entirely —
useful for tests and offline use; unknown names fall back to themselves
and are not written to the cache.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

import requests


_API_COLLECTION = "https://api.scryfall.com/cards/collection"
_USER_AGENT = "cod-sync/0.7 (+local CLI for personal use)"
_TIMEOUT = 15
_BATCH_SIZE = 75  # Scryfall's per-request limit.

# Hard-coded baseline so the most common reskins resolve without a Scryfall
# round-trip on a brand new install. Add to this list as community feedback
# surfaces new reskins; the cache backs everything else.
_SEED: dict[str, str] = {
    "Unstable Harmonics": "Rhystic Study",
}


def canonicalize_batch(names: Iterable[str]) -> dict[str, str]:
    """Resolve a batch of card names to their Cockatrice-canonical forms.

    Returns a `{input_name: canonical_name}` mapping covering every distinct
    input name. Unknown names are resolved via Scryfall in a single POST per
    chunk of 75 and the results are persisted. Anything that doesn't resolve
    maps to itself.
    """
    distinct = {n for n in names if n}
    if not distinct:
        return {}

    cache = _load_cache()
    out: dict[str, str] = {}
    unknown: list[str] = []
    for n in distinct:
        if n in cache:
            out[n] = cache[n]
        else:
            unknown.append(n)

    if not unknown:
        return out

    if _network_disabled():
        for n in unknown:
            out[n] = n
        return out

    resolved = _scryfall_batch_lookup(unknown)
    for n in unknown:
        canonical = resolved.get(n, n)
        out[n] = canonical
        cache[n] = canonical
    _save_cache(cache)
    return out


def canonicalize(name: str) -> str:
    """Single-name convenience wrapper around `canonicalize_batch`."""
    return canonicalize_batch([name]).get(name, name)


# ----- cache / env helpers --------------------------------------------------


def _network_disabled() -> bool:
    return os.environ.get("COD_SYNC_NO_NETWORK") == "1"


def _cache_path() -> Path:
    """Where to read/write the cache.

    `COD_SYNC_CACHE_DIR` wins over `XDG_CACHE_HOME` wins over `~/.cache`.
    Tests redirect via `COD_SYNC_CACHE_DIR` so they don't touch the user's
    real cache.
    """
    explicit = os.environ.get("COD_SYNC_CACHE_DIR")
    if explicit:
        return Path(explicit) / "cod-sync" / "alt_names.json"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "cod-sync" / "alt_names.json"


def _load_cache() -> dict[str, str]:
    """Build the in-memory cache: seed values, then whatever's on disk."""
    cache: dict[str, str] = dict(_SEED)
    path = _cache_path()
    if not path.exists():
        return cache
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return cache
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, str):
                cache[k] = v
    return cache


def _save_cache(cache: dict[str, str]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
    except OSError:
        pass  # cache writes are best-effort.


# ----- Scryfall ------------------------------------------------------------


def _scryfall_batch_lookup(names: list[str]) -> dict[str, str]:
    """Resolve unknown names through Scryfall's `/cards/collection` endpoint.

    Returns `{input_name: canonical_name}` for names that resolved. Missing
    keys mean the lookup failed (404, timeout, parse error); callers treat
    those as identity.
    """
    resolved: dict[str, str] = {}
    for i in range(0, len(names), _BATCH_SIZE):
        chunk = names[i:i + _BATCH_SIZE]
        try:
            resp = requests.post(
                _API_COLLECTION,
                json={"identifiers": [{"name": n} for n in chunk]},
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            continue
        _absorb_response(chunk, data, resolved)
    return resolved


def _absorb_response(
    chunk: list[str], data: dict, resolved: dict[str, str]
) -> None:
    """Match Scryfall response items back to input query names.

    Scryfall preserves request order in `data` and lists unresolved
    identifiers in `not_found`. Walk `chunk` skipping `not_found` names,
    then zip the survivors against `data` in order.
    """
    not_found_names: set[str] = set()
    for ident in data.get("not_found") or []:
        if isinstance(ident, dict):
            n = ident.get("name")
            if isinstance(n, str):
                not_found_names.add(n)

    data_items = data.get("data") or []
    di = 0
    for query in chunk:
        if query in not_found_names:
            continue
        if di >= len(data_items):
            break
        item = data_items[di]
        di += 1
        if isinstance(item, dict):
            canonical = item.get("name")
            if isinstance(canonical, str):
                resolved[query] = canonical
