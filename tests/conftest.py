"""Test-wide isolation for the alt_name fallback layer.

By default every test runs with `COD_SYNC_NO_NETWORK=1` (so the Scryfall
fallback is skipped) and a per-test cache directory under tmp_path_factory
(so writes don't pollute the user's real `~/.cache/cod-sync/`). Tests that
exercise the network path explicitly delete the env var inside the body.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_alt_name(monkeypatch, tmp_path_factory):
    cache_dir = tmp_path_factory.mktemp("cod_sync_cache")
    monkeypatch.setenv("COD_SYNC_NO_NETWORK", "1")
    monkeypatch.setenv("COD_SYNC_CACHE_DIR", str(cache_dir))
