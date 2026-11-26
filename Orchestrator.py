from collections import deque

from Emitter import*
from Scheduler import*
from Signals import enqueue_ready, release_request


class Orchestrator:
    def __init__(self, id, delay = 0, sim=None):
        self.id = id
        self.delay = delay
        self.sim = sim if sim is not None else scheduler
        self.ch_in_memory_1 = Handler(self.handle_memory_1, sim=self.sim, kind="classical", max_connections=1)
        self.ch_in_memory_2 = Handler(self.handle_memory_2, sim=self.sim, kind="classical", max_connections=1)
        self.ch_out_memory_1 = Emitter(sim=self.sim, kind="classical", max_connections=1)
        self.ch_out_memory_2 = Emitter(sim=self.sim, kind="classical", max_connections=1)
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
        """Pair the oldest ready slot on each side and release them with a shared swap_request_id."""
        if self._ready_1 and self._ready_2:
            e1 = self._ready_1.popleft()
            e2 = self._ready_2.popleft()
            # Only attach swap_request_id when at least one side has a real memory_id
            # (keeps bare Ready(5) unit tests returning Release(5) cleanly).
            has_mem_id = (
                (isinstance(e1, tuple) and e1[1] is not None)
                or (isinstance(e2, tuple) and e2[1] is not None)
            )
            req_id = self.sim.next_swap_request_id() if has_mem_id else None
            request_1 = release_request(e1, swap_request_id=req_id)
            request_2 = release_request(e2, swap_request_id=req_id)
            self.sim.add(0, lambda: self.ch_out_memory_1.emit(request_1))
            self.sim.add(0, lambda: self.ch_out_memory_2.emit(request_2))
