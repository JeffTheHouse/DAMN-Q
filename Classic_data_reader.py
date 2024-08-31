from Emitter import*
from Qubits import*

class Classic_data_reader:
    def __init__(self, id):
        self.id = id
        self.input_1 = Handler(self.result_1)
        self.input_2 = Handler(self.result_2)
        self.list_1 = []
        self.list_2 = []
        self.count_success = 0
        self.count_fail = 0
        self.count_11 = 0
        self.count_10 = 0
        self.count_01 = 0
        self.count_00 = 0

    
    def result_1(self, qubit):
        self.list_1.append(qubit)
        self.checker(len(self.list_1))
        
    def result_2(self, qubit):
        self.list_2.append(qubit)
        self.checker(len(self.list_2))

    def checker(self, length):
        if len(self.list_1) >= length and len(self.list_2) >= length:
            if self.list_1[length-1] == "0" and self.list_2[length-1] == "0":
                self.count_00 += 1
            elif self.list_1[length-1] == "1" and self.list_2[length-1] == "1":
                self.count_11 += 1
            elif self.list_1[length-1] == "0" and self.list_2[length-1] == "1":
                self.count_01 += 1
            elif self.list_1[length-1] == "1" and self.list_2[length-1] == "0":
                self.count_10 += 1
            
            del self.list_1[length-1]
            del self.list_2[length-1]

    
        
