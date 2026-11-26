from collections import deque

from Scheduler import*
from Emitter import*
from Measurment_module import*
from Memory import*
from Qubits import*
from Signals import BellOutcome


class Entaglment_swapping_module:
    """Ideal projective Bell-state measurement (BSM) with opt-in bounded queueing.

    - Default (`queue_capacity=1`, `queue_ttl=0`): reject-when-busy. Each side
      holds at most one waiting qubit; a second arrival on an occupied side is
      explicitly rejected (traced out) and `rejected_count` is incremented.
    - Opt-in (`queue_capacity > 1`): bounded per-side queue matching arrivals
      across the two inputs by `swap_request_id` (untagged legacy qubits match
      FIFO). Arrivals beyond `queue_capacity` are rejected (`rejected_count`).
    - Optional `queue_ttl > 0`: queued qubits that are not matched within
      `queue_ttl` simulation ticks expire (traced out, `expired_count += 1`).
    """

    def __init__(self, id, delay=0, queue_capacity=1, queue_ttl=0, sim=None):
        if queue_capacity < 1:
            raise ValueError(f"queue_capacity must be >= 1, got {queue_capacity}")
        if queue_ttl is not None and queue_ttl < 0:
            raise ValueError(f"queue_ttl must be >= 0, got {queue_ttl}")
        self.id = id
        self.delay = delay
        self.queue_capacity = int(queue_capacity)
        self.queue_ttl = float(queue_ttl) if queue_ttl else 0.0
        self.sim = sim if sim is not None else scheduler
        self.ch_in_q_1 = Handler(self.handle_qubit_1, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_in_q_2 = Handler(self.handle_qubit_2, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_out_c_1 = Emitter(sim=self.sim, kind="classical")
        self.ch_out_c_2 = Emitter(sim=self.sim, kind="classical")
        self.counter = 0
        self.queued_count = 0
        self.expired_count = 0
        self.rejected_count = 0
        self._queue_1 = deque()
        self._queue_2 = deque()
        self.measurement_values = ["00", "01", "10", "11"]

    @property
    def qubit_1(self):
        return self._queue_1[0][0] if self._queue_1 else None

    @property
    def qubit_2(self):
        return self._queue_2[0][0] if self._queue_2 else None

    def _reject(self, qubit):
        self.rejected_count += 1
        if isinstance(qubit, Qubit) and qubit.state is not None:
            qubit.state = None

    def _pop_partner(self, other_queue, req_id):
        for idx, (partner, handle) in enumerate(other_queue):
            partner_req = getattr(partner, "swap_request_id", None)
            if req_id is not None:
                if partner_req == req_id:
                    del other_queue[idx]
                    if handle is not None:
                        self.sim.cancel(handle)
                    return partner
            elif partner_req is None:
                del other_queue[idx]
                if handle is not None:
                    self.sim.cancel(handle)
                return partner
        return None

    def _expire_entry(self, queue, target_qubit):
        for idx, (q, _) in enumerate(queue):
            if q is target_qubit:
                del queue[idx]
                self.expired_count += 1
                if q.state is not None:
                    q.state = None
                return

    def _perform_swap(self, q1, q2):
        outcome, remaining_reg = Register.bell_measure(q1, q2, rng=self.sim.rng)
        swap_id = self.sim.next_swap_id()
        req_id = getattr(q1, "swap_request_id", None)
        if req_id is None:
            req_id = getattr(q2, "swap_request_id", None)
        if remaining_reg is not None:
            for ep in remaining_reg._qubits:
                ep.pair_id = swap_id
        msg = BellOutcome(outcome, swap_id=swap_id, swap_request_id=req_id)
        self.counter += 1
        self.sim.add(self.delay, lambda m=msg: self.ch_out_c_1.emit(m))
        self.sim.add(self.delay, lambda m=msg: self.ch_out_c_2.emit(m))

    def _handle_arrival(self, side, qubit):
        if not isinstance(qubit, Qubit) or qubit.register is None:
            self._reject(qubit)
            return

        own_queue = self._queue_1 if side == 1 else self._queue_2
        other_queue = self._queue_2 if side == 1 else self._queue_1
        req_id = getattr(qubit, "swap_request_id", None)

        partner = self._pop_partner(other_queue, req_id)
        if partner is not None:
            if side == 1:
                self._perform_swap(qubit, partner)
            else:
                self._perform_swap(partner, qubit)
            return

        if len(own_queue) >= self.queue_capacity:
            self._reject(qubit)
            return

        expiry_handle = None
        if self.queue_ttl > 0.0:
            expiry_handle = self.sim.add(
                self.queue_ttl,
                lambda q=qubit, q_ref=own_queue: self._expire_entry(q_ref, q),
            )
        own_queue.append((qubit, expiry_handle))
        self.queued_count += 1

    def handle_qubit_1(self, qubit):
        self._handle_arrival(1, qubit)

    def handle_qubit_2(self, qubit):
        self._handle_arrival(2, qubit)
