from collections import deque

from Emitter import *
from Scheduler import *
from Qubits import *
from Operators import *
from Signals import enqueue_ready, release_request


class Pauli_corrector:
    """Applies the Pauli correction once the matching qubit and ES message meet.

    Each ES message needs one qubit from the memory. A release is only sent
    when a readiness-announced slot is known, so requests are always tagged
    with the exact slot and never consume a slot the corrector has not seen.
    """

    def __init__(self, id, delay=0, sim=None):
        self.id = id
        self.delay = delay
        self.sim = sim if sim is not None else scheduler
        self.ch_in_q = Handler(self.handle_qubit, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_in_es = Handler(self.handle_es_c, sim=self.sim, kind="classical", max_connections=1)
        self.ch_in_memory = Handler(self.handle_memory, sim=self.sim, kind="classical", max_connections=1)
        self.ch_out_memory = Emitter(sim=self.sim, kind="classical", max_connections=1)
        self.ch_out_q = Emitter(sim=self.sim, kind="quantum", max_connections=1)
        self.message = None
        self._ready_slots = deque()
        self._in_flight = 0
        self._pending_qubits = deque()
        self._pending_messages = deque()

    @property
    def memory_qubit_counter(self):
        return len(self._ready_slots)

    def handle_memory(self, message):
        enqueue_ready(self._ready_slots, message)
        self._dispatch_requests()

    def handle_es_c(self, message):
        self._pending_messages.append(message)
        self._try_apply()
        self._dispatch_requests()

    def handle_qubit(self, qubit):
        if isinstance(qubit, Qubit):
            if self._in_flight > 0:
                self._in_flight -= 1
            self._pending_qubits.append(qubit)
            self._try_apply()
            self._dispatch_requests()

    def _dispatch_requests(self):
        """Request one known slot per ES message still lacking a qubit."""
        while self._ready_slots and (
            len(self._pending_messages) > len(self._pending_qubits) + self._in_flight
        ):
            request = release_request(self._ready_slots.popleft())
            self._in_flight += 1
            self.sim.add(0, lambda r=request: self.ch_out_memory.emit(r))

    def _try_apply(self):
        while self._pending_qubits and self._pending_messages:
            qubit = self._pending_qubits.popleft()
            message = self._pending_messages.popleft()
            if qubit.register is not None:
                if message[1] == "1":
                    qubit.apply_unitary(x_operator)
                if message[0] == "1":
                    qubit.apply_unitary(z_operator)
            self.sim.add(self.delay, lambda q=qubit: self.ch_out_q.emit(q))
