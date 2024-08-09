from Emitter import*
from Qubits import*

class Classic_data_reader:
    def __init__(self, id):
        self.id = id
        self.input_1 = Handler(self.result_1)
        self.input_2 = Handler(self.handle_qubit_2)

    
    def result_1(self, qubit):
        
