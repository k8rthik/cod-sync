"""Tests for the positional-arg dispatch layer.

We don't exercise the inner flow functions here — they have their own test
files. The job of these tests is: given an `argv`, did `main()` route to the
right function with the right arguments?
"""
from __future__ import annotations

import pytest

from cod_sync import cli


URL = "https://www.moxfield.com/decks/abc123"
URL2 = "https://archidekt.com/decks/999"


class _Spy:
    """Capture the args main() routed through to a flow function."""

    def __init__(self):
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return 0


@pytest.fixture
def spies(monkeypatch):
    walk, sync_file, bare = _Spy(), _Spy(), _Spy()
    monkeypatch.setattr("cod_sync.cli._walk_directory", walk)
    monkeypatch.setattr("cod_sync.cli._sync_file", sync_file)
    monkeypatch.setattr("cod_sync.cli._create_from_bare_url", bare)
    return {"walk": walk, "sync_file": sync_file, "bare": bare}


def test_bare_invocation_walks_cwd(spies):
    rc = cli.main([])
    assert rc == 0
    assert spies["walk"].calls == [((".",), {"recursive": False, "yes": False, "dry_run": False})]


def test_directory_target_walks_that_dir(tmp_path, spies):
    rc = cli.main([str(tmp_path)])
    assert rc == 0
    assert spies["walk"].calls[0][0] == (str(tmp_path),)


def test_recursive_flag_passes_through(tmp_path, spies):
    cli.main([str(tmp_path), "-r"])
    assert spies["walk"].calls[0][1]["recursive"] is True


def test_directory_plus_url_is_an_error(tmp_path, spies, capsys):
    rc = cli.main([str(tmp_path), URL])
    assert rc == 2
    assert "can't sync a directory" in capsys.readouterr().err
    assert spies["walk"].calls == []


def test_two_urls_is_an_error(spies, capsys):
    rc = cli.main([URL, URL2])
    assert rc == 2
    assert "two URLs" in capsys.readouterr().err
    assert spies["bare"].calls == []


def test_file_plus_url_routes_to_sync_file(tmp_path, monkeypatch, spies):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.cod").write_text("<x/>", encoding="utf-8")

    cli.main(["foo.cod", URL])
    args, _ = spies["sync_file"].calls[0]
    assert args == ("foo.cod", URL)


def test_resolves_bare_name_to_cod_suffix(tmp_path, monkeypatch, spies):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mydeck.cod").write_text("<x/>", encoding="utf-8")

    cli.main(["mydeck", URL])
    args, _ = spies["sync_file"].calls[0]
    assert args == ("mydeck.cod", URL)


def test_existing_file_without_url_routes_to_sync_file(tmp_path, monkeypatch, spies):
    """The URL fallback lives inside _sync_file, not the router. The router
    just dispatches as long as the file exists, even without a URL."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.cod").write_text("<x/>", encoding="utf-8")

    cli.main(["foo.cod"])
    args, _ = spies["sync_file"].calls[0]
    assert args == ("foo.cod", None)


def test_missing_file_without_url_errors(tmp_path, monkeypatch, spies, capsys):
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["nope.cod"])
    assert rc == 2
    assert "doesn't exist" in capsys.readouterr().err
    assert spies["sync_file"].calls == []


def test_bare_url_routes_to_create_from_bare_url(spies):
    cli.main([URL])
    args, _ = spies["bare"].calls[0]
    assert args == (URL,)


def test_yes_and_dry_run_flags_pass_through(tmp_path, monkeypatch, spies):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "foo.cod").write_text("<x/>", encoding="utf-8")

    cli.main(["foo.cod", URL, "--yes", "--dry-run"])
    _, kw = spies["sync_file"].calls[0]
    assert kw == {"yes": True, "dry_run": True}


def test_short_flags_pass_through(spies):
    cli.main([URL, "-y", "-n"])
    _, kw = spies["bare"].calls[0]
    assert kw == {"yes": True, "dry_run": True}
