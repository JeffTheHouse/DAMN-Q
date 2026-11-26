from collections import deque

from Emitter import*
from Scheduler import*
from Signals import enqueue_ready, release_request


class Orchestrator:
    def __init__(self, id, delay = 0, sim=None):
        self.id = id
        self.delay = delay
        self.sim = sim if sim is not None else scheduler
        self.ch_in_memory_1 = Handler(self.handle_memory_1, sim=self.sim)
        self.ch_in_memory_2 = Handler(self.handle_memory_2, sim=self.sim)
        self.ch_out_memory_1 = Emitter(sim=self.sim)
        self.ch_out_memory_2 = Emitter(sim=self.sim)
        self._ready_1 = deque()
        self._ready_2 = deque()

    @property
    def counter_memory_1(self):
        return len(self._ready_1)

    @property
    def counter_memory_2(self):
        return len(self._ready_2)

    def handle_memory_1(self, message):
        enqueue_ready(self._ready_1, message)
        self.coppler()

    def handle_memory_2(self, message):
        enqueue_ready(self._ready_2, message)
        self.coppler()

    def coppler(self):
        """Pair the oldest ready slot on each side and release exactly those slots."""
        if self._ready_1 and self._ready_2:
            request_1 = release_request(self._ready_1.popleft())
            request_2 = release_request(self._ready_2.popleft())
            self.sim.add(0, lambda: self.ch_out_memory_1.emit(request_1))
            self.sim.add(0, lambda: self.ch_out_memory_2.emit(request_2))
