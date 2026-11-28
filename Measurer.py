from Emitter import*
from Measurment_module import*
from Id_generator import*
from Signals import MeasurementResult
from Hardware_models import geometric_gap
import numpy as np
import random

class Measuring_Device:
    """Single-qubit detector with optional imperfections.

    - `detector_efficiency` (eta in (0, 1]): each arriving qubit is detected with
      probability eta. A missed qubit is removed before measurement, which leaves
      its partner in the reduced state (loss on the detector side).
    - `dark_count_rate` (per tick, in [0, 1]): spurious clicks that carry no
      `pair_id`. They are scheduled as a geometric-gap Bernoulli process started
      when the component is created, so the run must have a finite `until`.
    Defaults (eta = 1, rate = 0) leave all random draws unchanged.
    """

    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0, sim=None,
                 detector_efficiency=1.0, dark_count_rate=0.0):
        self.id = id
        self.delay = delay
        self.p_depolarization = p_depolarization
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
        self.ch_in_q = Handler(self.handle, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_out_result = Emitter(sim=self.sim, kind="classical")
        self.id_generator_measurement = Id_generator()
        if self.dark_count_rate > 0.0:
            self._schedule_dark_count()

    def handle(self, qubit):
        if qubit.state != None:
            if self.p_depolarization > 0.0:
                qubit.depolarize(self.p_depolarization)
            if self.detector_efficiency < 1.0:
                qubit.loss(1.0 - self.detector_efficiency, rng=self.sim.rng)
                if qubit.state is None:
                    self.missed_detections += 1
                    return
            mid = self.id_generator_measurement.generate()
            result = measure(mid, qubit, self.x_basis_p, rng=self.sim.rng)
            out = MeasurementResult(
                result.result,
                pair_id=getattr(qubit, "pair_id", None),
                basis=result.m_axis,
                measurement_id=mid,
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
