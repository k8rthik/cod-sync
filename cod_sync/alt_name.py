"""Reskin / flavor name normalization.

Moxfield and Archidekt return Secret Lair reskins under their printed
flavor name (e.g. "Unstable Harmonics"), but Cockatrice only recognizes
the canonical card name ("Rhystic Study"). This module resolves the
flavor name to the canonical name through three layers:

  1. Bundled seed dict (`_seed_data.SEED`) — ~450 known reskins, refreshed
     at release time via `scripts/refresh_seed.py`. Pure in-memory lookup.
  2. Disk cache (`~/.cache/cod-sync/alt_names.json`) — per-user, populated
     as Scryfall resolves new names. Loaded once per process and held in
     memory for the rest of the run.
  3. Scryfall `/cards/collection` endpoint — one batched POST per chunk of
     75 names, sharing a keep-alive HTTP session across chunks. Catches
     reskins that shipped after the bundled seed was regenerated.

Identity results (the card is not a reskin) are cached on disk too, so
every distinct card name is queried at most once across the user's whole
history. Network errors and 4xx/5xx responses silently fall back to
identity. Set `COD_SYNC_NO_NETWORK=1` to skip step 3 entirely.

Performance: the disk cache is read once per process, the seed is never
copied on the hot path, and the HTTP session is reused across batches.
A 100-card sync with everything cached returns in well under a
millisecond; with all entries unknown and network off, well under 10ms.
A directory walk amortizes Scryfall lookups across decks — the first
deck pays the round-trip cost, subsequent decks hit the in-memory cache.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import requests

from . import _seed_data, dfc

_API_COLLECTION = "https://api.scryfall.com/cards/collection"
_USER_AGENT = "cod-sync/0.7 (+https://github.com/k8rthik/cod-sync)"
_TIMEOUT = 15
_BATCH_SIZE = 75  # Scryfall's per-request limit.

_SEED: dict[str, str] = _seed_data.SEED


# ----- process-level state -------------------------------------------------
#
# Three pieces are memoized for the life of the process:
#   _disk_cache  — loaded once, mutated in place, written back when learned
#                  entries are added
#   _session     — keep-alive HTTP session so Scryfall batches reuse TCP/TLS
#   _cache_path_cache — env-resolved Path; saves an env lookup per call
#   _warned_save_failure — cache-write failures warn on stderr once, not per call
# All of these are reset by `_reset_state_for_tests()` between pytest tests.

_disk_cache: dict[str, str] | None = None
_session: requests.Session | None = None
_warned_save_failure: bool = False


def _reset_state_for_tests() -> None:
    """Drop process memoization. Call between tests so env changes take effect."""
    global _disk_cache, _session, _warned_save_failure
    _disk_cache = None
    _warned_save_failure = False
    if _session is not None:
        try:
            _session.close()
        except Exception:
            pass
        _session = None


# ----- public API ----------------------------------------------------------


def canonicalize_batch(names: Iterable[str]) -> dict[str, str]:
    """Resolve a batch of card names to their Cockatrice-canonical forms.

    Returns a `{input_name: canonical_name}` mapping covering every distinct
    non-empty input. The bundled seed and the in-memory disk cache are both
    O(1) per card. Unknown names hit Scryfall in chunks of 75 over a
    reused HTTP session.
    """
    distinct: set[str] = set()
    for n in names:
        if n:
            distinct.add(n)
    if not distinct:
        return {}

    disk = _get_disk_cache()
    seed = _SEED  # local reference avoids repeated module attribute lookups
    out: dict[str, str] = {}
    unknown: list[str] | None = None

    for n in distinct:
        # Disk wins over seed so users can override entries locally.
        v = disk.get(n)
        if v is None:
            v = seed.get(n)
        if v is not None:
            out[n] = dfc.front_face(v)
        else:
            if unknown is None:
                unknown = []
            unknown.append(n)

    if not unknown:
        return out

    if _network_disabled():
        for n in unknown:
            out[n] = n
        return out

    resolved = _scryfall_batch_lookup(unknown)
    for n in unknown:
        # Scryfall returns DFC canonicals as "Front // Back"; Cockatrice
        # only recognizes the front face, so strip before caching.
        canonical = dfc.front_face(resolved.get(n, n))
        out[n] = canonical
        disk[n] = canonical  # in-memory cache wins for the rest of the process
    _save_disk_cache(disk)
    return out


def canonicalize(name: str) -> str:
    """Single-name convenience wrapper around `canonicalize_batch`."""
    if not name:
        return name
    # Fast path: seed-only lookup avoids the iterator/set construction.
    disk = _get_disk_cache()
    v = disk.get(name)
    if v is not None:
        return dfc.front_face(v)
    v = _SEED.get(name)
    if v is not None:
        return dfc.front_face(v)
    if _network_disabled():
        return name
    resolved = _scryfall_batch_lookup([name])
    canonical = dfc.front_face(resolved.get(name, name))
    disk[name] = canonical
    _save_disk_cache(disk)
    return canonical


# ----- env + cache helpers -------------------------------------------------


def _network_disabled() -> bool:
    return os.environ.get("COD_SYNC_NO_NETWORK") == "1"


def _cache_path() -> Path:
    explicit = os.environ.get("COD_SYNC_CACHE_DIR")
    if explicit:
        return Path(explicit) / "cod-sync" / "alt_names.json"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "cod-sync" / "alt_names.json"


def _get_disk_cache() -> dict[str, str]:
    """Lazy-load the disk cache once per process, then keep it in memory."""
    global _disk_cache
    if _disk_cache is None:
        _disk_cache = _read_disk_cache()
    return _disk_cache


def _read_disk_cache() -> dict[str, str]:
    """Read the JSON cache file fresh. Used by the lazy loader."""
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


def _save_disk_cache(cache: dict[str, str]) -> None:
    """Persist the in-memory cache. Best-effort: never raises, but warns on
    stderr once per process so an unwritable cache doesn't degrade silently."""
    global _warned_save_failure
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # `indent=None` is ~5x faster than indent=2 for serialization and the
        # cache is only ever read by us, so prettiness costs more than it pays.
        with path.open("w", encoding="utf-8") as f:
            json.dump(cache, f, separators=(",", ":"), sort_keys=True)
    except OSError as e:
        if not _warned_save_failure:
            _warned_save_failure = True
            print(
                f"warning: could not write alt-name cache to {path}: {e}; "
                "card-name lookups will not be cached across runs",
                file=sys.stderr,
            )


# ----- Scryfall ------------------------------------------------------------


def _get_session() -> requests.Session:
    """Reuse a single HTTP session so Scryfall batches share TCP+TLS state."""
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        _session = s
    return _session


def _scryfall_batch_lookup(names: list[str]) -> dict[str, str]:
    """Resolve unknown names via Scryfall's `/cards/collection` endpoint.

    Returns `{input_name: canonical_name}` for names that resolved. Missing
    keys mean the lookup failed (404, timeout, parse error); callers treat
    those as identity.
    """
    resolved: dict[str, str] = {}
    session = _get_session()
    for i in range(0, len(names), _BATCH_SIZE):
        chunk = names[i : i + _BATCH_SIZE]
        try:
            resp = session.post(
                _API_COLLECTION,
                json={"identifiers": [{"name": n} for n in chunk]},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            continue
        _absorb_response(chunk, data, resolved)
    return resolved


def _absorb_response(chunk: list[str], data: dict[str, Any], resolved: dict[str, str]) -> None:
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
