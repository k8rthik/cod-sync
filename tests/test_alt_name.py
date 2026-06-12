"""Tests for the bundled-seed + Scryfall-fallback canonicalization."""

from __future__ import annotations

import json
import threading
import time

from cod_sync import alt_name

# ----- bundled seed --------------------------------------------------------


def test_seed_entry_resolves():
    out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Rhystic Study"}


def test_unknown_name_is_identity_when_network_disabled():
    out = alt_name.canonicalize_batch(["Counterspell"])
    assert out == {"Counterspell": "Counterspell"}


def test_batch_mixes_known_and_unknown():
    out = alt_name.canonicalize_batch(["Unstable Harmonics", "Sol Ring", "Counterspell"])
    assert out == {
        "Unstable Harmonics": "Rhystic Study",
        "Sol Ring": "Sol Ring",
        "Counterspell": "Counterspell",
    }


def test_empty_input_returns_empty():
    assert alt_name.canonicalize_batch([]) == {}
    assert alt_name.canonicalize_batch([""]) == {}
    assert alt_name.canonicalize_batch(["", "Sol Ring"]) == {"Sol Ring": "Sol Ring"}


def test_canonicalize_single():
    assert alt_name.canonicalize("Unstable Harmonics") == "Rhystic Study"
    assert alt_name.canonicalize("Sol Ring") == "Sol Ring"
    assert alt_name.canonicalize("") == ""


def test_seed_is_non_trivial():
    """Guardrail: catches an accidentally-blanked _seed_data.py."""
    assert len(alt_name._SEED) > 50


def test_network_disabled_does_not_write_cache(tmp_path, monkeypatch):
    """No disk writes when network is off — disk cache only exists for
    Scryfall results."""
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))
    alt_name.canonicalize_batch(["Sol Ring", "Madeup Card"])

    assert not (tmp_path / "cod-sync" / "alt_names.json").exists()


# ----- disk cache ----------------------------------------------------------


def test_disk_cache_overrides_seed(tmp_path, monkeypatch):
    """Disk cache wins on conflict so users can locally correct entries."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"Unstable Harmonics": "Local Override"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Local Override"}


def test_disk_cache_resolves_offline(tmp_path, monkeypatch):
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"New Reskin": "Real Card"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["New Reskin"])
    assert out == {"New Reskin": "Real Card"}


def test_corrupt_cache_is_tolerated(tmp_path, monkeypatch):
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("{not valid json")
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["Unstable Harmonics", "Sol Ring"])
    assert out == {"Unstable Harmonics": "Rhystic Study", "Sol Ring": "Sol Ring"}


def test_save_failure_warns_to_stderr(tmp_path, monkeypatch, capsys):
    """An unwritable cache must not raise, but must tell the user — silence
    means every future run re-pays the Scryfall round-trip with no clue why."""
    blocker = tmp_path / "blocker"
    blocker.write_text("")  # a file where a directory is needed → mkdir raises
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(blocker))

    alt_name._save_disk_cache({"New Reskin": "Real Card"})

    err = capsys.readouterr().err
    assert "warning:" in err
    assert str(blocker) in err


def test_save_failure_warns_only_once_per_process(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(blocker))

    alt_name._save_disk_cache({"New Reskin": "Real Card"})
    alt_name._save_disk_cache({"New Reskin": "Real Card"})

    assert capsys.readouterr().err.count("warning:") == 1


def test_save_success_is_silent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    alt_name._save_disk_cache({"New Reskin": "Real Card"})

    assert capsys.readouterr().err == ""
    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"New Reskin": "Real Card"}


# ----- Scryfall fallback ---------------------------------------------------


def _allow_network(monkeypatch):
    monkeypatch.delenv("COD_SYNC_NO_NETWORK", raising=False)


def test_scryfall_resolves_new_reskin(tmp_path, monkeypatch):
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    def fake_lookup(names):
        assert names == ["Brand New Reskin"]
        return {"Brand New Reskin": "Older Card"}, set()

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(["Brand New Reskin"])
    assert out == {"Brand New Reskin": "Older Card"}

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"__schema__": "2", "Brand New Reskin": "Older Card"}


def test_scryfall_room_canonical_is_kept_and_cached_full(tmp_path, monkeypatch):
    """Room/split canonicals come back from the lookup layer in full "A // B"
    form (shaped by layout in `_absorb_response`); the batch layer must pass
    them through and cache them verbatim — no blind front-face strip."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda _n: ({"Bottomless Pool": "Bottomless Pool // Locker Room"}, set()),
    )

    out = alt_name.canonicalize_batch(["Bottomless Pool"])
    assert out == {"Bottomless Pool": "Bottomless Pool // Locker Room"}

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"__schema__": "2", "Bottomless Pool": "Bottomless Pool // Locker Room"}


