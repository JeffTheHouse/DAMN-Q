from Scheduler import*
from Emitter import*
import numpy as np

class Detector_module:
    def __init__(self, id):
        self.id = id
        self.input_a_1 = Handler(self.result_a_1)
        self.input_a_2 = Handler(self.result_a_2)
        self.output_a_1 = Emitter()
        self.output_a_2 = Emitter()
        self.list_a_1 = []
        self.list_a_2 = []
        self.Total_qubits_1 = 0
        self.Total_qubits_2 = 0
        self.single_qubits_1 = 0
        self.single_qubits_2 = 0
        
        

    def result_a_1(self, qubit):
        self.Total_qubits_1 += 1
        if qubit.state != None:
            if np.shape(qubit.state.density_matrix)[0] == 4:
                self.list_a_1.append(qubit)
                scheduler.add(0, lambda: self.output_a_1.emit(qubit))
            elif np.shape(qubit.state.density_matrix) [0] == 2:
                self.single_qubits_1 += 1
            
    
    def result_a_2(self, qubit):
        self.Total_qubits_2 += 1
        if qubit.state != None:
            if np.shape(qubit.state.density_matrix)[0] == 4:
                self.list_a_2.append(qubit)
                scheduler.add(0, lambda: self.output_a_2.emit(qubit))
            elif np.shape(qubit.state.density_matrix) [0] == 2:
                self.single_qubits_2 += 1