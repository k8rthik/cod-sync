"""Typed source-fetch errors: classification at the source boundary and
end-to-end formatting at the CLI boundary.

Covers:
  - `errors.from_http_response` per status branch.
  - moxfield + archidekt error mapping for the underlying causes
    (HTTP status, timeout, connection error, malformed JSON, malformed URL).
  - dispatcher rejection paths.
  - `_format_source_error` per leaf type.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from cod_sync import errors, sources
from cod_sync.cli import _format_source_error
from cod_sync.sources import archidekt, moxfield


def _mock_response(
    *,
    status: int,
    headers: dict[str, str] | None = None,
    json_payload: Any = None,
    raise_on_json: Exception | None = None,
) -> MagicMock:
    """Build a `requests.Response`-shaped mock with just the surface we touch."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.headers = headers or {}
    if raise_on_json is not None:
        resp.json.side_effect = raise_on_json
    else:
        resp.json.return_value = json_payload or {}
    return resp


# ----- from_http_response ---------------------------------------------------


def test_from_http_response_404_is_DeckNotFoundError():
    resp = _mock_response(status=404)
    out = errors.from_http_response("https://example/decks/x", resp)
    assert isinstance(out, errors.DeckNotFoundError)


def test_from_http_response_410_is_DeckNotFoundError():
    resp = _mock_response(status=410)
    assert isinstance(errors.from_http_response("u", resp), errors.DeckNotFoundError)


def test_from_http_response_401_is_DeckPrivateError():
    resp = _mock_response(status=401)
    assert isinstance(errors.from_http_response("u", resp), errors.DeckPrivateError)


def test_from_http_response_403_is_DeckPrivateError():
    resp = _mock_response(status=403)
    assert isinstance(errors.from_http_response("u", resp), errors.DeckPrivateError)


def test_from_http_response_429_carries_retry_after():
    resp = _mock_response(status=429, headers={"Retry-After": "12"})
    out = errors.from_http_response("u", resp)
    assert isinstance(out, errors.RateLimitedError)
    assert out.retry_after == "12"


def test_from_http_response_429_without_retry_after():
    resp = _mock_response(status=429)
    out = errors.from_http_response("u", resp)
    assert isinstance(out, errors.RateLimitedError)
    assert out.retry_after is None


def test_from_http_response_500_is_RemoteServerError():
    resp = _mock_response(status=500)
    out = errors.from_http_response("u", resp)
    assert isinstance(out, errors.RemoteServerError)
    assert out.status == 500


def test_from_http_response_503_is_RemoteServerError():
    resp = _mock_response(status=503)
    out = errors.from_http_response("u", resp)
    assert isinstance(out, errors.RemoteServerError)
    assert out.status == 503


def test_from_http_response_unclassified_is_NetworkError():
    resp = _mock_response(status=418)
    out = errors.from_http_response("u", resp)
    assert isinstance(out, errors.NetworkError)
    assert "418" in out.cause


# ----- moxfield -------------------------------------------------------------


_MOX_URL = "https://moxfield.com/decks/abc123"


def test_moxfield_bad_url_raises_InvalidSourceError():
    with pytest.raises(errors.InvalidSourceError) as exc:
        moxfield.fetch("https://moxfield.com/notadeck/")
    assert "Moxfield" in exc.value.reason


def test_moxfield_404_raises_DeckNotFoundError(monkeypatch):
    monkeypatch.setattr(moxfield.requests, "get", lambda *a, **kw: _mock_response(status=404))
    with pytest.raises(errors.DeckNotFoundError):
        moxfield.fetch(_MOX_URL)


def test_moxfield_403_raises_DeckPrivateError(monkeypatch):
    monkeypatch.setattr(moxfield.requests, "get", lambda *a, **kw: _mock_response(status=403))
    with pytest.raises(errors.DeckPrivateError):
        moxfield.fetch(_MOX_URL)


def test_moxfield_429_raises_RateLimitedError_with_retry_after(monkeypatch):
    monkeypatch.setattr(
        moxfield.requests,
        "get",
        lambda *a, **kw: _mock_response(status=429, headers={"Retry-After": "30"}),
    )
    with pytest.raises(errors.RateLimitedError) as exc:
        moxfield.fetch(_MOX_URL)
    assert exc.value.retry_after == "30"


def test_moxfield_500_raises_RemoteServerError(monkeypatch):
    monkeypatch.setattr(moxfield.requests, "get", lambda *a, **kw: _mock_response(status=502))
    with pytest.raises(errors.RemoteServerError) as exc:
        moxfield.fetch(_MOX_URL)
    assert exc.value.status == 502


def test_moxfield_timeout_raises_NetworkError(monkeypatch):
    def boom(*a: Any, **kw: Any) -> Any:
        raise requests.Timeout("read timed out")

    monkeypatch.setattr(moxfield.requests, "get", boom)
    with pytest.raises(errors.NetworkError) as exc:
        moxfield.fetch(_MOX_URL)
    assert "Timeout" in exc.value.cause