def test_canonicalize_single_passes_through_shaped_names(tmp_path, monkeypatch):
    """Same guarantee for the single-name path."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda _n: ({"Bottomless Pool": "Bottomless Pool // Locker Room"}, set()),
    )

    assert alt_name.canonicalize("Bottomless Pool") == "Bottomless Pool // Locker Room"


def test_v2_cache_full_form_value_is_trusted_verbatim(tmp_path, monkeypatch):
    """Values in a schema-marked (v2) cache are written already shaped, so
    reads trust them as-is. This is what lets a local override map a name
    to a Room/split canonical."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        json.dumps({"__schema__": "2", "Bottomless Pool": "Bottomless Pool // Locker Room"})
    )
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["Bottomless Pool"])
    assert out == {"Bottomless Pool": "Bottomless Pool // Locker Room"}


# ----- legacy (pre-v2) cache migration --------------------------------------
#
# Caches written before layout-aware shaping stored raw Scryfall canonicals,
# so a true DFC could be cached as "Fell the Profane" ->
# "Fell the Profane // Fell Mire". Trusting that verbatim wrote the full name
# into the .cod — a name Cockatrice's database doesn't key (modal_dfc is
# stored by front face). Layouts aren't stored in the cache, so legacy
# full-form values can't be re-shaped offline; they're dropped on load and
# re-resolve through the layout-aware Scryfall path on next use.


def test_legacy_cache_poisoned_dfc_value_is_not_trusted(tmp_path, monkeypatch):
    """Regression: the poisoned legacy entry must not reach the output —
    offline, the dropped name falls back to identity (the front face the
    fetcher already delivered)."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"Fell the Profane": "Fell the Profane // Fell Mire"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["Fell the Profane"])
    assert out == {"Fell the Profane": "Fell the Profane"}


def test_legacy_cache_migration_keeps_reskins_and_stamps_file(tmp_path, monkeypatch):
    """Migration drops only full-form values; reskin entries survive, and the
    healed file is written back with the schema marker so the drop runs once."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        json.dumps(
            {
                "Fell the Profane": "Fell the Profane // Fell Mire",
                "Unstable Harmonics": "Local Override",
            }
        )
    )
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Local Override"}

    cached = json.loads(cache_path.read_text())
    assert cached == {"__schema__": "2", "Unstable Harmonics": "Local Override"}


def test_legacy_dropped_entry_reresolves_through_scryfall(tmp_path, monkeypatch):
    """Online, a dropped legacy entry re-resolves through the layout-aware
    lookup and the corrected (shaped) value is cached."""
    _allow_network(monkeypatch)
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"Fell the Profane": "Fell the Profane // Fell Mire"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda _n: ({"Fell the Profane": "Fell the Profane"}, set()),  # modal_dfc → front face
    )

    out = alt_name.canonicalize_batch(["Fell the Profane"])
    assert out == {"Fell the Profane": "Fell the Profane"}

    cached = json.loads(cache_path.read_text())
    assert cached == {"__schema__": "2", "Fell the Profane": "Fell the Profane"}


def test_migrated_cache_keeps_newly_learned_full_form_values(tmp_path, monkeypatch):
    """The marker must protect post-migration entries: a legitimately learned
    Room canonical survives a fresh process load instead of being re-dropped."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda _n: ({"Bottomless Pool": "Bottomless Pool // Locker Room"}, set()),
    )
    assert alt_name.canonicalize("Bottomless Pool") == "Bottomless Pool // Locker Room"

    # New process, offline: the cached full-form value must still be trusted.
    alt_name._reset_state_for_tests()
    monkeypatch.setenv("COD_SYNC_NO_NETWORK", "1")
    out = alt_name.canonicalize_batch(["Bottomless Pool"])
    assert out == {"Bottomless Pool": "Bottomless Pool // Locker Room"}


def test_scryfall_not_found_caches_identity(tmp_path, monkeypatch):
    """A definitive Scryfall not-found caches the identity so we don't
    re-query the same unknown card on every sync."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup", lambda _n: ({}, {"Garbage Name"})
    )

    out = alt_name.canonicalize_batch(["Garbage Name"])
    assert out == {"Garbage Name": "Garbage Name"}

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"__schema__": "2", "Garbage Name": "Garbage Name"}


