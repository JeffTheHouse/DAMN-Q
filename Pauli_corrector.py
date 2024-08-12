from Emitter import*
from Scheduler import*
from Qubits import*
from Operators import*

class Pauli_corrector:
    def __init__(self, id, delay = 0):
        self.id = id
        self.delay = delay
        self.ch_in_q = Handler(self.handle_qubit)
        self.ch_in_es = Handler(self.handle_es_c)
        self.ch_in_memory = Handler(self.handle_memory)
        self.ch_out_memory = Emitter()
        self.ch_out_q = Emitter()
        self.message = None
        self.memory_qubit_counter = 0


    def handle_memory(self, message):
        self.memory_qubit_counter +=1


    

    def handle_es_c(self, message):
        self.message = message
        scheduler.add(0, lambda: self.ch_out_memory.emit(1))

    
    def handle_qubit(self, qubit):
        if isinstance(qubit, Qubit):
            print(f"F1 {qubit.state.density_matrix} and received measurment: {self.message}")
            if self.message[1] == "1":
                qubit.state.density_matrix =  np.dot(np.dot(x_operator, qubit.state.density_matrix), x_operator)
                print(f"F2 {qubit.state.density_matrix} and received measurment: {self.message}")
                
            if self.message[0] == "1":
                qubit.state.density_matrix = np.dot(np.dot(z_operator, qubit.state.density_matrix), z_operator)
                print(f"F3 {qubit.state.density_matrix} and received measurment: {self.message}")
            self.memory_qubit_counter -= 1
            self.message = None
            scheduler.add(self.delay, lambda: self.ch_out_q.emit(qubit))

    