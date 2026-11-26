from Emitter import*
from Qubits import*
class Link:
    def __init__(self, id, delay, depolarization_p, loss_p = 0, sim=None):
        self.id = id
        self.delay = delay
        self.depolarization_p = depolarization_p
        self.loss_p = loss_p
        self.sim = sim if sim is not None else scheduler
        self.ch_in = Handler(self.handle_receive, sim=self.sim)
        self.ch_out = Emitter(sim=self.sim)

    def handle_receive(self, qubit):
        if isinstance(qubit, Qubit) and qubit.state is not None:
            qubit.depolarize(self.depolarization_p)
            qubit.loss(self.loss_p, rng=self.sim.rng)
        self.sim.add(self.delay, lambda: self.ch_out.emit(qubit))
