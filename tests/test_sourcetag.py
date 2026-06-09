from cod_sync.sourcetag import get_source_url, set_source_url

URL = "https://www.moxfield.com/decks/abc123"


def test_get_returns_none_when_absent():
    assert get_source_url("") is None
    assert get_source_url("some user notes\nmore notes") is None


def test_get_finds_marker():
    assert get_source_url(f"cod-sync-source: {URL}") == URL


def test_get_ignores_marker_with_no_url():
    assert get_source_url("cod-sync-source:") is None
    assert get_source_url("cod-sync-source:   ") is None


def test_set_on_empty_comments():
    assert set_source_url("", URL) == f"cod-sync-source: {URL}"


def test_set_preserves_existing_user_notes():
    comments = "remember: cut a land\nbudget: $200"
    out = set_source_url(comments, URL)
    lines = out.splitlines()
    assert lines[0] == "remember: cut a land"
    assert lines[1] == "budget: $200"
    assert lines[2] == f"cod-sync-source: {URL}"


def test_set_replaces_existing_marker_in_place():
    comments = f"notes\ncod-sync-source: {URL}\nmore notes"
    new_url = "https://archidekt.com/decks/999"
    out = set_source_url(comments, new_url)
    assert out == f"notes\ncod-sync-source: {new_url}\nmore notes"


def test_set_dedupes_extra_markers():
    comments = "cod-sync-source: old1\ncod-sync-source: old2\nuser note"
    out = set_source_url(comments, URL)
    assert out == f"cod-sync-source: {URL}\nuser note"


def test_round_trip_get_after_set():
    out = set_source_url("hello", URL)
    assert get_source_url(out) == URL
