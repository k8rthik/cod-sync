"""Test-wide isolation: keep alt_name from hitting Scryfall or the real cache.

By default every test runs with `COD_SYNC_NO_NETWORK=1` and a per-test
cache directory pointed at `tmp_path_factory`. Tests that exercise the
Scryfall path explicitly opt back in by deleting the env var inside the
test body.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_alt_name(monkeypatch, tmp_path_factory):
    cache_dir = tmp_path_factory.mktemp("cod_sync_cache")
    monkeypatch.setenv("COD_SYNC_NO_NETWORK", "1")
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(cache_dir))
