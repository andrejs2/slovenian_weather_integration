"""API request tracking for the ARSO Weather integration.

Provides transparent counting of HTTP requests per domain, with rolling
hourly windows for rate monitoring. Used by diagnostic sensors to expose
API traffic in the Home Assistant UI.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlparse

_LOGGER = logging.getLogger(__name__)

# Domains we track individually; everything else is grouped as "other"
_KNOWN_DOMAINS = frozenset({
    "vreme.arso.gov.si",
    "meteo.arso.gov.si",
    "www.arso.gov.si",
})


@dataclass
class ApiTracker:
    """Track HTTP request counts per domain with rolling hourly window."""

    _requests: dict[str, int] = field(default_factory=dict)
    _errors: dict[str, int] = field(default_factory=dict)
    _timestamps: deque[tuple[datetime, str]] = field(default_factory=deque)
    _error_timestamps: deque[tuple[datetime, str]] = field(
        default_factory=deque
    )
    _start_time: datetime = field(default_factory=datetime.now)

    @staticmethod
    def _domain_from_url(url: str) -> str:
        """Extract hostname from URL, or 'unknown'."""
        return urlparse(url).hostname or "unknown"

    def record_request(self, url: str) -> None:
        """Record a successful HTTP request."""
        domain = self._domain_from_url(url)
        self._requests[domain] = self._requests.get(domain, 0) + 1
        self._timestamps.append((datetime.now(), domain))

    def record_error(self, url: str) -> None:
        """Record a failed HTTP request."""
        domain = self._domain_from_url(url)
        self._errors[domain] = self._errors.get(domain, 0) + 1
        self._error_timestamps.append((datetime.now(), domain))

    def _cleanup(self) -> None:
        """Remove timestamps older than 1 hour."""
        cutoff = datetime.now() - timedelta(hours=1)
        while self._timestamps and self._timestamps[0][0] < cutoff:
            self._timestamps.popleft()
        while self._error_timestamps and self._error_timestamps[0][0] < cutoff:
            self._error_timestamps.popleft()

    @property
    def requests_per_hour(self) -> int:
        """Return number of requests in the last 60 minutes."""
        self._cleanup()
        return len(self._timestamps)

    @property
    def errors_per_hour(self) -> int:
        """Return number of errors in the last 60 minutes."""
        self._cleanup()
        return len(self._error_timestamps)

    @property
    def total_requests(self) -> int:
        """Return cumulative request count since startup."""
        return sum(self._requests.values())

    @property
    def total_errors(self) -> int:
        """Return cumulative error count since startup."""
        return sum(self._errors.values())

    @property
    def requests_by_domain(self) -> dict[str, int]:
        """Return cumulative request counts keyed by domain."""
        return dict(self._requests)

    @property
    def errors_by_domain(self) -> dict[str, int]:
        """Return cumulative error counts keyed by domain."""
        return dict(self._errors)

    @property
    def hourly_by_domain(self) -> dict[str, int]:
        """Return last-hour request counts keyed by domain."""
        self._cleanup()
        result: dict[str, int] = {}
        for _, domain in self._timestamps:
            result[domain] = result.get(domain, 0) + 1
        return result

    @property
    def uptime_hours(self) -> float:
        """Return hours since tracker was created."""
        delta = datetime.now() - self._start_time
        return round(delta.total_seconds() / 3600, 1)


class _TrackedContextManager:
    """Async context manager wrapper that records requests in ApiTracker."""

    __slots__ = ("_cm", "_url", "_tracker", "_entered")

    def __init__(self, cm, url: str, tracker: ApiTracker) -> None:
        self._cm = cm
        self._url = url
        self._tracker = tracker
        self._entered = False

    async def __aenter__(self):
        self._tracker.record_request(self._url)
        self._entered = True
        try:
            return await self._cm.__aenter__()
        except Exception:
            self._tracker.record_error(self._url)
            raise

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._tracker.record_error(self._url)
        return await self._cm.__aexit__(exc_type, exc_val, exc_tb)


class TrackedClientSession:
    """Wrapper around aiohttp.ClientSession that counts requests per domain.

    Only intercepts ``.get()`` (the only HTTP method this integration uses).
    All other attributes are delegated to the underlying session.
    """

    __slots__ = ("_session", "_tracker")

    def __init__(self, session, tracker: ApiTracker) -> None:
        self._session = session
        self._tracker = tracker

    def get(self, url, **kwargs):
        """Wrap session.get() with request tracking."""
        return _TrackedContextManager(
            self._session.get(url, **kwargs), url, self._tracker
        )

    def __getattr__(self, name):
        """Delegate everything else to the real session."""
        return getattr(self._session, name)
