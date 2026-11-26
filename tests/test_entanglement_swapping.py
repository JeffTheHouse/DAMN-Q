import random

import numpy as np
import pytest

from Emitter import Handler, bind, scheduler
from Entanglment_swapping_module import Entaglment_swapping_module
from Pauli_corrector import Pauli_corrector
from Qubits import Qubit, State
from States import phi_plus


@pytest.mark.xfail(
    strict=True,
    reason="entanglement_swap collapses shared endpoint State to a pure basis state instead of preserving I/2 marginal.",
)
def test_swap_preserves_endpoint_reduced_state():
    rng_state = random.getstate()
    random.seed(42)
    try:
        for _ in range(20):
            s_a = State(phi_plus.copy())
            s_b = State(phi_plus.copy())
            a1, a2 = Qubit.bell_state(1, 2, s_a)
            b1, b2 = Qubit.bell_state(3, 4, s_b)

            es = Entaglment_swapping_module(1, delay=0)
            es.handle_qubit_1(a2)
            es.handle_qubit_2(b1)

            rho_a1 = a1.state.density_matrix
            rho_b2 = b2.state.density_matrix
            assert rho_a1.shape == (2, 2)
            assert rho_b2.shape == (2, 2)
            assert np.allclose(rho_a1, 0.5 * np.eye(2))
            assert np.allclose(rho_b2, 0.5 * np.eye(2))
    finally:
        random.setstate(rng_state)


@pytest.mark.xfail(
    strict=True,
    reason="Pauli_corrector crashes with TypeError if qubit arrives before its swap message instead of waiting.",
)
def test_pauli_corrector_waits_for_swap_message():
    pc = Pauli_corrector(1, delay=0)
    received = []
    bind(pc.ch_out_q, Handler(lambda q: received.append(q)))

    q = Qubit(1, State(np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)))

    # Qubit arrives before the classical correction message
    pc.ch_in_q.handle(q)
    scheduler.run(1)
    assert received == []

    # Correction message ("01" -> apply X) arrives later
    pc.ch_in_es.handle("01")
    scheduler.run(2)
    assert len(received) == 1
    assert np.allclose(
        received[0].state.density_matrix,
        np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex),
    )
