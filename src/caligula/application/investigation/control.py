"""A person's hand on a running investigation: pause, resume, stop.

Agents meet the control at every charged tool call: while paused they wait
there, and once stopped their tools refuse and their turn ends. The team
checks it between rounds and after collection, so a stop ends the loop with
its own stop reason. What was recorded before the stop still counts.
"""

from __future__ import annotations

import threading


class RunControl:
    def __init__(self) -> None:
        self._running = threading.Event()
        self._running.set()
        self._stopped = threading.Event()

    @property
    def paused(self) -> bool:
        return not self._running.is_set() and not self.stopped

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def pause(self) -> None:
        self._running.clear()

    def resume(self) -> None:
        self._running.set()

    def stop(self) -> None:
        self._stopped.set()
        self._running.set()  # release anyone waiting, so they see the stop

    def checkpoint(self, poll: float = 0.5) -> bool:
        """Wait while paused. Returns False once the run is stopped."""
        while not self._running.wait(poll):
            pass
        return not self.stopped
