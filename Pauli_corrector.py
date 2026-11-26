from collections import deque

from Emitter import *
from Scheduler import *
from Qubits import *
from Operators import *


class Pauli_corrector:
    def __init__(self, id, delay=0):
        self.id = id
        self.delay = delay
        self.ch_in_q = Handler(self.handle_qubit)
        self.ch_in_es = Handler(self.handle_es_c)
        self.ch_in_memory = Handler(self.handle_memory)
        self.ch_out_memory = Emitter()
        self.ch_out_q = Emitter()
        self.message = None
        self.memory_qubit_counter = 0
        self._pending_qubits = deque()
        self._pending_messages = deque()

    def handle_memory(self, message):
        self.memory_qubit_counter += 1

    def handle_es_c(self, message):
        self._pending_messages.append(message)
        if self._pending_qubits:
            self._try_apply()
        else:
            scheduler.add(0, lambda: self.ch_out_memory.emit(1))

    def handle_qubit(self, qubit):
        if isinstance(qubit, Qubit):
            self._pending_qubits.append(qubit)
            self._try_apply()

    def _try_apply(self):
        while self._pending_qubits and self._pending_messages:
            qubit = self._pending_qubits.popleft()
            message = self._pending_messages.popleft()
            if qubit.register is not None:
                if message[1] == "1":
                    qubit.apply_unitary(x_operator)
                if message[0] == "1":
                    qubit.apply_unitary(z_operator)
            if self.memory_qubit_counter > 0:
                self.memory_qubit_counter -= 1
            scheduler.add(self.delay, lambda q=qubit: self.ch_out_q.emit(q))
