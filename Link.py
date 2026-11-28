from Emitter import*
from Qubits import*
class Link:
    def __init__(self, id, delay, depolarization_p, loss_p = 0, sim=None, kind=None, *, activity=None):
        self.id = id
        self.delay = delay
        self.depolarization_p = depolarization_p
        self.loss_p = loss_p
        self.sim = sim if sim is not None else scheduler
        self.kind = kind
        self.activity = activity
        self.ch_in = Handler(self.handle_receive, sim=self.sim, kind=kind, max_connections=1)
        self.ch_out = Emitter(sim=self.sim, kind=kind, max_connections=1)

    def handle_receive(self, qubit):
        if isinstance(qubit, Qubit) and qubit.state is not None:
            qubit.depolarize(self.depolarization_p)
            qubit.loss(self.loss_p, rng=self.sim.rng)
        if self.activity is None or not isinstance(qubit, Qubit):
            self.sim.add(self.delay, lambda: self.ch_out.emit(qubit))
            return

        alive = qubit.state is not None

        def deliver():
            if alive:
                self.activity["delivered"] += 1
                if self.activity["first_delivery_tick"] is None:
                    self.activity["first_delivery_tick"] = self.sim.time
            self.ch_out.emit(qubit)

        self.sim.add(self.delay, deliver)
