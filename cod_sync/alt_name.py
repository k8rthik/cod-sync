"""Reskin / flavor name normalization.

Moxfield and Archidekt return Secret Lair reskins under their printed
flavor name (e.g. "Unstable Harmonics"), but Cockatrice only recognizes
the canonical card name ("Rhystic Study"). This module maps the flavor
name to the canonical name via a bundled dictionary in `_seed_data.py`.

There is no runtime network call and no on-disk cache. The seed is
refreshed by running `scripts/refresh_seed.py` (which queries Scryfall)
and committed before each release. Cards not in the seed are treated as
canonical and passed through unchanged. Reskins that ship between
cod-sync releases are not covered until the seed is regenerated.
"""
from __future__ import annotations

from typing import Iterable

from . import _seed_data


_SEED: dict[str, str] = _seed_data.SEED


def canonicalize_batch(names: Iterable[str]) -> dict[str, str]:
    """Return `{input_name: canonical_name}` for every distinct input name.

    Names in the bundled seed map to their canonical card name. Everything
    else passes through unchanged.
    """
    return {n: _SEED.get(n, n) for n in names if n}


def canonicalize(name: str) -> str:
    """Single-name convenience wrapper around `canonicalize_batch`."""
    if not name:
        return name
    return _SEED.get(name, name)
