"""Typed source-fetch errors.

Every leaf class maps to a distinct user remedy; the CLI picks a
message template per type (`cli/formatting.py:_format_source_error`),
and each leaf carries just enough context (URL, HTTP status,
retry-after) for its template. `from_http_response` is the single place
HTTP status codes are classified, shared by all fetchers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests


class SourceError(Exception):
    """Base for source-fetch failures. Never raised directly."""

    def __init__(self, source: str, message: str) -> None:
        super().__init__(message)
        self.source = source


class InvalidSourceError(SourceError):
    """The source string is malformed, unsupported, or unreadable as input."""

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(source, f"invalid source ({reason})")
        self.reason = reason


class DeckNotFoundError(SourceError):
    """HTTP 404 / 410: deck was deleted or the URL is wrong."""

    def __init__(self, source: str) -> None:
        super().__init__(source, "deck not found")


class DeckPrivateError(SourceError):
    """HTTP 401 / 403: deck is private or requires login."""

    def __init__(self, source: str) -> None:
        super().__init__(source, "deck is private or requires login")


class RateLimitedError(SourceError):
    """HTTP 429: source is rate-limiting us. May carry a Retry-After hint."""

    def __init__(self, source: str, retry_after: str | None = None) -> None:
        super().__init__(source, "rate limited")
        self.retry_after = retry_after


class RemoteServerError(SourceError):
    """HTTP 5xx: the source site is having issues, not our fault."""

    def __init__(self, source: str, status: int) -> None:
        super().__init__(source, f"server error (HTTP {status})")
        self.status = status


class NetworkError(SourceError):
    """Connection refused, DNS failure, timeout, or unclassified HTTP code."""

    def __init__(self, source: str, cause: str) -> None:
        super().__init__(source, f"network error ({cause})")
        self.cause = cause


class MalformedResponseError(SourceError):
    """Response body could not be parsed or is missing required fields."""

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(source, f"malformed response ({reason})")
        self.reason = reason


def from_http_response(url: str, resp: requests.Response) -> SourceError:
    """Map a non-2xx HTTP response onto the right typed error.

    Single point of truth for status-code classification; both source
    fetchers route here so their behavior stays in sync.
    """
    status = resp.status_code
    if status in (404, 410):
        return DeckNotFoundError(url)
    if status in (401, 403):
        return DeckPrivateError(url)
    if status == 429:
        return RateLimitedError(url, retry_after=resp.headers.get("Retry-After"))
    if 500 <= status < 600:
        return RemoteServerError(url, status=status)
    return NetworkError(url, cause=f"HTTP {status}")
