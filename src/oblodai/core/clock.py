"""Injectable clock for signing.

The core rejects timestamps more than +/-300 s from its own time; a host with a drifting clock
would get ``merchant.bad_signature`` on every call. The transport learns the server's time from the
``Date`` header of a signature-failure response, re-signs once, and keeps the offset only if that
re-signed attempt got past authentication.
"""

from __future__ import annotations

import time
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

__all__ = ["MAX_PLAUSIBLE_OFFSET_SECONDS", "Clock", "SkewCorrectingClock", "system_now"]


def system_now() -> int:
    """Current unix time in seconds."""
    return int(time.time())


#: Anything with ``__call__() -> int`` fits: the tests inject a frozen clock.
Clock = Callable[[], int]

#: Offsets beyond this are implausible drift and are ignored (a broken proxy ``Date``).
MAX_PLAUSIBLE_OFFSET_SECONDS = 24 * 3600


class SkewCorrectingClock:
    """A clock that can be nudged onto the server's time for the lifetime of a client."""

    def __init__(self, base: Optional[Clock] = None) -> None:
        self._base: Clock = base or system_now
        self._offset = 0

    def now(self) -> int:
        return self._base() + self._offset

    def __call__(self) -> int:
        return self.now()

    @property
    def offset(self) -> int:
        """Server-minus-local offset currently applied, seconds."""
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
        self._offset = offset_sec

    def reset(self) -> None:
        self._offset = 0
