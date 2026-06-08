"""Reskin / flavor name normalization.

Moxfield and Archidekt return Secret Lair reskins under their printed
flavor name (e.g. "Unstable Harmonics"), but Cockatrice only recognizes
the canonical card name ("Rhystic Study"). This module resolves the
flavor name to the canonical name through three layers:

  1. Bundled seed dict (`_seed_data.SEED`) — ~450 known reskins, refreshed
     at release time via `scripts/refresh_seed.py`. Pure in-memory lookup.
  2. Disk cache (`~/.cache/cod-sync/alt_names.json`) — per-user, populated
     as Scryfall resolves new names. Survives between syncs and only stores
     entries we LEARNED (the seed is not duplicated to disk).
  3. Scryfall `/cards/collection` endpoint — one batched POST per chunk of
     75 names. Catches reskins that shipped after the bundled seed was
     regenerated.

Identity results (the card is not a reskin) are cached on disk too, so
every distinct card name is queried at most once across the user's whole
history. Network errors and 4xx/5xx responses silently fall back to
identity. Set `COD_SYNC_NO_NETWORK=1` to skip step 3 entirely; unknown
names then pass through unchanged and nothing is written to disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

import requests

from . import _seed_data


_API_COLLECTION = "https://api.scryfall.com/cards/collection"
_USER_AGENT = "cod-sync/0.7 (+https://github.com/k8rthik/cod-sync)"
_TIMEOUT = 15
_BATCH_SIZE = 75  # Scryfall's per-request limit.

_SEED: dict[str, str] = _seed_data.SEED


def canonicalize_batch(names: Iterable[str]) -> dict[str, str]:
    """Resolve a batch of card names to their Cockatrice-canonical forms.

    Returns a `{input_name: canonical_name}` mapping covering every distinct
    non-empty input. Bundled seed and on-disk cache are checked in memory.
    Everything else goes to Scryfall in chunks of 75 and is cached.
    """
    distinct = {n for n in names if n}
    if not distinct:
        return {}

    out: dict[str, str] = {}
    known = _load_known()  # seed + on-disk
    unknown: list[str] = []
    for n in distinct:
        if n in known:
            out[n] = known[n]
        else:
            unknown.append(n)

    if not unknown:
        return out

    if _network_disabled():
        for n in unknown:
            out[n] = n
        return out

    resolved = _scryfall_batch_lookup(unknown)
    additions: dict[str, str] = {}
    for n in unknown:
        canonical = resolved.get(n, n)
        out[n] = canonical
        additions[n] = canonical
    _append_to_cache(additions)
    return out


def canonicalize(name: str) -> str:
    """Single-name convenience wrapper around `canonicalize_batch`."""
    if not name:
        return name
    return canonicalize_batch([name]).get(name, name)


# ----- cache + env helpers --------------------------------------------------


def _network_disabled() -> bool:
    return os.environ.get("COD_SYNC_NO_NETWORK") == "1"


def _cache_path() -> Path:
    explicit = os.environ.get("COD_SYNC_CACHE_DIR")
    if explicit:
        return Path(explicit) / "cod-sync" / "alt_names.json"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "cod-sync" / "alt_names.json"


def _load_known() -> dict[str, str]:
    """Union of bundled seed and on-disk learned cache (disk wins on conflict)."""
    out: dict[str, str] = dict(_SEED)
    out.update(_load_disk_cache())
    return out


def _load_disk_cache() -> dict[str, str]:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def _append_to_cache(additions: dict[str, str]) -> None:
    """Merge `additions` into the on-disk cache. Seed is never persisted here."""
    if not additions:
        return
    existing = _load_disk_cache()
    existing.update(additions)
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, sort_keys=True)
    except OSError:
        pass  # best-effort.


# ----- Scryfall ------------------------------------------------------------


def _scryfall_batch_lookup(names: list[str]) -> dict[str, str]:
    """Resolve unknown names via Scryfall's `/cards/collection` endpoint.

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
