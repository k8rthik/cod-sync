"""Test-wide isolation for the alt_name fallback layer.

Resets module-level memoization (disk cache, HTTP session, cache path) so
env-var changes set inside a test actually take effect, then disables the
Scryfall fallback and redirects the cache to a per-test tmpdir.

Also wires the `network` marker: tests marked `@pytest.mark.network` make
real HTTP requests to third-party deck sites and are skipped by default;
set COD_SYNC_RUN_NETWORK_TESTS=1 to opt in.
"""

from __future__ import annotations

import os

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


def pytest_collection_modifyitems(config, items):
    if os.environ.get("COD_SYNC_RUN_NETWORK_TESTS") == "1":
        return
    skip = pytest.mark.skip(
        reason="network tests are opt-in; set COD_SYNC_RUN_NETWORK_TESTS=1 to run"
    )
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
