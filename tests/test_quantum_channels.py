import random

import numpy as np

from Measurment_module import measure
from Operators import x_operator, y_operator, z_operator
from Qubits import Qubit, State
from States import phi_plus


def test_loss_on_bell_pair_leaves_maximally_mixed_partner():
    shared = State(phi_plus.copy())
    q1, q2 = Qubit.bell_state(1, 2, shared)

    q1.loss(1.0)

    assert q1.state is None
    assert np.allclose(q2.state.density_matrix, 0.5 * np.eye(2))


def test_single_qubit_depolarizing_channel():
    rho = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
    p = 0.75
    expected = (1.0 - p) * rho + (p / 3.0) * (
        x_operator @ rho @ x_operator
        + y_operator @ rho @ y_operator
        + z_operator @ rho @ z_operator
    )

    q = Qubit(1, State(rho.copy()))
    q.state.depolarizing_channel(p)

    assert np.allclose(q.state.density_matrix, expected)


def test_single_qubit_depolarizing_general_state():
    rho = 0.5 * np.array([[1.0, 1.0], [1.0, 1.0]], dtype=complex)
    p = 0.3
    expected = (1.0 - p) * rho + (p / 3.0) * (
        x_operator @ rho @ x_operator
        + y_operator @ rho @ y_operator
        + z_operator @ rho @ z_operator
    )

    q = Qubit(1, State(rho.copy()))
    q.state.depolarizing_channel(p)

    assert np.allclose(q.state.density_matrix, expected)
    assert np.isclose(np.trace(q.state.density_matrix), 1.0)
    assert np.allclose(q.state.density_matrix, q.state.density_matrix.conj().T)


def test_x_basis_measurement_single_qubit_plus_state():
    plus = 0.5 * np.array([[1.0, 1.0], [1.0, 1.0]], dtype=complex)
    q = Qubit(1, State(plus.copy()))

    out = measure(1, q, x_basis_p=1.0)

    assert out.result == "0"
    assert out.m_axis == "x"
    assert np.allclose(q.state.density_matrix, plus)


def test_x_basis_measurement_two_qubit_bell_state():
    plus = 0.5 * np.array([[1.0, 1.0], [1.0, 1.0]], dtype=complex)
    minus = 0.5 * np.array([[1.0, -1.0], [-1.0, 1.0]], dtype=complex)

    rng_state = random.getstate()
    random.seed(123)
    seen = set()
    try:
        for i in range(20):
            q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
            out = measure(i, q1, x_basis_p=1.0)
            assert out.m_axis == "x"
            assert out.result in ("0", "1")
            seen.add(out.result)
            expected_partner = plus if out.result == "0" else minus
            assert np.allclose(q2.state.density_matrix, expected_partner)
    finally:
        random.setstate(rng_state)

    assert seen == {"0", "1"}


def test_z_basis_measurement_two_qubit_bell_state():
    ket0 = np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex)
    ket1 = np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex)

    rng_state = random.getstate()
    random.seed(123)
    seen = set()
    try:
        for i in range(20):
            q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))
            out = measure(i, q1, x_basis_p=0.0)
            assert out.m_axis == "z"
            assert out.result in ("0", "1")
            seen.add(out.result)
            expected_partner = ket0 if out.result == "0" else ket1
            assert np.allclose(q2.state.density_matrix, expected_partner)
    finally:
        random.setstate(rng_state)

    assert seen == {"0", "1"}
