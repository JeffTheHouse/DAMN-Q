from Scheduler import*
from Emitter import*
from Emitter import scheduler
import numpy as np

class Detector_module:
    """Counts arriving qubits per port in O(1) memory.

    Counters (`ebits_1`, `ebits_2`, `single_qubits_*`, `Total_qubits_*`) are
    always maintained. Qubit references are kept in `list_a_1`/`list_a_2`
    only when `trace=True`; otherwise those lists stay empty so long runs do
    not accumulate state objects.
    """

    def __init__(self, id, trace=False, sim=None):
        self.id = id
        self.trace = bool(trace)
        self.sim = sim if sim is not None else scheduler
        self.input_a_1 = Handler(self.result_a_1, sim=self.sim, kind="quantum", max_connections=1)
        self.input_a_2 = Handler(self.result_a_2, sim=self.sim, kind="quantum", max_connections=1)
        self.output_a_1 = Emitter(sim=self.sim, kind="quantum", max_connections=1)
        self.output_a_2 = Emitter(sim=self.sim, kind="quantum", max_connections=1)
        self.list_a_1 = []
        self.list_a_2 = []
        self.ebits_1 = 0
        self.ebits_2 = 0
        self.Total_qubits_1 = 0
        self.Total_qubits_2 = 0
        self.single_qubits_1 = 0
        self.single_qubits_2 = 0

    def result_a_1(self, qubit):
        self.Total_qubits_1 += 1
        if qubit.state != None:
            if np.shape(qubit.state.density_matrix)[0] == 4:
                self.ebits_1 += 1
                if self.trace:
                    self.list_a_1.append(qubit)
                self.sim.add(0, lambda: self.output_a_1.emit(qubit))
            elif np.shape(qubit.state.density_matrix) [0] == 2:
                self.single_qubits_1 += 1

    def result_a_2(self, qubit):
        self.Total_qubits_2 += 1
        if qubit.state != None:
            if np.shape(qubit.state.density_matrix)[0] == 4:
                self.ebits_2 += 1
                if self.trace:
                    self.list_a_2.append(qubit)
                self.sim.add(0, lambda: self.output_a_2.emit(qubit))
            elif np.shape(qubit.state.density_matrix) [0] == 2:
                self.single_qubits_2 += 1
