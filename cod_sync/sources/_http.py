"""Shared keep-alive HTTP session for the deck fetchers.

`requests` is imported lazily on first network use, and one session is
shared so a directory walk reuses the TCP+TLS connection across decks —
see ARCHITECTURE.md ("Latency design") for the numbers. The lock guards
lazy construction only; `requests.Session` is itself safe for
concurrent requests.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests

_USER_AGENT = "cod-sync/0.1 (+local CLI for personal use)"

_lock = threading.Lock()
_session: requests.Session | None = None


def get_session() -> requests.Session:
    """Return the process-wide session, constructing it on first use."""
    global _session
    with _lock:
        if _session is None:
            import requests  # deferred: only network paths pay the import

            s = requests.Session()
            s.headers.update({"User-Agent": _USER_AGENT, "Accept": "application/json"})
            _session = s
        return _session


def _reset_state_for_tests() -> None:
    """Drop the memoized session. Call between pytest tests."""
    global _session
    with _lock:
        if _session is not None:
            try:
                _session.close()
            except Exception:
                pass
            _session = None
