from collections import deque

from Emitter import *
from Scheduler import *
from Qubits import *
from Operators import *
from Signals import enqueue_ready, release_request


class Pauli_corrector:
    """Applies the Pauli correction once the matching qubit and Bell outcome meet.

    When both a pending qubit (`qubit.pair_id`) and a pending Bell outcome
    (`message.swap_id`) carry IDs, they are matched by ID even if qubits and
    classical outcomes arrive in different orders. Untagged legacy inputs fall
    back to FIFO pairing.
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

    def _pop_matching_pair(self):
        """Return `(qubit, message)` matched by swap/pair ID, or FIFO if untagged."""
        if not self._pending_qubits or not self._pending_messages:
            return None

        # 1. Exact ID match: qubit.pair_id == message.swap_id
        for q_idx, q in enumerate(self._pending_qubits):
            q_pid = getattr(q, "pair_id", None)
            if q_pid is None:
                continue
            for m_idx, m in enumerate(self._pending_messages):
                if getattr(m, "swap_id", None) == q_pid:
                    del self._pending_qubits[q_idx]
                    del self._pending_messages[m_idx]
                    return q, m

        # 2. Legacy untagged fallback: only pair if either side lacks an ID
        for q_idx, q in enumerate(self._pending_qubits):
            q_pid = getattr(q, "pair_id", None)
            for m_idx, m in enumerate(self._pending_messages):
                m_sid = getattr(m, "swap_id", None)
                if q_pid is None or m_sid is None:
                    del self._pending_qubits[q_idx]
                    del self._pending_messages[m_idx]
                    return q, m

        return None

    def _try_apply(self):
        while True:
            pair = self._pop_matching_pair()
            if pair is None:
                break
            qubit, message = pair
            if qubit.register is not None:
                if message[1] == "1":
                    qubit.apply_unitary(x_operator)
                if message[0] == "1":
                    qubit.apply_unitary(z_operator)
            self.sim.add(self.delay, lambda q=qubit: self.ch_out_q.emit(q))
