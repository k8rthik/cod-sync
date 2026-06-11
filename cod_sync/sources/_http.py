"""Shared keep-alive HTTP session for the deck fetchers.

Two latency concerns live here:

- `requests` costs ~75ms to import — more than half of total CLI startup.
  Importing it lazily on first network use means invocations that never
  fetch (--info, --version, --help, declined prompts) don't pay for it.
- A directory walk fetches many decks from the same host. Sharing one
  session reuses the TCP+TLS connection across decks instead of paying a
  fresh handshake per deck.

Thread safety mirrors `alt_name`: the lock guards lazy construction only;
`requests.Session` is itself safe for concurrent requests.
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
