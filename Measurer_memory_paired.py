from collections import deque

from Emitter import*
from Measurment_module import*
from Id_generator import*
from Signals import MeasurementResult, ReadoutRejected, enqueue_ready, release_request
from Hardware_models import geometric_gap
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

    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0, sim=None,
                 detector_efficiency=1.0, dark_count_rate=0.0):
        self.id = id
        self.delay = delay
        self.p_depolarization= p_depolarization
        self.x_basis_p = x_basis_p
        self.sim = sim if sim is not None else scheduler
        if not (0.0 < detector_efficiency <= 1.0):
            raise ValueError(f"detector_efficiency must be in (0, 1], got {detector_efficiency}")
        if not (0.0 <= dark_count_rate <= 1.0):
            raise ValueError(f"dark_count_rate must be in [0, 1], got {dark_count_rate}")
        self.detector_efficiency = float(detector_efficiency)
        self.dark_count_rate = float(dark_count_rate)
        self.dark_counts = 0
        self.missed_detections = 0
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
        if self.dark_count_rate > 0.0:
            self._schedule_dark_count()

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
        if self.detector_efficiency < 1.0 and qubit.state is not None:
            qubit.loss(1.0 - self.detector_efficiency, rng=self.sim.rng)
            if qubit.state is None:
                self.missed_detections += 1
                return
        measurment_id = self.id_generator_measurement.generate()
        result = measure(measurment_id, qubit, self.x_basis_p, rng=self.sim.rng)
        out = MeasurementResult(
            result.result,
            pair_id=getattr(qubit, "pair_id", None),
            basis=result.m_axis,
            measurement_id=measurment_id,
        )
        self.sim.add(self.delay, lambda m=out: self.ch_out_result.emit(m))

    def _schedule_dark_count(self):
        self.sim.add(geometric_gap(self.dark_count_rate, self.sim.rng), self._on_dark_count)

    def _on_dark_count(self):
        mid = self.id_generator_measurement.generate()
        bit = "1" if self.sim.rng.random() < 0.5 else "0"
        basis = "x" if self.sim.rng.random() < self.x_basis_p else "z"
        self.dark_counts += 1
        out = MeasurementResult(bit, pair_id=None, basis=basis, measurement_id=mid)
        self.sim.add(self.delay, lambda m=out: self.ch_out_result.emit(m))
        self._schedule_dark_count()
