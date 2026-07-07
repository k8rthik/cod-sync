"""The committed man page must match what the generator produces.

``man/cod-sync.1`` is generated from the argparse parser in ``cod_sync.cli``
(see ``scripts/gen_manpage.py``). This test regenerates it and compares, so a
flag or help-text change that forgets to regen fails here instead of shipping
a stale man page. Skips cleanly when the ``argparse-manpage`` dev dependency
isn't installed.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_MANPAGE = _ROOT / "man" / "cod-sync.1"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("argparse_manpage") is None,
    reason="argparse-manpage not installed (dev dependency)",
)

# The .TH header carries the version string; normalize it away so a bare
# version bump doesn't fail this check — only flag/help drift should.
_TH_RE = re.compile(r"^\.TH .*$", re.MULTILINE)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "gen_manpage", _ROOT / "scripts" / "gen_manpage.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize(text: str) -> str:
    return _TH_RE.sub(".TH", text)


def test_committed_manpage_matches_generator():
    generated = _load_generator().render()
    committed = _MANPAGE.read_text(encoding="utf-8")
    assert _normalize(committed) == _normalize(generated), (
        "man/cod-sync.1 is stale — regenerate with `python scripts/gen_manpage.py`"
    )
