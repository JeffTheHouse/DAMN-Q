import numpy as np
import pytest

from Emitter import Handler, bind, scheduler
from Memory import Quantum_memory
from Qubits import Qubit, State
from Source import Source


@pytest.mark.xfail(
    strict=True,
    reason="Quantum_memory keys entries by scheduler._time, so same-tick arrivals overwrite each other.",
)
def test_same_tick_arrivals_do_not_overwrite():
    mem = Quantum_memory(1, depolarization_p=0, delay=0, capacity=10)
    q1 = Qubit(1, State(np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)))
    q2 = Qubit(2, State(np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex)))

    # Both arrive at the same scheduler timestamp (t=0)
    mem.ch_in_q.handle(q1)
    mem.ch_in_q.handle(q2)

    assert len(mem.memory) == 2
    assert len(mem.temperory_memory) == 2


def test_single_qubit_source_assigns_integer_id():
    src = Source(1, delay=1, type=1)
    received = []
    bind(src.out_ch_1, Handler(lambda q: received.append(q)))

    scheduler.run(1)

    assert len(received) == 1
    assert isinstance(received[0].id, int)