def test_transient_failure_is_not_cached(tmp_path, monkeypatch):
    """A name missing from both `resolved` and `not_found` means the request
    itself failed (timeout, 5xx). Fall back to identity for this run but do
    NOT cache it — caching would permanently mask a reskin behind one blip."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    calls = [0]

    def fake_lookup(names):
        calls[0] += 1
        return {}, set()  # transport failure: nothing resolved, nothing definitive

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(["Flaky Card"])
    assert out == {"Flaky Card": "Flaky Card"}
    assert not (tmp_path / "cod-sync" / "alt_names.json").exists()

    # Next run retries instead of trusting a poisoned identity entry.
    alt_name.canonicalize_batch(["Flaky Card"])
    assert calls[0] == 2


def test_full_form_not_found_retries_by_front_half(tmp_path, monkeypatch):
    """Scryfall's collection endpoint doesn't match full "A // B" names —
    they come back not_found. The batch layer retries those by front half,
    which resolves the card and its layout, so the shaped canonical comes
    back regardless of which form the caller passed in."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    lookups: list[list[str]] = []

    def fake_lookup(names):
        lookups.append(sorted(names))
        if any(" // " in n for n in names):
            # First pass: full forms are never matched by the endpoint.
            return {}, set(names)
        # Retry pass: half-names resolve, shaped by layout.
        out = {}
        if "Storm the Vault" in names:
            out["Storm the Vault"] = "Storm the Vault"  # transform → front face
        if "Bottomless Pool" in names:
            out["Bottomless Pool"] = "Bottomless Pool // Locker Room"  # split → full
        return out, set(names) - set(out)

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(
        ["Storm the Vault // Vault of Catlacan", "Bottomless Pool // Locker Room"]
    )
    assert out == {
        "Storm the Vault // Vault of Catlacan": "Storm the Vault",
        "Bottomless Pool // Locker Room": "Bottomless Pool // Locker Room",
    }
    assert len(lookups) == 2
    assert lookups[1] == ["Bottomless Pool", "Storm the Vault"]

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {
        "__schema__": "2",
        "Storm the Vault // Vault of Catlacan": "Storm the Vault",
        "Bottomless Pool // Locker Room": "Bottomless Pool // Locker Room",
    }


def test_full_form_unknown_on_both_passes_caches_identity(tmp_path, monkeypatch):
    """A full-form name whose front half is also unknown is a definitive
    miss: identity, cached."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", lambda names: ({}, set(names)))

    out = alt_name.canonicalize_batch(["Made Up // Card"])
    assert out == {"Made Up // Card": "Made Up // Card"}

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"__schema__": "2", "Made Up // Card": "Made Up // Card"}


def test_seed_short_circuits_scryfall(tmp_path, monkeypatch):
    """Bundled seed entries never go to the network."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    called = []
    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda names: called.append(names) or ({}, set()),
    )

    out = alt_name.canonicalize_batch(["Unstable Harmonics"])
    assert out == {"Unstable Harmonics": "Rhystic Study"}
    assert called == []
    # Seed lookups don't bloat the disk cache either.
    assert not (tmp_path / "cod-sync" / "alt_names.json").exists()


def test_scryfall_mixed_seed_and_unknown(tmp_path, monkeypatch):
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    def fake_lookup(names):
        assert set(names) == {"Mystery", "Counterspell"}
        return {"Mystery": "Real Mystery"}, {"Counterspell"}

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(["Unstable Harmonics", "Mystery", "Counterspell"])
    assert out == {
        "Unstable Harmonics": "Rhystic Study",
        "Mystery": "Real Mystery",
        "Counterspell": "Counterspell",
    }

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    # Cache holds the LEARNED entries only — seed is not duplicated.
    assert cached == {
        "__schema__": "2",
        "Mystery": "Real Mystery",
        "Counterspell": "Counterspell",
    }


def test_second_sync_hits_cache_not_scryfall(tmp_path, monkeypatch):
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    call_count = [0]

    def fake_lookup(names):
        call_count[0] += 1
        return {n: n for n in names}, set()

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    alt_name.canonicalize_batch(["Unknown A", "Unknown B"])
    alt_name.canonicalize_batch(["Unknown A", "Unknown B"])

    assert call_count[0] == 1


# ----- thread safety -------------------------------------------------------


