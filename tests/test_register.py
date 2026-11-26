import random

import numpy as np

from Measurment_module import measure
from Operators import x_operator, z_operator
from Qubits import Qubit, Register, State
from States import phi_plus


KET0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
KET1 = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex)


def _werner_state(fidelity):
    """Return Werner state F |Phi+><Phi+| + ((1 - F) / 3) (I - |Phi+><Phi+|)."""
    return fidelity * phi_plus + ((1.0 - fidelity) / 3.0) * (np.eye(4, dtype=complex) - phi_plus)


def test_measure_second_qubit_of_01_returns_1():
    rho_01 = np.kron(KET0, KET1)
    q1, q2 = Qubit.bell_state(1, 2, State(rho_01))

    out = measure(1, q2, x_basis_p=0.0)

    assert out.result == "1"
    assert out.m_axis == "z"
    assert q1.register is not q2.register
    assert np.allclose(q1.state.density_matrix, KET0)
    assert np.allclose(q2.state.density_matrix, KET1)


def test_measure_first_qubit_of_01_returns_0():
    rho_01 = np.kron(KET0, KET1)
    q1, q2 = Qubit.bell_state(1, 2, State(rho_01))

    out = measure(1, q1, x_basis_p=0.0)

    assert out.result == "0"
    assert out.m_axis == "z"
    assert np.allclose(q1.state.density_matrix, KET0)
    assert np.allclose(q2.state.density_matrix, KET1)


def test_local_depolarization_affects_only_target_qubit():
    rho_01 = np.kron(KET0, KET1)
    q1, q2 = Qubit.bell_state(1, 2, State(rho_01))

    q2.depolarize(0.75)

    assert np.allclose(q1.register.reduced_density_matrix([q1]), KET0)
    assert np.allclose(q1.register.reduced_density_matrix([q2]), 0.5 * np.eye(2))


def test_local_depolarization_on_bell_pair_produces_werner_state():
    q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
    p = 0.3

    q1.depolarize(p)

    expected = (1.0 - 4.0 * p / 3.0) * phi_plus + (4.0 * p / 3.0) * (0.25 * np.eye(4))
    assert np.allclose(q1.register.density_matrix, expected)
    assert np.allclose(q1.register.reduced_density_matrix([q1]), 0.5 * np.eye(2))
    assert np.allclose(q1.register.reduced_density_matrix([q2]), 0.5 * np.eye(2))


def test_loss_uses_general_partial_trace():
    rho_01 = np.kron(KET0, KET1)
    q1, q2 = Qubit.bell_state(1, 2, State(rho_01))

    q2.loss(1.0)

    assert q2.state is None
    assert q1.state is not None
    assert np.allclose(q1.state.density_matrix, KET0)


def test_register_join_and_reordered_reduced_density_matrix():
    q1 = Qubit(1, State(KET0.copy()))
    q2 = Qubit(2, State(KET1.copy()))

    joint = Register.join(q1.register, q2.register)

    assert q1.register is joint
    assert q2.register is joint
    assert np.allclose(joint.density_matrix, np.kron(KET0, KET1))
    assert np.allclose(joint.reduced_density_matrix([q2, q1]), np.kron(KET1, KET0))


def test_bell_measure_and_pauli_correction_yields_exact_phi_plus():
    rng_state = random.getstate()
    random.seed(7)
    seen = set()
    try:
        for _ in range(40):
            a1, a2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
            b1, b2 = Qubit.bell_state(3, 4, State(phi_plus.copy()))

            outcome, rem = Register.bell_measure(a2, b1)
            seen.add(outcome)

            assert a2.register is None
            assert b1.register is None
            assert a1.register is rem
            assert b2.register is rem

            # Endpoint marginals remain maximally mixed before correction
            assert np.allclose(rem.reduced_density_matrix([a1]), 0.5 * np.eye(2))
            assert np.allclose(rem.reduced_density_matrix([b2]), 0.5 * np.eye(2))

            if outcome[1] == "1":
                b2.apply_unitary(x_operator)
            if outcome[0] == "1":
                b2.apply_unitary(z_operator)

            joint_ab = rem.reduced_density_matrix([a1, b2])
            assert np.allclose(joint_ab, phi_plus)
    finally:
        random.setstate(rng_state)

    assert seen == {"00", "01", "10", "11"}


def test_bell_measure_werner_swap_matches_analytic_fidelity():
    f1, f2 = 0.85, 0.90
    expected_f = f1 * f2 + (1.0 - f1) * (1.0 - f2) / 3.0

    rng_state = random.getstate()
    random.seed(19)
    try:
        for _ in range(12):
            a1, a2 = Qubit.bell_state(1, 2, State(_werner_state(f1)))
            b1, b2 = Qubit.bell_state(3, 4, State(_werner_state(f2)))

            outcome, rem = Register.bell_measure(a2, b1)
            if outcome[1] == "1":
                b2.apply_unitary(x_operator)
            if outcome[0] == "1":
                b2.apply_unitary(z_operator)

            joint_ab = rem.reduced_density_matrix([a1, b2])
            fidelity = float(np.real(np.trace(phi_plus @ joint_ab)))
            assert np.isclose(fidelity, expected_f, atol=1e-12)
    finally:
        random.setstate(rng_state)
