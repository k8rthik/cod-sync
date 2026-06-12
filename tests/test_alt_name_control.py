"""Provenance-aware resolution and user overrides in `alt_name`.

`canonicalize_batch_detailed` reports whether each mapping is settled
(already in the disk cache — user-confirmed or previously learned) so
the CLI can prompt once per new mapping. `set_override` persists a
user's decision to the disk cache, which wins over the bundled seed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cod_sync import alt_name

FLAVOR = "Unstable Harmonics"
CANONICAL = "Rhystic Study"


def _cache_file() -> Path:
    return Path(os.environ["COD_SYNC_CACHE_DIR"]) / "cod-sync" / "alt_names.json"


def test_seed_mapping_is_unsettled_on_fresh_cache():
    res = alt_name.canonicalize_batch_detailed([FLAVOR])[FLAVOR]
    assert res.canonical == CANONICAL
    assert res.settled is False


def test_unknown_name_is_unsettled_identity():
    res = alt_name.canonicalize_batch_detailed(["Sol Ring"])["Sol Ring"]
    assert res.canonical == "Sol Ring"
    assert res.settled is False


def test_set_override_settles_the_mapping():
    alt_name.set_override(FLAVOR, CANONICAL)
    res = alt_name.canonicalize_batch_detailed([FLAVOR])[FLAVOR]
    assert res.canonical == CANONICAL
    assert res.settled is True


def test_set_override_wins_over_seed():
    alt_name.set_override(FLAVOR, "My Custom Name")
    assert alt_name.canonicalize(FLAVOR) == "My Custom Name"


def test_set_override_persists_with_schema_marker():
    alt_name.set_override(FLAVOR, CANONICAL)
    data = json.loads(_cache_file().read_text())
    assert data["__schema__"] == "2"
    assert data[FLAVOR] == CANONICAL


def test_set_override_rejects_empty_values():
    with pytest.raises(ValueError):
        alt_name.set_override("", CANONICAL)
    with pytest.raises(ValueError):
        alt_name.set_override(FLAVOR, "")


def test_canonicalize_batch_matches_detailed():
    detailed = alt_name.canonicalize_batch_detailed([FLAVOR, "Sol Ring"])
    flat = alt_name.canonicalize_batch([FLAVOR, "Sol Ring"])
    assert flat == {name: res.canonical for name, res in detailed.items()}
