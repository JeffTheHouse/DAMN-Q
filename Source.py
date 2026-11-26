from Qubits import*
from Emitter import*
from Id_generator import*
class Source:
    def __init__(self, id, delay, type, sim=None):
        self.id = id
        if delay <= 0:
            raise ValueError("Source needs a delay bigger than zero!")
        else:
            self.delay = delay
        self.type = type
        self.sim = sim if sim is not None else scheduler
        self.id_generator = Id_generator()
        self.out_ch_1 = Emitter(sim=self.sim, kind="quantum", max_connections=1)
        self.out_ch_2 = Emitter(sim=self.sim, kind="quantum", max_connections=1)

        self.sim.add(self.delay, lambda:self.prepare())

    def prepare(self):
        if self.type == 1:
            qubit = Qubit(self.id_generator.generate(), State(np.array([[1 , 0],[0 , 0]])))
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

        self.sim.add(self.delay, lambda:self.prepare())
