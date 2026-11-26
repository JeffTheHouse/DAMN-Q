from collections import deque

from Qubits import *
from Emitter import *
from Id_generator import *
from Signals import Ready, Release


def _composed_depolarization_p(p, ticks):
    """Return effective single-qubit depolarizing probability after `ticks` discrete steps."""
    if p == 0 or ticks == 0:
        return 0.0
    if ticks < 0:
        raise ValueError(f"Storage duration must be non-negative, got {ticks}")
    if not float(ticks).is_integer():
        raise ValueError(
            f"Storage depolarization requires integer storage ticks, got {ticks}"
        )
    n = int(round(ticks))
    return 0.75 * (1.0 - (1.0 - 4.0 * p / 3.0) ** n)

class Direction:
    def __init__(self, flow):
        self.flow = flow
    """dicretion = 0 means the flow of information is from left to right respecting this component
            direction = 1 means the flow of information is from right to left respecting this component"""


class Quantum_memory:
    """Slot-based quantum memory.

    Readiness is announced as `Ready(slot_id)` on `ch_out_c`. Controllers may
    answer with `Release(slot_id)` to take exactly that slot, or with a bare
    message to take the oldest (fifo=1) or newest (fifo=0) confirmed slot.
    A release for an evicted or already-released slot is a no-op.
    """

    def __init__(self, id, depolarization_p, delay=0, capacity=100, fifo=1, sim=None):
        self.id = id
        self.delay = delay
        self.depolarization_p = depolarization_p
        self.fifo = fifo
        self.sim = sim if sim is not None else scheduler
        self.ch_in_q = Handler(self.handle_receive)
        self.ch_in_c = Handler(self.handle_classic)
        self.ch_in_paired_memory = Handler(self.handle_paired_memory)
        self.ch_out_c = Emitter()
        self.ch_out_q = Emitter()
        self.ch_out_paired_memory = Emitter()
        self.memory_address_generator = Id_generator()
        self.capacity = capacity
        self.memory = {}
        self.temperory_memory = {}
        self.paired_memory_message = None
        self._pending_order = deque()
        self._confirmed_order = deque()

    @property
    def occupied_slots(self):
        return len(self.memory) + len(self.temperory_memory)

    def _evict_oldest(self):
        oldest_confirmed_idx = None
        oldest_confirmed = None
        for idx, sid in enumerate(self._confirmed_order):
            if sid is not None and sid in self.memory:
                oldest_confirmed_idx = idx
                oldest_confirmed = sid
                break

        oldest_pending_idx = None
        oldest_pending = None
        for idx, sid in enumerate(self._pending_order):
            if sid is not None and sid in self.temperory_memory:
                oldest_pending_idx = idx
                oldest_pending = sid
                break

        if oldest_confirmed is not None and (
            oldest_pending is None or oldest_confirmed < oldest_pending
        ):
            self._confirmed_order[oldest_confirmed_idx] = None
            _, evicted_qubit = self.memory.pop(oldest_confirmed)
            evicted_qubit.state = None
        elif oldest_pending is not None:
            _, evicted_qubit = self.temperory_memory.pop(oldest_pending)
            evicted_qubit.state = None
            self._pending_order[oldest_pending_idx] = None
        self._trim_orders()

    def _trim_orders(self):
        """Drop tombstones at both ends so the order deques stay bounded."""
        while self._confirmed_order and (
            self._confirmed_order[0] is None or self._confirmed_order[0] not in self.memory
        ):
            self._confirmed_order.popleft()
        while self._confirmed_order and (
            self._confirmed_order[-1] is None or self._confirmed_order[-1] not in self.memory
        ):
            self._confirmed_order.pop()

    def handle_paired_memory(self, message):
        if not self._pending_order:
            return
        slot_id = self._pending_order.popleft()
        if slot_id is None or slot_id not in self.temperory_memory:
            # Attempt was lost on arrival or already evicted before herald arrived
            return

        arrival_time, qubit = self.temperory_memory.pop(slot_id)
        if message == 1:
            self.memory[slot_id] = (arrival_time, qubit)
            self._confirmed_order.append(slot_id)
            self.sim.add(0, lambda s=slot_id: self.ch_out_c.emit(Ready(s)))
        else:
            qubit.state = None

    def handle_receive(self, qubit):
        if qubit.state is not None:
            if self.occupied_slots >= self.capacity:
                self._evict_oldest()
            slot_id = self.memory_address_generator.generate()
            self.temperory_memory[slot_id] = (self.sim.time, qubit)
            self._pending_order.append(slot_id)
            self.sim.add(1, lambda: self.ch_out_paired_memory.emit(1))
            """There needs to be at least delay = 1! The message can not arrive eralier than the qubits"""
        else:
            self._pending_order.append(None)
            self.sim.add(1, lambda: self.ch_out_paired_memory.emit(0))

    def _find_confirmed_index(self, request):
        """Index into `_confirmed_order` of the slot this request targets, or None."""
        if isinstance(request, Release):
            for idx, sid in enumerate(self._confirmed_order):
                if sid == request.slot_id and sid in self.memory:
                    return idx
            return None
        # Untagged legacy request: oldest (FIFO) or newest (LIFO) live slot
        indices = range(len(self._confirmed_order))
        if self.fifo != 1:
            indices = reversed(indices)
        for idx in indices:
            sid = self._confirmed_order[idx]
            if sid is not None and sid in self.memory:
                return idx
        return None

    def handle_classic(self, request):
        idx = self._find_confirmed_index(request)
        if idx is None:
            # Evicted, already released, or nothing confirmed: never reassign a slot
            return

        slot_id = self._confirmed_order[idx]
        arrival_time, emitted_qubit = self.memory[slot_id]
        passed_time = self.sim.time - arrival_time
        # Validate duration before mutating memory occupancy
        p_eff = _composed_depolarization_p(self.depolarization_p, passed_time)

        self._confirmed_order[idx] = None
        self.memory.pop(slot_id)
        self._trim_orders()

        if p_eff != 0.0 and emitted_qubit.state is not None:
            emitted_qubit.depolarize(p_eff)
        self.sim.add(self.delay, lambda q=emitted_qubit: self.ch_out_q.emit(q))
