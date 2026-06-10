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
        return {"Brand New Reskin": "Older Card"}

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(["Brand New Reskin"])
    assert out == {"Brand New Reskin": "Older Card"}

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"Brand New Reskin": "Older Card"}


def test_scryfall_dfc_canonical_is_stripped_to_front_face(tmp_path, monkeypatch):
    """Scryfall returns DFC canonicals as "Front // Back"; Cockatrice's card
    database keys on the front face only, so the alt_name layer must strip
    the back face before the name reaches the .cod or the disk cache."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda _n: {"Dowsing Dagger": "Dowsing Dagger // Lost Vale of Pahz"},
    )

    out = alt_name.canonicalize_batch(["Dowsing Dagger"])
    assert out == {"Dowsing Dagger": "Dowsing Dagger"}

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"Dowsing Dagger": "Dowsing Dagger"}


def test_canonicalize_single_strips_dfc_back_face(tmp_path, monkeypatch):
    """Same guarantee for the single-name path."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda _n: {"Dowsing Dagger": "Dowsing Dagger // Lost Vale of Pahz"},
    )

    assert alt_name.canonicalize("Dowsing Dagger") == "Dowsing Dagger"


def test_stale_disk_cache_with_dfc_full_form_is_sanitized(tmp_path, monkeypatch):
    """Users who picked up bad "Front // Back" entries before the fix get
    healed on the next sync — output is stripped even if the cache is dirty."""
    cache_path = tmp_path / "cod-sync" / "alt_names.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(json.dumps({"Dowsing Dagger": "Dowsing Dagger // Lost Vale of Pahz"}))
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    out = alt_name.canonicalize_batch(["Dowsing Dagger"])
    assert out == {"Dowsing Dagger": "Dowsing Dagger"}


def test_scryfall_404_caches_identity(tmp_path, monkeypatch):
    """Even when Scryfall returns nothing, cache the identity so we don't
    re-query the same unknown card on every sync."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", lambda _n: {})

    out = alt_name.canonicalize_batch(["Garbage Name"])
    assert out == {"Garbage Name": "Garbage Name"}

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    assert cached == {"Garbage Name": "Garbage Name"}


def test_seed_short_circuits_scryfall(tmp_path, monkeypatch):
    """Bundled seed entries never go to the network."""
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    called = []
    monkeypatch.setattr(
        "cod_sync.alt_name._scryfall_batch_lookup",
        lambda names: called.append(names) or {},
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
        return {"Mystery": "Real Mystery"}

    monkeypatch.setattr("cod_sync.alt_name._scryfall_batch_lookup", fake_lookup)

    out = alt_name.canonicalize_batch(["Unstable Harmonics", "Mystery", "Counterspell"])
    assert out == {
        "Unstable Harmonics": "Rhystic Study",
        "Mystery": "Real Mystery",
        "Counterspell": "Counterspell",
    }

    cached = json.loads((tmp_path / "cod-sync" / "alt_names.json").read_text())
    # Cache holds the LEARNED entries only — seed is not duplicated.
    assert cached == {"Mystery": "Real Mystery", "Counterspell": "Counterspell"}


def test_second_sync_hits_cache_not_scryfall(tmp_path, monkeypatch):
    _allow_network(monkeypatch)
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(tmp_path))

    call_count = [0]

    def fake_lookup(names):
        call_count[0] += 1
        return {n: n for n in names}

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
        return {n: n.replace("Skin", "Canon") for n in names}

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
    chunk = ["A flavor", "B normal", "C bogus", "D normal"]
    data = {
        "data": [
            {"name": "A canonical"},
            {"name": "B normal"},
            {"name": "D normal"},
        ],
        "not_found": [{"name": "C bogus"}],
    }
    alt_name._absorb_response(chunk, data, resolved)
    assert resolved == {
        "A flavor": "A canonical",
        "B normal": "B normal",
        "D normal": "D normal",
    }


def test_absorb_response_handles_empty_response():
    resolved: dict[str, str] = {}
    alt_name._absorb_response(["A"], {}, resolved)
    assert resolved == {}


# ----- direct Scryfall HTTP layer (mocked) ---------------------------------


def test_scryfall_lookup_swallows_network_error(monkeypatch):
    import requests

    class BoomSession:
        def post(self, *_a, **_k):
            raise requests.ConnectionError("offline")

    monkeypatch.setattr("cod_sync.alt_name._get_session", lambda: BoomSession())
    assert alt_name._scryfall_batch_lookup(["X"]) == {}


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
    assert alt_name._scryfall_batch_lookup(["X"]) == {}
