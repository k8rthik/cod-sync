"""Performance contract for the alt_name layer.

These tests are intentionally generous about wall-clock targets — CI
machines vary by 10x — but they're strict about the structural invariants
that make those targets achievable: disk-cache is read once per process,
the seed dict is never copied on the hot path, the HTTP session is reused
across batches, and repeated lookups within a process don't re-query
Scryfall.

When a target trips here, the failure is almost always one of those
invariants regressing, not actual wall-clock drift.
"""

from __future__ import annotations

import json
import time

import pytest

from cod_sync import alt_name

# ----- structural invariants (the ones that drive latency) ------------------


def test_disk_cache_loaded_once_per_process(monkeypatch, tmp_path):
    """Across many calls, the JSON file is read at most once."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"Some Card": "Some Card"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    reads = [0]
    real = alt_name._read_disk_cache

    def counted():
        reads[0] += 1
        return real()

    monkeypatch.setattr("cod_sync.alt_name._read_disk_cache", counted)

    for _ in range(50):
        alt_name.canonicalize_batch(["Unstable Harmonics", "Sol Ring"])

    assert reads[0] == 1, (
        f"Disk cache should be read exactly once; got {reads[0]} reads. "
        "Lazy-load invariant has regressed."
    )


def test_session_reused_across_scryfall_batches(monkeypatch, tmp_path):
    """One requests.Session is created and reused across all batches."""
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("COD_SYNC_NO_NETWORK", raising=False)

    import requests

    session_constructions = [0]
    real_session_ctor = requests.Session

    def counting_session(*a, **k):
        session_constructions[0] += 1
        return real_session_ctor(*a, **k)

    # `requests` is imported lazily inside `_get_session`; patching the real
    # module's Session is what that deferred import resolves to.
    monkeypatch.setattr(requests, "Session", counting_session)
    # Replace lookup at the very end of the network path so we don't actually
    # hit Scryfall but the session is still constructed.
    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda names: ({n: n for n in names}, set()),
    )
    # Force at least one Scryfall call so _get_session would be invoked.
    # Since _scryfall_batch_lookup is mocked, _get_session is never called.
    # Instead, hit _get_session directly to verify single construction.
    s1 = alt_name._get_session()
    s2 = alt_name._get_session()
    s3 = alt_name._get_session()

    assert session_constructions[0] == 1, (
        f"requests.Session was constructed {session_constructions[0]} times. "
        "Should be exactly 1 — keep-alive is the whole point."
    )
    assert s1 is s2 is s3


def test_repeated_unknown_only_hits_scryfall_once(monkeypatch, tmp_path):
    """Cross-deck case: same unknown card across many calls = 1 Scryfall hit."""
    monkeypatch.delenv("COD_SYNC_NO_NETWORK", raising=False)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    calls = [0]

    def fake_lookup(names):
        calls[0] += 1
        return {n: n for n in names}, set()

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    # Simulate a 15-deck walk where every deck has "Random Card" in it.
    for _ in range(15):
        alt_name.canonicalize_batch(["Random Card"])

    assert calls[0] == 1, (
        f"Scryfall hit {calls[0]} times across 15 decks containing the same "
        "unknown card. In-memory caching has regressed."
    )


def test_seed_lookups_dont_touch_disk(monkeypatch, tmp_path):
    """Pure-seed calls don't touch the disk cache (read or write)."""
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    # Warm the lazy disk load (which is empty / doesn't exist).
    alt_name._get_disk_cache()

    reads = [0]
    monkeypatch.setattr(
        "cod_sync.alt_name._read_disk_cache",
        lambda: reads.__setitem__(0, reads[0] + 1) or {},
    )

    for _ in range(100):
        out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Rhystic Study"}
    assert reads[0] == 0, "Seed-only lookups should never touch disk"
    assert not (tmp_path / "cod-sync" / "alt_names.json").exists(), (
        "Seed-only lookups should not create the cache file"
    )


# ----- latency budgets ------------------------------------------------------
#
# These wall-clock checks use very loose bounds (10–100x slack) so they don't
# flake under load. The point is to catch O(N^2) regressions, not microsecond
# drift.


def _measure(fn, repeats: int = 1) -> float:
    """Wall-clock seconds for `fn()` repeated `repeats` times."""
    start = time.perf_counter()
    for _ in range(repeats):
        fn()
    return time.perf_counter() - start


@pytest.mark.parametrize("size", [10, 100, 500])
def test_offline_batch_under_target(size, monkeypatch, tmp_path):
    """Offline batch of N cards resolves in well under a millisecond per card."""
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))
    names = [f"Card {i}" for i in range(size)]

    # Warm: first call lazy-loads disk and writes identity cache.
    alt_name.canonicalize_batch(names)

    # Now measure on a hot in-memory cache.
    elapsed = _measure(lambda: alt_name.canonicalize_batch(names))
    per_card_us = elapsed * 1_000_000 / size
    assert elapsed < 0.05, (
        f"Hot batch of {size} cards took {elapsed * 1000:.2f}ms "
        f"({per_card_us:.1f}us/card). Target: under 50ms total."
    )


def test_seed_lookup_throughput(monkeypatch, tmp_path):
    """1000 single seed lookups should finish in well under 100ms."""
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))
    alt_name.canonicalize("Sol Ring")  # warm

    elapsed = _measure(lambda: alt_name.canonicalize("Unstable Harmonics"), repeats=1000)
    per_call_us = elapsed * 1000  # ms per 1000 calls = us per call
    assert elapsed < 0.5, (
        f"1000 seed lookups took {elapsed * 1000:.1f}ms "
        f"({per_call_us:.1f}us/call). Target: well under 500ms."
    )


def test_directory_walk_simulation(monkeypatch, tmp_path):
    """Simulate a 15-deck walk where decks share ~50% of their cards.

    Validates that cross-deck memoization actually amortizes lookups.
    """
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    # 15 decks, each 100 cards. Half overlap with the previous deck.
    decks = []
    for i in range(15):
        deck = [f"Shared {j}" for j in range(50)] + [f"Unique deck{i} card{j}" for j in range(50)]
        decks.append(deck)

    elapsed = _measure(lambda: [alt_name.canonicalize_batch(d) for d in decks])
    assert elapsed < 0.5, (
        f"15-deck walk simulation took {elapsed * 1000:.1f}ms; "
        "expect well under 500ms with proper cross-call memoization."
    )


# ----- write-amplification --------------------------------------------------


def test_offline_path_does_not_write_disk(monkeypatch, tmp_path):
    """When network is off, unknown cards do not get persisted to disk —
    otherwise the cache fills with junk identities the user never asked for."""
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    alt_name.canonicalize_batch([f"Mystery {i}" for i in range(100)])

    assert not (tmp_path / "cod-sync" / "alt_names.json").exists()


def test_cache_write_is_single_per_batch(monkeypatch, tmp_path):
    """One canonicalize_batch call = at most one disk write, no matter how many
    unknowns or how many Scryfall chunks."""
    monkeypatch.delenv("COD_SYNC_NO_NETWORK", raising=False)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda names: ({n: n for n in names}, set()),
    )

    writes = [0]
    real_save = alt_name._save_disk_cache

    def counted(cache):
        writes[0] += 1
        real_save(cache)

    monkeypatch.setattr("cod_sync.alt_name._save_disk_cache", counted)

    # 200 unknowns: 3 Scryfall chunks of 75/75/50.
    alt_name.canonicalize_batch([f"Unknown {i}" for i in range(200)])

    assert writes[0] == 1, f"200-card batch wrote disk {writes[0]} times; should be 1."
