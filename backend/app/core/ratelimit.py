"""Per-process rate limiting and login lockout (Phase 7).

**In memory on purpose.** The app runs as a single worker - the APScheduler jobs live in the same
process (see `app/jobs/scheduler.py`), so a dict behind a lock is a real limit and not a
decoration. Running more than one worker would make each of them count separately, which is why
Milestone 2 replaces this with Redis; until then, one worker is a deployment requirement and it is
documented as one.

Two different things live here:

* **A sliding window** for request volume, keyed by IP or by user id. Sliding, not fixed-bucket,
  so a burst across a minute boundary cannot buy twice the limit.
* **A lockout** for consecutive failed logins against one email. This is not a rate limit - it is
  the answer to "the attacker knows the email and will try a thousand passwords slowly". A success
  clears it; only failures count.

The client address is `request.client.host` and never `X-Forwarded-For`: a header any caller can
set would let one attacker pose as a million, which is worse than having no limit at all. Behind a
real proxy, set the trusted-proxy handling deliberately rather than trusting the header here.
"""

import threading
import time
from collections import deque

from fastapi import Depends, Request

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.models import User

WINDOW_SECONDS = 60.0


class _Windows:
    """Timestamps of recent hits, per key, pruned to the window."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, now: float, window: float = WINDOW_SECONDS) -> int:
        """Record a hit. Returns 0 when it fits, or the seconds to wait before retrying."""
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            cutoff = now - window
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= limit:
                # The oldest hit is what frees a slot, so the wait is exactly until it ages out.
                return max(1, int(hits[0] + window - now) + 1)
            hits.append(now)
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class _Lockout:
    """Consecutive failed logins per email, with a cooldown once the threshold is crossed."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = {}

    def locked_for(self, email: str, now: float) -> int:
        """Seconds remaining on the lockout, or 0 when the account may try again."""
        with self._lock:
            failures = self._failures.get(email)
            if not failures:
                return 0
            if len(failures) < settings.LOGIN_FAILURES_BEFORE_LOCKOUT:
                return 0
            release_at = failures[-1] + settings.LOGIN_LOCKOUT_MINUTES * 60
            return max(0, int(release_at - now) + 1) if release_at > now else 0

    def record_failure(self, email: str, now: float) -> None:
        with self._lock:
            failures = self._failures.setdefault(email, [])
            # Only the failures that still matter: a wrong password last week is not a signal.
            cutoff = now - settings.LOGIN_LOCKOUT_MINUTES * 60
            self._failures[email] = [stamp for stamp in failures if stamp > cutoff][
                -(settings.LOGIN_FAILURES_BEFORE_LOCKOUT - 1) :
            ] + [now]

    def clear(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


windows = _Windows()
lockouts = _Lockout()


def reset() -> None:
    """Tests call this between cases; the counters are process state, not request state."""
    windows.reset()
    lockouts.reset()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _enforce(key: str, limit: int, message: str) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    retry_after = windows.hit(key, limit, time.monotonic())
    if retry_after:
        raise AppError(
            429,
            "TOO_MANY_REQUESTS",
            message,
            {"limit": limit, "window_seconds": int(WINDOW_SECONDS), "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def limit_by_ip(route: str, limit: int, message: str):
    """Dependency factory for unauthenticated routes: the caller has no identity to key on yet."""

    def dependency(request: Request) -> None:
        _enforce(f"ip:{route}:{client_ip(request)}", limit, message)

    return dependency


def limit_by_user(route: str, limit: int, message: str):
    """Dependency factory for authenticated routes: keyed by user, so one busy volunteer cannot
    lock out the door for everybody on the same campus wifi."""

    def dependency(request: Request, user: User = Depends(get_current_user)) -> None:
        _enforce(f"user:{route}:{user.id}", limit, message)

    return dependency
