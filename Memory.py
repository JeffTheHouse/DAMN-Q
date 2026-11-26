from collections import deque

from Qubits import *
from Emitter import *
from Id_generator import *


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
    def __init__(self, id, depolarization_p, delay=0, capacity=100, fifo=1):
        self.id = id
        self.delay = delay
        self.depolarization_p = depolarization_p
        self.fifo = fifo
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
        oldest_confirmed = self._confirmed_order[0] if self._confirmed_order else None
        oldest_pending = None
        for sid in self._pending_order:
            if sid is not None and sid in self.temperory_memory:
                oldest_pending = sid
                break

        if oldest_confirmed is not None and (
            oldest_pending is None or oldest_confirmed < oldest_pending
        ):
            self._confirmed_order.popleft()
            _, evicted_qubit = self.memory.pop(oldest_confirmed)
            evicted_qubit.state = None
        elif oldest_pending is not None:
            _, evicted_qubit = self.temperory_memory.pop(oldest_pending)
            evicted_qubit.state = None
            for idx, sid in enumerate(self._pending_order):
                if sid == oldest_pending:
                    self._pending_order[idx] = None
                    break

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
            scheduler.add(0, lambda: self.ch_out_c.emit(1))
        else:
            qubit.state = None

    def handle_receive(self, qubit):
        if qubit.state is not None:
            if self.occupied_slots >= self.capacity:
                self._evict_oldest()
            slot_id = self.memory_address_generator.generate()
            self.temperory_memory[slot_id] = (scheduler._time, qubit)
            self._pending_order.append(slot_id)
            scheduler.add(1, lambda: self.ch_out_paired_memory.emit(1))
            """There needs to be at least delay = 1! The message can not arrive eralier than the qubits"""
        else:
            self._pending_order.append(None)
            scheduler.add(1, lambda: self.ch_out_paired_memory.emit(0))

    def handle_classic(self, request):
        if not self._confirmed_order:
            return
        if self.fifo == 1:
            slot_id = self._confirmed_order.popleft()
        else:
            slot_id = self._confirmed_order.pop()

        arrival_time, emitted_qubit = self.memory.pop(slot_id)
        passed_time = scheduler._time - arrival_time
        p_eff = _composed_depolarization_p(self.depolarization_p, passed_time)
        if p_eff != 0.0 and emitted_qubit.state is not None:
            emitted_qubit.depolarize(p_eff)
        scheduler.add(self.delay, lambda q=emitted_qubit: self.ch_out_q.emit(q))
