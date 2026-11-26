import numpy as np
import pytest

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


@pytest.mark.xfail(
    strict=True,
    reason="Single-qubit depolarizing_channel applies (X+Y+Z) rho (X+Y+Z) instead of sum of Pauli terms.",
)
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


@pytest.mark.xfail(
    strict=True,
    reason="measure() accesses nonexistent State.density_operator, uses elementwise *, and hardcodes 4x4 kron.",
)
def test_x_basis_measurement_single_qubit_plus_state():
    plus = 0.5 * np.array([[1.0, 1.0], [1.0, 1.0]], dtype=complex)
    q = Qubit(1, State(plus.copy()))

    out = measure(1, q, x_basis_p=1.0)

    assert out.result == "0"


@pytest.mark.xfail(
    strict=True,
    reason="measure() accesses nonexistent State.density_operator and uses elementwise * instead of @.",
)
def test_x_basis_measurement_two_qubit_bell_state():
    q1, q2 = Qubit.bell_state(1, 2, State(phi_plus.copy()))

    out = measure(1, q1, x_basis_p=1.0)

    assert out.result in ("0", "1")
    rho_post = q2.state.density_matrix
    assert rho_post.shape == (2, 2)
    assert np.isclose(np.trace(rho_post), 1.0)
