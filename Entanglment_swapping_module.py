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
        if self.qubit_1 is not None and self.qubit_2 is not None:
            measurement_result =  random.choice(self.measurement_values)
           

            for i in range(2):
                if self.qubit_1.state.density_matrix[int(str(i) + measurement_result[0], 2)][int(str(i) + measurement_result[0],2)] != 0:
                    self.qubit_1.state.density_matrix = np.zeros((2,2))
                    self.qubit_1.state.density_matrix [i][i] = 1
                    break

            for i in range(2):    
                if self.qubit_2.state.density_matrix[int(str(i) + measurement_result[1], 2)][int(str(i) + measurement_result[1],2)] != 0:
                    self.qubit_2.state.density_matrix = np.zeros((2,2))
                    self.qubit_2.state.density_matrix [i][i] = 1 
                    break

            self.qubit_1.state , self.qubit_2.state = None, None
            self.qubit_1 , self.qubit_2 = None, None

            if int(measurement_result[0]) == 1:
                if int(measurement_result[1]) == 1:
                    measurement_result= "10"
                else:
                    measurement_result = "01"
                
                

            scheduler.add(0, lambda: self.ch_out_c_1.emit(measurement_result))
            scheduler.add(0, lambda: self.ch_out_c_2.emit(measurement_result))
        else:
            pass

            
        

        


    def handle_qubit_1(self, qubit):
        if self.qubit_1 == None and np.shape(qubit.state.density_matrix) [0] == 4 :
            self.qubit_1 = qubit
            self.entanglement_swap()
        else:
            print(f"ERROR: Entanglement swapper is doublefed on a side")
    
    def handle_qubit_2(self, qubit):
        if self.qubit_2 == None and np.shape(qubit.state.density_matrix) [0] == 4:
            self.qubit_2 = qubit
            self.entanglement_swap()
        else:
            print(f"ERROR: Entanglement swapper is doublefed on a side")

        
        
            



            

    
        