import random

import numpy as np
import pytest

from Emitter import Handler, bind, scheduler
from Entanglment_swapping_module import Entaglment_swapping_module
from Pauli_corrector import Pauli_corrector
from Qubits import Qubit, State
from States import phi_plus


KET0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
KET1 = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex)
PLUS = 0.5 * np.array([[1.0, 1.0], [1.0, 1.0]], dtype=complex)
MINUS = 0.5 * np.array([[1.0, -1.0], [-1.0, 1.0]], dtype=complex)


def _werner_state(fidelity):
    return fidelity * phi_plus + ((1.0 - fidelity) / 3.0) * (np.eye(4, dtype=complex) - phi_plus)


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

            assert a1.register is b2.register
            rho_a1 = a1.register.reduced_density_matrix([a1])
            rho_b2 = b2.register.reduced_density_matrix([b2])
            assert rho_a1.shape == (2, 2)
            assert rho_b2.shape == (2, 2)
            assert np.allclose(rho_a1, 0.5 * np.eye(2))
            assert np.allclose(rho_b2, 0.5 * np.eye(2))
    finally:
        random.setstate(rng_state)


def test_pauli_corrector_waits_for_swap_message():
    pc = Pauli_corrector(1, delay=0)
    received = []
    memory_requests = []
    bind(pc.ch_out_q, Handler(lambda q: received.append(q)))
    bind(pc.ch_out_memory, Handler(lambda m: memory_requests.append(m)))

    q = Qubit(1, State(KET0.copy()))

    # Qubit arrives before the classical correction message
    pc.ch_in_q.handle(q)
    scheduler.run(1)
    assert received == []
    assert memory_requests == []

    # Correction message ("01" -> apply X) arrives later; buffered qubit is consumed
    # without requesting another qubit from memory
    pc.ch_in_es.handle("01")
    scheduler.run(2)
    assert memory_requests == []
    assert len(received) == 1
    assert np.allclose(received[0].state.density_matrix, KET1)


def test_pauli_corrector_message_first_requests_memory_and_queues_fifo():
    pc = Pauli_corrector(1, delay=0)
    received = []
    memory_requests = []
    bind(pc.ch_out_q, Handler(lambda q: received.append(q)))
    bind(pc.ch_out_memory, Handler(lambda m: memory_requests.append(m)))

    # Two corrections arrive before any qubits
    pc.ch_in_es.handle("01")  # X on |0> -> |1>
    pc.ch_in_es.handle("10")  # Z on |+> -> |->
    scheduler.run(1)
    assert memory_requests == [1, 1]
    assert received == []

    q1 = Qubit(1, State(KET0.copy()))
    q2 = Qubit(2, State(PLUS.copy()))
    pc.ch_in_q.handle(q1)
    pc.ch_in_q.handle(q2)
    scheduler.run(2)

    assert len(received) == 2
    assert received[0] is q1
    assert received[1] is q2
    assert np.allclose(received[0].state.density_matrix, KET1)
    assert np.allclose(received[1].state.density_matrix, MINUS)


@pytest.mark.parametrize(
    ("draw", "expected_outcome"),
    [
        (0.125, "00"),
        (0.375, "01"),
        (0.625, "10"),
        (0.875, "11"),
    ],
)
def test_swapper_and_corrector_produce_exact_phi_plus_for_all_four_outcomes(
    monkeypatch, draw, expected_outcome
):
    monkeypatch.setattr(random, "random", lambda: draw)

    es = Entaglment_swapping_module(1, delay=3)
    pc = Pauli_corrector(1, delay=2)

    c1_events = []
    c2_events = []
    corrected = []
    bind(es.ch_out_c_1, Handler(lambda m: c1_events.append((scheduler.time, m))))
    bind(es.ch_out_c_2, Handler(lambda m: c2_events.append((scheduler.time, m))))
    bind(es.ch_out_c_2, pc.ch_in_es)
    bind(pc.ch_out_q, Handler(lambda q: corrected.append((scheduler.time, q))))

    a1, a2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
    b1, b2 = Qubit.bell_state(3, 4, State(phi_plus.copy()))

    # Feed b2 into corrector and swap a2, b1 at t=0
    pc.ch_in_q.handle(b2)
    es.ch_in_q_1.handle(a2)
    es.ch_in_q_2.handle(b1)

    scheduler.run(10)

    assert c1_events == [(3, expected_outcome)]
    assert c2_events == [(3, expected_outcome)]
    assert len(corrected) == 1
    assert corrected[0][0] == 5
    assert corrected[0][1] is b2

    assert a1.register is b2.register
    joint_ab = a1.register.reduced_density_matrix([a1, b2])
    assert np.allclose(joint_ab, phi_plus)


def test_swapper_and_corrector_werner_states_match_analytic_fidelity():
    f1, f2 = 0.85, 0.90
    expected_f = f1 * f2 + (1.0 - f1) * (1.0 - f2) / 3.0

    rng_state = random.getstate()
    random.seed(23)
    try:
        for _ in range(12):
            scheduler.reset()
            es = Entaglment_swapping_module(1, delay=1)
            pc = Pauli_corrector(1, delay=1)
            corrected = []
            bind(es.ch_out_c_2, pc.ch_in_es)
            bind(pc.ch_out_q, Handler(lambda q: corrected.append(q)))

            a1, a2 = Qubit.bell_state(1, 2, State(_werner_state(f1)))
            b1, b2 = Qubit.bell_state(3, 4, State(_werner_state(f2)))

            pc.ch_in_q.handle(b2)
            es.ch_in_q_1.handle(a2)
            es.ch_in_q_2.handle(b1)

            scheduler.run(5)

            assert len(corrected) == 1
            assert a1.register is b2.register
            joint_ab = a1.register.reduced_density_matrix([a1, b2])
            fidelity = float(np.real(np.trace(phi_plus @ joint_ab)))
            assert np.isclose(fidelity, expected_f, atol=1e-12)
    finally:
        random.setstate(rng_state)
