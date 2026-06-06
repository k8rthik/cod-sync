"""Tests for the no-subcommand smart dispatch in `cod-sync`."""
from __future__ import annotations

import os

import pytest

from cod_sync import cli


URL = "https://www.moxfield.com/decks/abc123"


def test_passes_through_explicit_sync():
    out = cli._maybe_inject_subcommand(["sync", "foo.cod", URL])
    assert out == ["sync", "foo.cod", URL]


def test_passes_through_explicit_import():
    out = cli._maybe_inject_subcommand(["import", "foo.cod", URL])
    assert out == ["import", "foo.cod", URL]


def test_passes_through_explicit_dir():
    out = cli._maybe_inject_subcommand(["dir", "/some/path"])
    assert out == ["dir", "/some/path"]


def test_passes_through_help_only():
    assert cli._maybe_inject_subcommand(["--help"]) == ["--help"]
    assert cli._maybe_inject_subcommand(["-h"]) == ["-h"]
    assert cli._maybe_inject_subcommand([]) == []


def test_passes_through_single_positional():
    """One positional is ambiguous; let argparse complain."""
    assert cli._maybe_inject_subcommand(["solo"]) == ["solo"]


def test_routes_to_sync_when_file_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.cod").write_text("<x/>", encoding="utf-8")

    out = cli._maybe_inject_subcommand(["real.cod", URL])
    assert out == ["sync", "real.cod", URL]


def test_routes_to_import_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = cli._maybe_inject_subcommand(["nope.cod", URL])
    assert out == ["import", "nope.cod", URL]


def test_auto_appends_cod_suffix_for_sync(tmp_path, monkeypatch):
    """`cod-sync mydeck URL` finds `mydeck.cod` and dispatches sync."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mydeck.cod").write_text("<x/>", encoding="utf-8")

    out = cli._maybe_inject_subcommand(["mydeck", URL])
    assert out == ["sync", "mydeck.cod", URL]


def test_auto_appends_cod_suffix_for_import(tmp_path, monkeypatch):
    """`cod-sync newdeck URL` becomes `import newdeck.cod URL` when nothing exists."""
    monkeypatch.chdir(tmp_path)

    out = cli._maybe_inject_subcommand(["newdeck", URL])
    assert out == ["import", "newdeck.cod", URL]


def test_preserves_cod_suffix_when_already_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out = cli._maybe_inject_subcommand(["new.cod", URL])
    assert out == ["import", "new.cod", URL]


def test_flags_pass_through_for_sync(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.cod").write_text("<x/>", encoding="utf-8")

    out = cli._maybe_inject_subcommand(["real.cod", URL, "--yes"])
    assert out == ["sync", "real.cod", URL, "--yes"]


def test_flags_pass_through_for_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out = cli._maybe_inject_subcommand(["fresh", URL, "-n"])
    assert out == ["import", "fresh.cod", URL, "-n"]


def test_leading_flag_does_not_break_dispatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.cod").write_text("<x/>", encoding="utf-8")

    out = cli._maybe_inject_subcommand(["-y", "real.cod", URL])
    assert out == ["sync", "-y", "real.cod", URL]


def test_end_to_end_routes_through_main_to_sync(tmp_path, monkeypatch):
    """main() dispatches the rewritten argv to run_sync."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "real.cod").write_text("<x/>", encoding="utf-8")

    called: dict = {}

    def fake_run_sync(cod_path, source, *, yes, dry_run):
        called["cod_path"] = cod_path
        called["source"] = source
        called["yes"] = yes
        called["dry_run"] = dry_run
        return 0

    monkeypatch.setattr("cod_sync.cli.run_sync", fake_run_sync)

    rc = cli.main(["real.cod", URL, "--yes"])

    assert rc == 0
    assert called == {
        "cod_path": "real.cod",
        "source": URL,
        "yes": True,
        "dry_run": False,
    }


def test_end_to_end_routes_through_main_to_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    called: dict = {}

    def fake_run_import(cod_path, source, *, yes, dry_run):
        called["cod_path"] = cod_path
        called["source"] = source
        called["yes"] = yes
        called["dry_run"] = dry_run
        return 0

    monkeypatch.setattr("cod_sync.cli.run_import", fake_run_import)

    rc = cli.main(["fresh", URL, "-y"])

    assert rc == 0
    assert called == {
        "cod_path": "fresh.cod",
        "source": URL,
        "yes": True,
        "dry_run": False,
    }
