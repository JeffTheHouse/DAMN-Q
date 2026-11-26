import heapq
import itertools
import random


class EventHandle:
    """Handle returned by Simulation.add() allowing event cancellation."""

    def __init__(self, time, seq, callback, owner=None):
        self.time = time
        self.seq = seq
        self.callback = callback
        self._owner = owner
        self._cancelled = False

    @property
    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True


class Simulation:
    """One self-contained run: clock, event queue, random stream and link IDs.

    Components accept an optional `sim` argument. When omitted they use the
    process-wide default instance exported by `Emitter.scheduler`, so existing
    scripts keep working. Two `Simulation` objects never share state.
    """

    def __init__(self, seed=None):
        self.seed = seed
        self.rng = random.Random(seed)
        self._queue = []
        self._time = 0
        self._counter = itertools.count()
        self._link_ids = itertools.count()

    @property
    def time(self):
        return self._time

    def next_link_id(self):
        return next(self._link_ids)

    def add(self, delay, callback):
        if delay < 0:
            raise ValueError("Event delay must be non-negative.")
        event_time = self._time + delay
        seq = next(self._counter)
        handle = EventHandle(event_time, seq, callback, owner=self)
        heapq.heappush(self._queue, (event_time, seq, handle))
        return handle

    def cancel(self, handle):
        if getattr(handle, "_owner", None) is not self:
            raise ValueError("EventHandle does not belong to this Simulation.")
        handle.cancel()

    def _discard_cancelled(self):
        while self._queue and self._queue[0][2].cancelled:
            heapq.heappop(self._queue)

    def step(self, until=None):
        """Execute the next non-cancelled event if within `until`.

        Returns True if an event was executed, False otherwise.
        """
        self._discard_cancelled()
        if not self._queue:
            return False
        event_time, _, handle = self._queue[0]
        if until is not None and event_time > until:
            return False
        heapq.heappop(self._queue)
        self._time = event_time
        handle.callback()
        return True

    def run(self, until):
        while self.step(until=until):
            pass
        if until > self._time:
            self._time = until

    def reset(self):
        """Return the run to its initial state, including the random stream."""
        self._queue = []
        self._time = 0
        self._counter = itertools.count()
        self._link_ids = itertools.count()
        self.rng = random.Random(self.seed)
