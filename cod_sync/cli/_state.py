"""Shared CLI runtime state.

Centralizes the quiet-mode flag and the ``say()`` helper so every cli
submodule reads from the same module-level binding. Submodules MUST
reach the flag through this module (``_state._QUIET`` / ``_state.say``)
so that ``main()``'s write at startup is visible everywhere.
"""
from __future__ import annotations

# Module-level quiet state — single-shot CLI, so threading `quiet: bool`
# through ~10 function signatures would be churn for no benefit. Errors
# (anything going to sys.stderr) ignore this flag.
_QUIET = False


def say(msg: str = "") -> None:
    """Print informational output unless --quiet is set."""
    if not _QUIET:
        print(msg)
