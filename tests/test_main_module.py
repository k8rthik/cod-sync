"""`python -m cod_sync` must propagate main()'s exit code.

The `cod-sync` console script gets this for free — the entry-point
wrapper calls `sys.exit(main())` — but the module form has to do it
explicitly in `__main__.py`. Exit codes are documented CLI contract,
so the regression test runs the real interpreter in a subprocess.
"""

from __future__ import annotations

import os
import subprocess
import sys


def _run_module(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, COD_SYNC_NO_NETWORK="1")
    return subprocess.run(
        [sys.executable, "-m", "cod_sync", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_error_exit_code_propagates(tmp_path):
    """A missing deck file with no URL is a usage error: exit code 2."""
    result = _run_module(["missing.cod"], cwd=str(tmp_path))
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "doesn't exist" in result.stderr


def test_success_exit_code_is_zero(tmp_path):
    """Walking an empty directory succeeds: exit code 0."""
    result = _run_module([str(tmp_path)], cwd=str(tmp_path))
    assert result.returncode == 0, (result.stdout, result.stderr)
