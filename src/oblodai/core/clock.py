"""Injectable clock for signing.

The core rejects timestamps more than +/- ``SKEW_SECONDS`` (``x-oblodai-signing``) from its own time; a host with a drifting clock
would get ``merchant.bad_signature`` on every call. The transport learns the server's time from the
``Date`` header of a signature-failure response, re-signs once, and keeps the offset only if that
re-signed attempt got past authentication.
"""

from __future__ import annotations

import threading
import time
from email.utils import parsedate_to_datetime
from typing import Callable, Optional, Tuple

__all__ = ["MAX_PLAUSIBLE_OFFSET_SECONDS", "Clock", "SkewCorrectingClock", "system_now"]


def system_now() -> int:
    """Current unix time in seconds."""
    return int(time.time())


#: Anything with ``__call__() -> int`` fits: the tests inject a frozen clock.
Clock = Callable[[], int]

#: Offsets beyond this are implausible drift and are ignored (a broken proxy ``Date``).
MAX_PLAUSIBLE_OFFSET_SECONDS = 24 * 3600


class SkewCorrectingClock:
    """A clock that can be nudged onto the server's time for the lifetime of a client.

    One clock is shared by every call a client makes, and a client is safe to share across
    threads, so the offset lives behind a lock. A caller that installed a correction must also be
    able to tell whether it is still the one in force: see :meth:`revert_if_unchanged`.
    """

    def __init__(self, base: Optional[Clock] = None) -> None:
        self._base: Clock = base or system_now
        self._offset = 0
        self._lock = threading.Lock()

    def now(self) -> int:
        return self.now_with_offset()[0]

    def now_with_offset(self) -> Tuple[int, int]:
        """``(timestamp, offset)`` read together, so a request knows what it was signed with."""
        with self._lock:
            offset = self._offset
        return self._base() + offset, offset

    def __call__(self) -> int:
        return self.now()

    @property
    def offset(self) -> int:
        """Server-minus-local offset currently applied, seconds."""
        with self._lock:
            return self._offset

    def observe_server_date(self, date_header: Optional[str]) -> Optional[int]:
        """Measure the offset from a response ``Date``.

        Returns ``None`` when the header is absent, unparsable or implausible.
        """
        if not date_header:
            return None
        try:
            parsed = parsedate_to_datetime(date_header)
        except (TypeError, ValueError):
            return None
        if parsed is None:
            return None
        offset = round(parsed.timestamp()) - self._base()
        return None if abs(offset) > MAX_PLAUSIBLE_OFFSET_SECONDS else offset

    def correct(self, offset_sec: int) -> None:
        """Install an offset for every subsequent call this client makes."""
        with self._lock:
            self._offset = offset_sec

    def revert_if_unchanged(self, installed: int, previous: int) -> bool:
        """Undo :meth:`correct`, but only if nobody else has corrected the clock since.

        One call learning that its correction did not help says nothing about a correction another
        thread installed a moment later; clobbering that one would put every in-flight request back
        onto the wrong time.
        """
        with self._lock:
            if self._offset != installed:
                return False
            self._offset = previous
            return True

    def reset(self) -> None:
        with self._lock:
            self._offset = 0
