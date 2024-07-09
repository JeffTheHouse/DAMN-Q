from Scheduler import*
from Emitter import*
from Measurment_module import*
from Memory import*
from Qubits import*


class Entaglment_swapping_module:
    def __init__(self, id, delay = 0):
        self.id = id
        self.delay = delay
        self.ch_in_q_1 = Handler(self.handle_qubit_1)
        self.ch_in_q_2 = Handler(self.handle_qubit_2)
        self.ch_out_c_1 = Emitter()
        self.ch_out_c_2 = Emitter()
        self.counter = 0
        self.qubit_1 = None
        self.qubit_2 = None
        self.measurement_values = ["00", "01", "10", "11"]
    
    def entanglement_swap(self):
        if self.qubit_1 and self.qubit_2 != None:
            measurement_result =  random.choice(self.measurement_values)
            for i in range(2):
               if self.qubit_1.state.density_matrix [i][measurement_result [1]] != 0:
                   density_matrix = np.zeros(2,2)
                   density_matrix [i][i] = 1
                   self.qubit_1.state.density_matrix = density_matrix
                   self.qubit_1.state = None
                   scheduler.add(0, lambda: self.ch_out_c_1.emit(measurement_result))
                   

            for i in range(2):
               if self.qubit_2.state.density_matrix [measurement_result [1]] [i] != 0:
                   density_matrix = np.zeros(2,2)
                   density_matrix [i][i] = 1
                   self.qubit_2.state.density_matrix = density_matrix
                   self.qubit_2.state = None
                   scheduler.add(0, lambda: self.ch_out_c_2.emit(measurement_result))

                   
               



        self.qubit_1, self.qubit_2 = None

        


    def handle_qubit_1(self, qubit):
        if self.qubit_1 == None:
            self.qubit_1 = qubit
            self.entanglement_swap()
        else:
            print(f"ERROR: Entanglement swapper is doublefed on a side")
    
    def handle_qubit_2(self, qubit):
        if self.qubit_2 == None:
            self.qubit_2 = qubit
            self.entanglement_swap()
        else:
            print(f"ERROR: Entanglement swapper is doublefed on a side")

        
        
            



            

    
        