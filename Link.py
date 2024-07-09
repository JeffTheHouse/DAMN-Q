from Emitter import*
from Qubits import*
class Link:
    def __init__(self, id, delay, depolarization_p, loss_p = 0):
        self.id = id
        self.delay = delay
        self.depolarization_p = depolarization_p
        self.loss_p = loss_p
        self.ch_in = Handler(self.handle_receive)
        self.ch_out = Emitter()
    

    def handle_receive(self, qubit):
        if isinstance(qubit, Qubit):
            qubit.state.depolarizing_channel(self.depolarization_p)
            qubit.loss(self.loss_p)
        scheduler.add(self.delay, lambda: self.ch_out.emit(qubit))
