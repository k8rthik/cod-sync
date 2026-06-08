"""Test-wide isolation for the alt_name fallback layer.

Resets module-level memoization (disk cache, HTTP session, cache path) so
env-var changes set inside a test actually take effect, then disables the
Scryfall fallback and redirects the cache to a per-test tmpdir.
"""
from __future__ import annotations

import pytest

from cod_sync import alt_name


@pytest.fixture(autouse=True)
def _isolate_alt_name(monkeypatch, tmp_path_factory):
    alt_name._reset_state_for_tests()
    cache_dir = tmp_path_factory.mktemp("cod_sync_cache")
    monkeypatch.setenv("COD_SYNC_NO_NETWORK", "1")
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(cache_dir))
    yield
    alt_name._reset_state_for_tests()
