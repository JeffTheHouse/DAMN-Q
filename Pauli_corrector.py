from Emitter import*
from Scheduler import*
from Qubits import*
from Operators import*

class Pauli_corrector:
    def __init__(self, id, delay = 0):
        self.id = id
        self.delay = delay
        self.ch_in_q = Handler(self.handle_qubit)
        self.ch_in_c = Handler(self.handle_classic)
        self.ch_in_memory = Handler(self.handle_memory)
        self.ch_out_memory = Emitter()
        self.ch_out_q = Emitter()
        self.qubit = None


    def handle_memory(self, message):
        scheduler.add(0, lambda: self.ch_out_memory.emit(1))

    def handle_qubit(self, qubit):
        if isinstance(qubit, Qubit):
            self.qubit = qubit

    def handle_classic(self, message):
        if message[0] == 1:
           self.qubit =  x_operator * self.qubit * x_operator
        if message[1] == 1:
           self.qubit = z_operator * self.qubit * z_operator
        scheduler.add(self.delay, lambda: self.ch_out_q.emit(self.qubit))
        self.qubit = None

    