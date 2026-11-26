from collections import deque

from Qubits import *
from Emitter import *
from Id_generator import *
from Signals import PeerHerald, ReadoutRejected, Ready, Release


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

    - Peer heralds carry `PeerHerald(ok, pair_id)` so out-of-order heralds are
      matched by `pair_id` (bare `0`/`1` retains legacy FIFO matching).
    - Readiness is announced as `Ready(slot_id, memory_id)` on `ch_out_c`.
    - Controllers reply with `Release(slot_id, memory_id)` (or legacy bare `1`).
      If a tagged `Release` targets an evicted or already-released slot on this
      memory, `ReadoutRejected(slot_id, memory_id)` is emitted on `ch_out_c` so
      controllers do not stall waiting for a qubit that will never arrive.
    """

    def __init__(self, id, depolarization_p, delay=0, capacity=100, fifo=1, sim=None):
        self.id = id
        self.delay = delay
        self.depolarization_p = depolarization_p
        self.fifo = fifo
        self.sim = sim if sim is not None else scheduler
        self.ch_in_q = Handler(self.handle_receive, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_in_c = Handler(self.handle_classic, sim=self.sim, kind="classical", max_connections=1)
        self.ch_in_paired_memory = Handler(self.handle_paired_memory, sim=self.sim, kind="classical", max_connections=1)
        self.ch_out_c = Emitter(sim=self.sim, kind="classical")
        self.ch_out_q = Emitter(sim=self.sim, kind="quantum", max_connections=1)
        self.ch_out_paired_memory = Emitter(sim=self.sim, kind="classical", max_connections=1)
        self.memory_address_generator = Id_generator()
        self.capacity = capacity
        self.memory = {}
        self.temperory_memory = {}
        self.paired_memory_message = None
        self.heralded_count = 0
        self.evicted_count = 0
        self._pending_order = deque()
        self._pending_by_pair = {}
        self._early_heralds = {}
        self._confirmed_order = deque()

    @property
    def occupied_slots(self):
        return len(self.memory) + len(self.temperory_memory)

    def _evict_oldest(self):
        oldest_confirmed = None
        for sid in self._confirmed_order:
            if sid is not None and sid in self.memory:
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
            # Leave `oldest_confirmed` in `_confirmed_order` as a tombstone
            # (absent from `self.memory`) so stale release requests are rejected.
            _, evicted_qubit = self.memory.pop(oldest_confirmed)
            evicted_qubit.state = None
            self.evicted_count += 1
        elif oldest_pending is not None:
            _, evicted_qubit = self.temperory_memory.pop(oldest_pending)
            pid = getattr(evicted_qubit, "pair_id", None)
            if pid is not None and self._pending_by_pair.get(pid) == oldest_pending:
                self._pending_by_pair[pid] = None
            evicted_qubit.state = None
            self._pending_order[oldest_pending_idx] = None
            self.evicted_count += 1

    def _remove_pending_slot(self, slot_id):
        try:
            self._pending_order.remove(slot_id)
        except ValueError:
            pass

    def _resolve_herald(self, slot_id, ok):
        if slot_id is None or slot_id not in self.temperory_memory:
            # Attempt was lost on arrival or already evicted before herald arrived
            return
        arrival_time, qubit = self.temperory_memory.pop(slot_id)
        if ok:
            self.memory[slot_id] = (arrival_time, qubit)
            self._confirmed_order.append(slot_id)
            self.heralded_count += 1
            self.sim.add(0, lambda s=slot_id: self.ch_out_c.emit(Ready(s, memory_id=self.id)))
        else:
            qubit.state = None

    def handle_paired_memory(self, message):
        pid = getattr(message, "pair_id", None)
        ok = (message == 1)

        if pid is not None:
            if pid not in self._pending_by_pair:
                # Peer herald arrived before our qubit; buffer by pair_id
                self._early_heralds[pid] = ok
                return
            slot_id = self._pending_by_pair.pop(pid)
            if slot_id is not None:
                self._remove_pending_slot(slot_id)
            self._resolve_herald(slot_id, ok)
            return

        # Legacy untagged bare 0/1 herald: match by arrival order
        if not self._pending_order:
            return
        slot_id = self._pending_order.popleft()
        if slot_id is not None and slot_id in self.temperory_memory:
            _, q = self.temperory_memory[slot_id]
            q_pid = getattr(q, "pair_id", None)
            if q_pid is not None and self._pending_by_pair.get(q_pid) == slot_id:
                self._pending_by_pair.pop(q_pid, None)
        self._resolve_herald(slot_id, ok)

    def handle_receive(self, qubit):
        pid = getattr(qubit, "pair_id", None)
        if qubit.state is not None:
            if self.occupied_slots >= self.capacity:
                self._evict_oldest()
            slot_id = self.memory_address_generator.generate()
            self.temperory_memory[slot_id] = (self.sim.time, qubit)
            self._pending_order.append(slot_id)
            if pid is not None:
                self._pending_by_pair[pid] = slot_id
            herald = PeerHerald(1, pair_id=pid)
            self.sim.add(1, lambda h=herald: self.ch_out_paired_memory.emit(h))
            """There needs to be at least delay = 1! The message can not arrive eralier than the qubits"""
            if pid is not None and pid in self._early_heralds:
                early_ok = self._early_heralds.pop(pid)
                self._pending_by_pair.pop(pid, None)
                self._remove_pending_slot(slot_id)
                self._resolve_herald(slot_id, early_ok)
        else:
            self._pending_order.append(None)
            if pid is not None:
                if pid in self._early_heralds:
                    self._early_heralds.pop(pid)
                else:
                    self._pending_by_pair[pid] = None
            herald = PeerHerald(0, pair_id=pid)
            self.sim.add(1, lambda h=herald: self.ch_out_paired_memory.emit(h))

    def _remove_confirmed_slot(self, slot_id):
        try:
            self._confirmed_order.remove(slot_id)
        except ValueError:
            pass

    def handle_classic(self, request):
        if isinstance(request, Release):
            if request.memory_id is not None and request.memory_id != self.id:
                # Release is addressed to a different memory -> ignore
                return
            slot_id = request.slot_id
            if slot_id not in self.memory:
                # Evicted or already released: consume tombstone and notify controller
                self._remove_confirmed_slot(slot_id)
                self.sim.add(
                    0,
                    lambda s=slot_id: self.ch_out_c.emit(
                        ReadoutRejected(s, memory_id=self.id)
                    ),
                )
                return

            arrival_time, emitted_qubit = self.memory[slot_id]
            passed_time = self.sim.time - arrival_time
            # Validate duration before mutating memory occupancy
            p_eff = _composed_depolarization_p(self.depolarization_p, passed_time)

            self.memory.pop(slot_id)
            self._remove_confirmed_slot(slot_id)
        else:
            if not self._confirmed_order:
                return
            slot_id = (
                self._confirmed_order[0] if self.fifo == 1 else self._confirmed_order[-1]
            )
            if slot_id is None or slot_id not in self.memory:
                # Stale legacy release request for an already-evicted confirmed slot
                if self.fifo == 1:
                    self._confirmed_order.popleft()
                else:
                    self._confirmed_order.pop()
                return

            arrival_time, emitted_qubit = self.memory[slot_id]
            passed_time = self.sim.time - arrival_time
            # Validate duration before mutating memory occupancy
            p_eff = _composed_depolarization_p(self.depolarization_p, passed_time)

            if self.fifo == 1:
                self._confirmed_order.popleft()
            else:
                self._confirmed_order.pop()
            self.memory.pop(slot_id)

        if p_eff != 0.0 and emitted_qubit.state is not None:
            emitted_qubit.depolarize(p_eff)
        self.sim.add(self.delay, lambda q=emitted_qubit: self.ch_out_q.emit(q))
