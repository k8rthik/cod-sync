"""--version / -V prints the package version and exits cleanly."""
from __future__ import annotations

import pytest

from cod_sync import __version__, cli


def test_version_flag_prints_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert f"cod-sync {__version__}" in out


def test_short_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["-V"])
    assert excinfo.value.code == 0
    assert __version__ in capsys.readouterr().out