def test_concurrent_canonicalize_is_thread_safe(tmp_path, monkeypatch):
    """Concurrent lookups that learn new entries must not corrupt the cache.

    Pre-lock, a thread serializing the cache dict in `_save_disk_cache` races
    another thread's `disk[name] = canonical` mutation and `json.dump` raises
    RuntimeError (dict changed size during iteration), which nothing catches.
    """
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    def fake_lookup(names):
        time.sleep(0.001)  # widen the miss -> mutate+save race window
        return {n: n.replace("Skin", "Canon") for n in names}, set()

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    names = [f"Skin {i}" for i in range(80)]
    n_threads = 8
    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []

    def worker(offset: int) -> None:
        barrier.wait()
        try:
            for i in range(40):
                n = names[(offset + i) % len(names)]
                assert alt_name.canonicalize(n) == n.replace("Skin", "Canon")
            out = alt_name.canonicalize_batch(names)
            assert out == {n: n.replace("Skin", "Canon") for n in names}
        except BaseException as exc:  # noqa: BLE001 - re-raised in main thread
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(k * 11,)) for k in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    # Cache file must be parseable, consistent JSON — no torn writes.
    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached.pop("__schema__") == "2"
    assert all(cached[k] == k.replace("Skin", "Canon") for k in cached)


def test_disk_cache_lazy_init_is_single_object(tmp_path, monkeypatch):
    """Threads racing the lazy load must all see the same cache dict —
    otherwise entries learned through one copy are lost from the other."""
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    n_threads = 16
    barrier = threading.Barrier(n_threads)
    results: list[dict[str, str]] = []

    def worker() -> None:
        barrier.wait()
        results.append(alt_name._get_disk_cache())

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == n_threads
    assert len({id(r) for r in results}) == 1


# ----- response matching ---------------------------------------------------


def test_absorb_response_matches_in_order():
    resolved: dict[str, str] = {}
    not_found: set[str] = set()
    chunk = ["A flavor", "B normal", "C bogus", "D normal"]
    data = {
        "data": [
            {"name": "A canonical"},
            {"name": "B normal"},
            {"name": "D normal"},
        ],
        "not_found": [{"name": "C bogus"}],
    }
    alt_name._absorb_response(chunk, data, resolved, not_found)
    assert resolved == {
        "A flavor": "A canonical",
        "B normal": "B normal",
        "D normal": "D normal",
    }
    assert not_found == {"C bogus"}


def test_absorb_response_handles_empty_response():
    resolved: dict[str, str] = {}
    not_found: set[str] = set()
    alt_name._absorb_response(["A"], {}, resolved, not_found)
    assert resolved == {}
    assert not_found == set()


def test_absorb_response_shapes_by_layout():
    """Scryfall card objects carry `layout`; the canonical name is shaped
    with it — transform/modal DFCs reduce to the front face, split-style
    cards (Rooms, aftermath) keep the full name."""
    resolved: dict[str, str] = {}
    not_found: set[str] = set()
    chunk = ["Dowsing Dagger", "Bottomless Pool", "Dusk"]
    data = {
        "data": [
            {"name": "Dowsing Dagger // Lost Vale of Pahz", "layout": "transform"},
            {"name": "Bottomless Pool // Locker Room", "layout": "split"},
            {"name": "Dusk // Dawn", "layout": "aftermath"},
        ],
    }
    alt_name._absorb_response(chunk, data, resolved, not_found)
    assert resolved == {
        "Dowsing Dagger": "Dowsing Dagger",
        "Bottomless Pool": "Bottomless Pool // Locker Room",
        "Dusk": "Dusk // Dawn",
    }


def test_absorb_response_missing_layout_strips_to_front_face():
    """No layout field → fall back to the historical DFC strip."""
    resolved: dict[str, str] = {}
    not_found: set[str] = set()
    data = {"data": [{"name": "Dowsing Dagger // Lost Vale of Pahz"}]}
    alt_name._absorb_response(["Dowsing Dagger"], data, resolved, not_found)
    assert resolved == {"Dowsing Dagger": "Dowsing Dagger"}


# ----- direct Scryfall HTTP layer (mocked) ---------------------------------


def test_scryfall_lookup_swallows_network_error(monkeypatch):
    import requests

    class BoomSession:
        def post(self, *_a, **_k):
            raise requests.ConnectionError("offline")

    monkeypatch.setattr("cod_sync.alt_name._get_session", lambda: BoomSession())
    assert alt_name._scryfall_batch_lookup(["X"]) == ({}, set())


def test_scryfall_lookup_handles_bad_json(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not json")

    class FakeSession:
        def post(self, *_a, **_k):
            return FakeResp()

    monkeypatch.setattr("cod_sync.alt_name._get_session", lambda: FakeSession())
    assert alt_name._scryfall_batch_lookup(["X"]) == ({}, set())
