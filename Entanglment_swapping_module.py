from Scheduler import*
from Emitter import*
from Measurment_module import*
from Memory import*
from Qubits import*


class Entaglment_swapping_module:
    def __init__(self, id, delay=0, sim=None):
        self.id = id
        self.delay = delay
        self.sim = sim if sim is not None else scheduler
        self.ch_in_q_1 = Handler(self.handle_qubit_1, sim=self.sim)
        self.ch_in_q_2 = Handler(self.handle_qubit_2, sim=self.sim)
        self.ch_out_c_1 = Emitter(sim=self.sim)
        self.ch_out_c_2 = Emitter(sim=self.sim)
        self.counter = 0
        self.qubit_1 = None
        self.qubit_2 = None
        self.measurement_values = ["00", "01", "10", "11"]

    def entanglement_swap(self):
        if self.qubit_1 is not None and self.qubit_2 is not None:
            q1, q2 = self.qubit_1, self.qubit_2
            self.qubit_1, self.qubit_2 = None, None
            outcome, _ = Register.bell_measure(q1, q2, rng=self.sim.rng)
            self.counter += 1
            self.sim.add(self.delay, lambda msg=outcome: self.ch_out_c_1.emit(msg))
            self.sim.add(self.delay, lambda msg=outcome: self.ch_out_c_2.emit(msg))

    def handle_qubit_1(self, qubit):
        if self.qubit_1 is None and qubit.register is not None:
            self.qubit_1 = qubit
            self.entanglement_swap()
        else:
            print("ERROR: Entanglement swapper is doublefed on a side")

    def handle_qubit_2(self, qubit):
        if self.qubit_2 is None and qubit.register is not None:
            self.qubit_2 = qubit
            self.entanglement_swap()
        else:
            print("ERROR: Entanglement swapper is doublefed on a side")
