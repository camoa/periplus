"""A line on standard error when one rule or span runs long on one file.

Python's ``re`` keeps the interpreter lock for the whole of one search, so a watching thread gets
no turn while a runaway pattern backtracks. The search does check for signals as it goes, so a
one-shot timer's handler runs in the middle of it, writes the line, and lets the search go on.
The line reads the clock; nothing it does reaches the map or the report.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from types import FrameType, TracebackType
from typing import Any

__all__ = ["DEFAULT_SLOW_AFTER", "SlowWatch"]

#: Seconds one rule or span may spend on one file before the line is written.
DEFAULT_SLOW_AFTER = 10.0


class SlowWatch:
    """Times each step, one rule or span on one file, while it is entered as a context.

    ``begin`` ends the step before it and starts the next; ``end`` ends the last. A step that
    passes ``after`` seconds writes one line as it passes them, and one more with its time when
    it ends. Off a platform with ``setitimer``, or off the main thread, where a handler cannot be
    set, nothing is written.
    """

    def __init__(self, after: float) -> None:
        self._after = after
        self._on = hasattr(signal, "setitimer") and (
            threading.current_thread() is threading.main_thread()
        )
        self._step: tuple[str, str, float] | None = None
        self._warned = False
        self._previous: Any = None

    def __enter__(self) -> SlowWatch:
        if self._on:
            self._previous = signal.signal(signal.SIGALRM, self._alarm)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._on:
            self.end()
            signal.signal(signal.SIGALRM, self._previous)

    def begin(self, what: str, file: str) -> None:
        """End the step running, if any, and start timing ``what`` on ``file``."""
        if not self._on:
            return
        self.end()
        self._step, self._warned = (what, file, time.monotonic()), False
        signal.setitimer(signal.ITIMER_REAL, self._after)

    def end(self) -> None:
        """Stop timing the step running, writing its time if its line was written."""
        if not self._on or self._step is None:
            return
        signal.setitimer(signal.ITIMER_REAL, 0)
        what, file, began = self._step
        self._step = None
        if self._warned:
            _write(f"{what} on {file}: took {time.monotonic() - began:.2f} s")

    def _alarm(self, signum: int, frame: FrameType | None) -> None:
        step = self._step
        if step is None or self._warned:
            return
        # A signal raised just before its step ended can run in the next step, and the timer's
        # clock is not the monotonic one: either way the step is not late yet, so wait the rest.
        left = self._after - (time.monotonic() - step[2])
        if left > 0:
            signal.setitimer(signal.ITIMER_REAL, left)
            return
        what, file, began = step
        self._warned = True
        _write(f"{what} on {file}: {time.monotonic() - began:.2f} s so far, still running")


def _write(line: str) -> None:
    sys.stderr.write(f"periplus map: slow: {line}\n")
    sys.stderr.flush()
