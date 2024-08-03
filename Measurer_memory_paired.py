from Emitter import*
from Measurment_module import*
from Id_generator import*
import numpy as np
import random

class Measurement_output:
    def __init__(self, id, measrument_result, es_result):
        self.id = id
        self.measurment_result = measrument_result
        self.es_result = es_result

class Measurer_memory_paired:
    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0):
        self.id = id
        self.delay = delay
        self.p_depolarization= p_depolarization
        self.x_basis_p = x_basis_p
        self.ch_in_q = Handler(self.handle_qubit)
        self.ch_in_es = Handler(self.handle_es)
        self.ch_in_memory_c = Handler(self.handle_memory_c)
        self.ch_out_memory_c = Emitter()
        self.ch_out_result = Emitter()
        self.id_generator_measurement = Id_generator()
        self.memory_qubit_counter = 0
        self.es_message = None

        
    def handle_memory_c(self, message):
        if message == 1:
            self.memory_qubit_counter += 1
    
    def handle_es(self, message):
        if self.memory_qubit_counter != 0:
            self.memory_qubit_counter -= 1
            self.es_message = message
            scheduler.add(0, lambda: self.ch_out_memory_c.emit(1))
    
    def handle_qubit(self, qubit):
        measurment_id = self.id_generator_measurement.generate()
        output = Measurement_output(measurment_id, measure(self.id_generator_measurement.generate(), qubit, self.x_basis_p), self.es_message)
        scheduler.add(self.delay, lambda: self.ch_out_result.emit(output))
        
        
