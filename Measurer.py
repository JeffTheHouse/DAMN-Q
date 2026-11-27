from Emitter import*
from Measurment_module import*
from Id_generator import*
from Signals import MeasurementResult
import numpy as np
import random

class Measuring_Device:
    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0, sim=None):
        self.id = id
        self.delay = delay
        self.p_depolarization = p_depolarization
        self.x_basis_p = x_basis_p
        self.sim = sim if sim is not None else scheduler
        self.ch_in_q = Handler(self.handle, sim=self.sim, kind="quantum", max_connections=1)
        self.ch_out_result = Emitter(sim=self.sim, kind="classical")
        self.id_generator_measurement = Id_generator()

    def handle(self, qubit):
        if qubit.state != None:
            if self.p_depolarization > 0.0:
                qubit.depolarize(self.p_depolarization)
            mid = self.id_generator_measurement.generate()
            result = measure(mid, qubit, self.x_basis_p, rng=self.sim.rng)
            out = MeasurementResult(
                result.result,
                pair_id=getattr(qubit, "pair_id", None),
                basis=result.m_axis,
                measurement_id=mid,
            )
            self.sim.add(self.delay, lambda m=out: self.ch_out_result.emit(m))
