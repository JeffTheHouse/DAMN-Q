from Emitter import*
from Measurment_module import*
from Id_generator import*
import numpy as np
import random

class Measurer_memory_paired:
    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0):
        self.id = id
        self.delay = delay
        self.p_depolarization_depolarization= p_depolarization
        self.x_basis_p = x_basis_p
        self.ch_in_q = Handler(self.handle_qubit)
        self.ch_in_c = Handler(self.handle_classic)
        self.id_generator_measurement = Id_generator()
        self.qubit = None

        


        def handle_qubit(self, qubit):
            self.qubit = qubit

        def handle_measurement(self):
            print(f"measurer: {self.id}")
            if self.qubit.state != None:
                result = measure(self.id_generator_measurement.generate(), self.qubit, self.x_basis_p)
                scheduler.add( self.delay, lambda: print(f"the result is {result.result}"))
            else:
                scheduler.add(self.delay, lambda: print(f"Qubit went missing in measurer {self.id}"))

        def handle_classic(self, message):
            self.handle_measurment()
            self.qubit = None