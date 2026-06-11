"""The change-summary header counts cards, not unique-name lines.

Importing a fresh 100-card deck with basics collapsed into `+ 4x Forest`
style lines must still report 100 changes — the per-line count undersells
what's actually being written.
"""

from __future__ import annotations

from cod_sync import diff
from cod_sync.cli import _state, formatting


def test_summary_header_counts_cards_not_lines(capsys):
    _state._QUIET = False
    changes = [
        diff.Change("add", "main", "Forest", 0, 4),
        diff.Change("add", "main", "Sol Ring", 0, 1),
        diff.Change("qty", "main", "Swamp", 1, 4),
        diff.Change("remove", "side", "Gamble", 2, 0),
    ]
    formatting._print_summary(changes)
    out = capsys.readouterr().out
    assert "10 change(s):" in out
