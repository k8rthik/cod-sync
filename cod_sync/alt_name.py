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
history — but only definitive answers are cached: a name Scryfall reports
as not-found is cached as identity, while a transport failure (timeout,
5xx) falls back to identity for the current run without caching, so one
network blip can't permanently mask a reskin. Set `COD_SYNC_NO_NETWORK=1`
to skip step 3 entirely.

Name shaping: Scryfall canonicals are shaped to Cockatrice's database
form using the card's `layout` (`dfc.cockatrice_name`) — transform/modal
DFCs reduce to the front face; single-face multi-part cards (split,
Rooms, aftermath, adventures/omens, prepare) keep the full "A // B"
name. Cached and seed values are stored
already shaped and trusted verbatim at read time.

Performance: the disk cache is read once per process, the seed is never
copied on the hot path, and the HTTP session is reused across batches.
A 100-card sync with everything cached returns in well under a
millisecond; with all entries unknown and network off, well under 10ms.
A directory walk amortizes Scryfall lookups across decks — the first
deck pays the round-trip cost, subsequent decks hit the in-memory cache.

Thread safety: `canonicalize` and `canonicalize_batch` may be called from
multiple threads. A single module-level lock guards lazy initialization of
the disk cache and HTTP session, all cache mutations, and disk writes; the
lock is never held during Scryfall HTTP calls, so concurrent batches overlap
their network I/O. Two threads racing on the same unknown name may each
query Scryfall once (results are identical; last write wins). Cache reads
are unlocked and rely on CPython's atomic dict access.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import _seed_data, dfc

if TYPE_CHECKING:
    # `requests` costs ~75ms to import; it's deferred to first network use
    # so CLI invocations that never hit Scryfall don't pay for it.
    import requests

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
#   _warned_save_failure — cache-write failures warn on stderr once, not per call
# All are guarded by `_state_lock`: mutate `_disk_cache` and call
# `_save_disk_cache` only while holding it. All are reset by
# `_reset_state_for_tests()` between pytest tests.

_state_lock = threading.Lock()
_disk_cache: dict[str, str] | None = None
_session: requests.Session | None = None
_warned_save_failure: bool = False


def _reset_state_for_tests() -> None:
    """Drop process memoization. Call between tests so env changes take effect."""
    global _disk_cache, _session, _warned_save_failure
    with _state_lock:
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
    distinct = {n for n in names if n}
    if not distinct:
        return {}

    disk = _get_disk_cache()
    seed = _SEED  # local reference avoids repeated module attribute lookups
    out: dict[str, str] = {}
    unknown: list[str] | None = None

    for n in distinct:
        # Disk wins over seed so users can override entries locally.
        # Values are stored already Cockatrice-shaped; trust them verbatim.
        v = disk.get(n)
        if v is None:
            v = seed.get(n)
        if v is not None:
            out[n] = v
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

    resolved, not_found = _scryfall_batch_lookup(unknown)  # network — lock not held

    # Scryfall's collection endpoint doesn't match full "A // B" names —
    # they come back not_found even for real cards. Retry those by front
    # half: the half resolves the card and its layout, so the shaped
    # canonical is right whether the card is a true DFC (→ front face)
    # or split-style (→ the full name back).
    retry = [n for n in not_found if " // " in n]
    if retry:
        half_to_full = {dfc.front_face(n): n for n in retry}
        re_resolved, _ = _scryfall_batch_lookup(list(half_to_full))
        for half, full in half_to_full.items():
            canonical = re_resolved.get(half)
            if canonical is not None:
                resolved[full] = canonical
                not_found.discard(full)

    learned = False
    with _state_lock:
        for n in unknown:
            canonical = resolved.get(n)
            if canonical is not None:
                # Already shaped by layout in `_absorb_response`.
                out[n] = canonical
                disk[n] = canonical  # in-memory cache wins for the rest of the process
                learned = True
            elif n in not_found:
                # Definitive miss: cache identity so we never re-query it.
                out[n] = n
                disk[n] = n
                learned = True
            else:
                # Transport failure: identity for this run only — caching it
                # would let one network blip permanently mask a reskin.
                out[n] = n
        if learned:
            _save_disk_cache(disk)
    return out


def canonicalize(name: str) -> str:
    """Single-name convenience wrapper around `canonicalize_batch`."""
    if not name:
        return name
    # Fast path: seed/disk lookup avoids the batch's set construction.
    disk = _get_disk_cache()
    v = disk.get(name)
    if v is None:
        v = _SEED.get(name)
    if v is not None:
        return v
    return canonicalize_batch([name]).get(name, name)


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
    with _state_lock:
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
    stderr once per process so an unwritable cache doesn't degrade silently.

    Callers must hold `_state_lock`; all mutations of the cache dict happen
    under the same lock, so `json.dump` can safely iterate it.
    """
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
    with _state_lock:
        if _session is None:
            import requests  # deferred: only network paths pay the import

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


def _scryfall_batch_lookup(names: list[str]) -> tuple[dict[str, str], set[str]]:
    """Resolve unknown names via Scryfall's `/cards/collection` endpoint.

    Returns `(resolved, not_found)`: `resolved` maps input names to their
    Cockatrice-shaped canonical names; `not_found` holds names Scryfall
    definitively reported as unknown. A name in neither means its request
    failed in transit (timeout, 5xx, parse error) — callers fall back to
    identity for the run without caching the answer.
    """
    import requests  # deferred: only network paths pay the import

    resolved: dict[str, str] = {}
    not_found: set[str] = set()
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
        _absorb_response(chunk, data, resolved, not_found)
    return resolved, not_found


def _absorb_response(
    chunk: list[str], data: dict[str, Any], resolved: dict[str, str], not_found: set[str]
) -> None:
    """Match Scryfall response items back to input query names.

    Scryfall preserves request order in `data` and lists unresolved
    identifiers in `not_found`. Walk `chunk` skipping `not_found` names,
    then zip the survivors against `data` in order. Canonical names are
    shaped to Cockatrice's form using each card's `layout`, so split-style
    cards (split, Rooms, aftermath, adventures/omens, prepare) keep their
    full "A // B" name while true DFCs
    reduce to the front face.
    """
    not_found_names: set[str] = set()
    for ident in data.get("not_found") or []:
        if isinstance(ident, dict):
            n = ident.get("name")
            if isinstance(n, str):
                not_found_names.add(n)
    not_found.update(not_found_names)

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
                layout = item.get("layout")
                resolved[query] = dfc.cockatrice_name(
                    canonical, layout if isinstance(layout, str) else None
                )
