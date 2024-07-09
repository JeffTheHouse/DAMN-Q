from Qubits import*
from Emitter import*
from Id_generator import*
class Source:
    def __init__(self, id, delay, type):
        self.id = id
        self.delay = delay
        self.type = type
        self.id_generator = Id_generator()
        self.out_ch_1 = Emitter()
        self.out_ch_2 = Emitter()

        scheduler.add(self.delay, lambda:self.prepare())
    
    def prepare(self):
        if self.type == 1:
            qubit = Qubit(self.id_generator.generate, State(np.array([[1 , 0],[0 , 0]])))
            self.out_ch_1.emit(qubit)
        elif self.type == 2:
            qubit_1 , qubit_2 = Qubit.bell_state(self.id_generator.generate(), self.id_generator.generate(), State(np.array([[.5,0,0,.5],
                                                                                                                             [0,0,0,0],
                                                                                                                             [0,0,0,0],
                                                                                                                             [.5,0,0,.5]])))
            
            self.out_ch_1.emit(qubit_1)
            self.out_ch_2.emit(qubit_2)
        else:
            print(f"error")

        scheduler.add(self.delay, lambda:self.prepare())

