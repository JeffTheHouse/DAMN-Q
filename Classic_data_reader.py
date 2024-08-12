from Emitter import*
from Qubits import*

class Classic_data_reader:
    def __init__(self, id):
        self.id = id
        self.input_1 = Handler(self.result_1)
        self.input_2 = Handler(self.result_2)
        self.list_1 = []
        self.list_2 = []

    
    def result_1(self, qubit):
        self.list_1.append(qubit)
        self.checker(len(self.list_1))
        
    def result_2(self, qubit):
        self.list_2.append(qubit)
        self.checker(len(self.list_2))

    def checker(self, length):
        if len(self.list_1) >= length and len(self.list_2) >= length:
            if self.list_1[length-1] == self.list_2[length-1]:
                print(f"Ok: Q1 {self.list_1[length-1]} , Q2 {self.list_2[length-1]}")
                del self.list_1[length-1]
                del self.list_2[length-1]

            else:
                print(f"FUCK THIS : {self.list_1[length-1]} , {self.list_2[length-1]}")

    
        
