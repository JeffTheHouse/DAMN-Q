from Emitter import*
from Measurment_module import*
from Id_generator import*
import numpy as np
import random

class Measuring_Device:
    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0):
        self.id = id
        self.delay = delay
        self.p_depolarization_depolarization= p_depolarization
        self.x_basis_p = x_basis_p
        self.ch_in_q = Handler(self.handle)
        self.ch_out_result = Emitter()
        self.id_generator_measurement = Id_generator()
        

    def handle(self, qubit):
        if qubit.state != None:
            result = measure(self.id_generator_measurement.generate(), qubit, self.x_basis_p)
            scheduler.add( self.delay, lambda: self.ch_out_result.emit(result.result))