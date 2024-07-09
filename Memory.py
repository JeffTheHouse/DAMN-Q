from Qubits import*
from Emitter import*
from Id_generator import*

class Direction:
    def __init__(self, flow):
        self.flow = flow
    """dicretion = 0 means the flow of information is from left to right respecting this component
            direction = 1 means the flow of information is from right to left respecting this component"""
        

class Quantum_memory:
    def __init__(self, id, direction, delay = 0, capacity = 100, fifo = 1):
        self.id = id
        self.delay = delay
        self.fifo = fifo
        self.direction = Direction(direction)
        self.ch_in_q = Handler(self.handle_receive)
        self.ch_in_c = Handler(self.handle_classic)
        self.ch_in_paired_memory = Handler(self.handle_paired_memory)
        self.ch_out_c = Emitter()
        self.ch_out_q = Emitter()
        self.ch_out_paired_memory = Emitter()
        self.memory_address_generator = Id_generator()
        self.capacity = capacity
        self.memory = {}
        self.temperory_memory = {}
        self.paired_memory_message = None
        self.direction_signal()

    def direction_signal(self):
        scheduler.add(0,lambda: self.ch_out_q.emit(self.direction))
    
    def handle_paired_memory(self, message):
        time_stamp = min(self.temperory_memory.keys())
        if message == 1:
            self.memory[time_stamp] = self.temperory_memory.pop(time_stamp)
            scheduler.add(0, lambda: self.ch_out_c.emit(1))
        else:
            del self.temperory_memory[time_stamp]


    def handle_receive(self, qubit):
        if qubit.state != None:
            
            current_address = scheduler._time
            occupied_temporary_memory = len(self.temperory_memory)

            self.memory [current_address] = qubit
            if self.capacity == occupied_temporary_memory:
                del self.memory[min(self.memory.keys())]
            scheduler.add(1, lambda:self.ch_out_paired_memory.emit(1))
            """There needs to be at least delay = 1! The message can not arrive eralier than the qubits"""

            current_address = scheduler._time
            self.temperory_memory [current_address] = qubit


        else:
            scheduler.add(1, lambda: self.ch_out_paired_memory.emit(0))


    def handle_classic(self, request):
        if self.fifo == 1:
            emited_qubit = self.memory.pop(min(self.memory.keys()))
            scheduler.add(self.delay, lambda: self.ch_out_q.emit(emited_qubit))




        


