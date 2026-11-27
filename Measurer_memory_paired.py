from collections import deque

from Emitter import*
from Measurment_module import*
from Id_generator import*
from Signals import MeasurementResult, ReadoutRejected, enqueue_ready, release_request
import numpy as np
import random

class Measurement_output:
    def __init__(self, id, measrument_result, es_result):
        self.id = id
        self.measrument_result = measrument_result
        self.es_result = es_result

class Measurer_memory_paired:
    """Measures memory qubits; each ES message claims one ready memory slot.

    ES messages wait until a readiness-announced slot exists, so the release
    is always tagged with that slot. If the memory reports `ReadoutRejected`
    for an evicted slot, the pending ES trigger is retried on the next ready
    slot instead of being lost.
    """

    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0, sim=None):
        self.id = id
        self.delay = delay
        self.p_depolarization= p_depolarization
        self.x_basis_p = x_basis_p
        self.sim = sim if sim is not None else scheduler
        self.ch_in_q = Handler(self.handle_qubit, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_in_es = Handler(self.handle_es, sim=self.sim, kind="classical", max_connections=1)
        self.ch_in_memory_c = Handler(self.handle_memory_c, sim=self.sim, kind="classical", max_connections=1)
        self.ch_out_memory_c = Emitter(sim=self.sim, kind="classical", max_connections=1)
        self.ch_out_result = Emitter(sim=self.sim, kind="classical")
        self.id_generator_measurement = Id_generator()
        self._ready_slots = deque()
        self._pending_es = deque()
        self._in_flight_es = {}
        self.es_message = None

    @property
    def memory_qubit_counter(self):
        return len(self._ready_slots)

    def handle_memory_c(self, message):
        if isinstance(message, ReadoutRejected):
            retried = self._in_flight_es.pop(message.slot_id, None)
            if retried is not None:
                self._pending_es.appendleft(retried)
            self._dispatch()
            return
        enqueue_ready(self._ready_slots, message)
        self._dispatch()

    def handle_es(self, message):
        self._pending_es.append(message)
        self._dispatch()

    def _dispatch(self):
        while self._ready_slots and self._pending_es:
            es_msg = self._pending_es.popleft()
            self.es_message = es_msg
            entry = self._ready_slots.popleft()
            request = release_request(entry)
            slot_id = entry[0] if isinstance(entry, tuple) else entry
            if slot_id is not None:
                self._in_flight_es[slot_id] = es_msg
            self.sim.add(0, lambda r=request: self.ch_out_memory_c.emit(r))

    def handle_qubit(self, qubit):
        if self._in_flight_es:
            # Clear oldest in-flight entry once a readout succeeds
            first_key = next(iter(self._in_flight_es))
            self._in_flight_es.pop(first_key, None)
        if qubit.state is not None and self.p_depolarization > 0.0:
            qubit.depolarize(self.p_depolarization)
        measurment_id = self.id_generator_measurement.generate()
        result = measure(measurment_id, qubit, self.x_basis_p, rng=self.sim.rng)
        out = MeasurementResult(
            result.result,
            pair_id=getattr(qubit, "pair_id", None),
            basis=result.m_axis,
            measurement_id=measurment_id,
        )
        self.sim.add(self.delay, lambda m=out: self.ch_out_result.emit(m))