def test_moxfield_connection_error_raises_NetworkError(monkeypatch):
    def boom(*a: Any, **kw: Any) -> Any:
        raise requests.ConnectionError("dns failure")

    monkeypatch.setattr(moxfield.requests, "get", boom)
    with pytest.raises(errors.NetworkError) as exc:
        moxfield.fetch(_MOX_URL)
    assert "ConnectionError" in exc.value.cause


def test_moxfield_bad_json_raises_MalformedResponseError(monkeypatch):
    resp = _mock_response(status=200, raise_on_json=ValueError("not json"))
    monkeypatch.setattr(moxfield.requests, "get", lambda *a, **kw: resp)
    with pytest.raises(errors.MalformedResponseError):
        moxfield.fetch(_MOX_URL)


# ----- archidekt ------------------------------------------------------------


_ARCH_URL = "https://archidekt.com/decks/999/test"


def test_archidekt_bad_url_raises_InvalidSourceError():
    with pytest.raises(errors.InvalidSourceError) as exc:
        archidekt.fetch("https://archidekt.com/notadeck/")
    assert "Archidekt" in exc.value.reason


def test_archidekt_404_raises_DeckNotFoundError(monkeypatch):
    monkeypatch.setattr(archidekt.requests, "get", lambda *a, **kw: _mock_response(status=404))
    with pytest.raises(errors.DeckNotFoundError):
        archidekt.fetch(_ARCH_URL)


def test_archidekt_429_raises_RateLimitedError(monkeypatch):
    monkeypatch.setattr(archidekt.requests, "get", lambda *a, **kw: _mock_response(status=429))
    with pytest.raises(errors.RateLimitedError):
        archidekt.fetch(_ARCH_URL)


def test_archidekt_503_raises_RemoteServerError(monkeypatch):
    monkeypatch.setattr(archidekt.requests, "get", lambda *a, **kw: _mock_response(status=503))
    with pytest.raises(errors.RemoteServerError):
        archidekt.fetch(_ARCH_URL)


def test_archidekt_connection_error_raises_NetworkError(monkeypatch):
    def boom(*a: Any, **kw: Any) -> Any:
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(archidekt.requests, "get", boom)
    with pytest.raises(errors.NetworkError):
        archidekt.fetch(_ARCH_URL)


def test_archidekt_bad_json_raises_MalformedResponseError(monkeypatch):
    resp = _mock_response(status=200, raise_on_json=ValueError("html error page"))
    monkeypatch.setattr(archidekt.requests, "get", lambda *a, **kw: resp)
    with pytest.raises(errors.MalformedResponseError):
        archidekt.fetch(_ARCH_URL)


# ----- dispatcher -----------------------------------------------------------


def test_dispatcher_unsupported_host_raises_InvalidSourceError():
    with pytest.raises(errors.InvalidSourceError) as exc:
        sources.fetch("https://tappedout.net/mtg-decks/xyz/")
    assert "unsupported" in exc.value.reason.lower()


def test_dispatcher_missing_file_raises_InvalidSourceError(tmp_path):
    missing = tmp_path / "nope.txt"
    with pytest.raises(errors.InvalidSourceError):
        sources.fetch(str(missing))


# ----- formatter ------------------------------------------------------------


def test_format_DeckNotFoundError_mentions_404_and_url():
    msg = _format_source_error(errors.DeckNotFoundError("https://x/decks/1"))
    assert "404" in msg
    assert "https://x/decks/1" in msg
    assert "deleted" in msg.lower()


def test_format_DeckPrivateError_mentions_private():
    msg = _format_source_error(errors.DeckPrivateError("u"))
    assert "private" in msg.lower()


def test_format_RateLimitedError_includes_retry_after_when_present():
    msg = _format_source_error(errors.RateLimitedError("u", retry_after="60"))
    assert "429" in msg
    assert "retry-after: 60s" in msg


def test_format_RateLimitedError_omits_retry_after_when_absent():
    msg = _format_source_error(errors.RateLimitedError("u"))
    assert "429" in msg
    assert "retry-after" not in msg.lower()


def test_format_RemoteServerError_includes_status():
    msg = _format_source_error(errors.RemoteServerError("u", status=502))
    assert "502" in msg


def test_format_NetworkError_includes_cause_and_remedy():
    msg = _format_source_error(errors.NetworkError("u", cause="Timeout"))
    assert "Timeout" in msg
    assert "connection" in msg.lower()


def test_format_MalformedResponseError_suggests_filing_a_bug():
    msg = _format_source_error(errors.MalformedResponseError("u", reason="invalid JSON"))
    assert "bug" in msg.lower()


def test_format_InvalidSourceError_includes_reason():
    msg = _format_source_error(errors.InvalidSourceError("u", reason="bad host"))
    assert "invalid source" in msg.lower()
    assert "bad host" in msg
